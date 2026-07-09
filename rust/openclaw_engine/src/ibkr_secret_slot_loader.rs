//! MODULE_NOTE
//! 模塊用途：IBKR Phase 2 `secret_slot_contract` 純載入器（P1，fingerprint-only）。
//!   stat `<secrets-root>/external/ibkr/{readonly,paper,live}` 三槽，只算兩個
//!   sha256 指紋（`secret_slot_fingerprint` = paper 槽 stat-only 描述符；
//!   `account_fingerprint_hash` = normalize(paper/account_id)），產出一條可過
//!   `IbkrSecretSlotContractV1::validate()` 的 leg。
//! 主要函數：`load_ibkr_secret_slot_contract_from_base`（純 loader，收 base dir，
//!   可測繞全域）、`resolve_ibkr_secrets_base` + `load_ibkr_secret_slot_contract`
//!   （env-resolving wrapper）、`ibkr_secret_slot_contract`（OnceLock cache）、
//!   `denied_ibkr_secret_slot_contract_fallback`（fail-closed 回退）、
//!   `ibkr_paper_slot_fingerprint` / `ibkr_account_fingerprint_hash`（P1 建、P5
//!   復用的單一 pub(crate) 純指紋函數，保證跨腿 hash 對齊）。
//! 依賴：`openclaw_types::ibkr_phase2_runtime`（消費既有型別，不新造）、`sha2`/
//!   `hex`（指紋）、`libc::geteuid`（owner 校驗）、std::fs/os::unix。
//! 硬邊界（絕不鬆動）：
//!   - 只讀、零真錢、不接 IPC/Python/DB、不開 socket、不翻 flag、不接 matrix
//!     live-eval；live 槽永不讀內容、保持 absent（AMD-2026-07-08-01）。
//!   - 明文零逃逸：account_id 是唯一被讀內容的檔，讀→normalize→hash→立即歸零
//!     drop（`ZeroizedString`）；contract struct 全欄位皆 enum/bool/64-hex，
//!     結構上無欄位可容明文；`secret_content_serialized` / `account_id_serialized`
//!     恒為常量 false（不從輸入推導）；error/log 只帶路徑 + io::Error + posture/
//!     bool/64-hex，絕不內插明文。
//!   - fail-closed：base 不可信 / symlink 槽 / 祖先目錄可寫 → Err → 呼叫端
//!     denied fallback；絕不捏造 accepted=true 的假 PASS。
//!
//! TODO(P5)：本模塊為 scaffold-only leg——P1 不接任何 production caller（OnceLock
//!   cache 無讀者、無 IPC route）。故用檔案級 `#![allow(dead_code)]`（沿 crate
//!   既有慣例：param_extractor 於首個 consumer 落地前的做法）。P5 session
//!   attestation / healthcheck 接入後，改為函數級 allow 或移除本屬性。

#![allow(dead_code)]

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use sha2::{Digest, Sha256};

use openclaw_types::{
    IbkrSecretSlotContractV1, IbkrSecretSlotPosture, IBKR_SECRET_SLOT_CONTRACT_ID,
};

/// paper 槽內 IBKR 帳號檔的檔名。抽 const 供 P5 復用，避免各腿檔名漂移。
const IBKR_ACCOUNT_ID_FILENAME: &str = "account_id";

/// secret_slot_contract 的進程級快取（load-once）。
///
/// 為什麼 OnceLock<Result<..>>：source-of-record 只需 boot 後載入一次；失敗也
/// 快取為 Err 以維持 fail-closed（呼叫端回退 denied fallback + 標 reason）。
static IBKR_SECRET_SLOT_CONTRACT: OnceLock<Result<IbkrSecretSlotContractV1, String>> =
    OnceLock::new();

// ---------------------------------------------------------------------------
// 明文歸零 wrapper（覆写④ / Q4）
// ---------------------------------------------------------------------------

/// account_id 明文的 RAII 包裝：`Drop` 時手動把底層 bytes 全部歸零，避免明文殘留
/// 在堆上。
///
/// 為什麼不引入 zeroize crate：威脅模型為本機 owner-only 檔 + 受信引擎進程（LOW），
/// 手動 Drop 歸零已足夠且不增新 workspace 依賴（AMD Q4 裁決）。
struct ZeroizedString(String);

impl ZeroizedString {
    fn as_str(&self) -> &str {
        &self.0
    }
}

impl Drop for ZeroizedString {
    fn drop(&mut self) {
        // 手動歸零：把底層 bytes 全部覆寫為 0。Drop 後 String 不再被使用，故短暫
        // 破壞 UTF-8 不變量無害（NUL 本身仍是合法 UTF-8）。
        // SAFETY: 僅寫 0 到既有 buffer，不改長度/容量，且緊接著正常釋放。
        unsafe {
            for b in self.0.as_mut_vec() {
                *b = 0;
            }
        }
    }
}

/// 讀 account_id 明文並包進歸零 wrapper。
///
/// 為什麼 error 只帶路徑 + io::Error：結構上不可能把（部分讀入的）檔案內容內插進
/// 錯誤字串（明文零逃逸 / E3 LOW-1 日誌紀律）。讀失敗（缺檔/權限/非 UTF-8）時
/// io::Error 不含檔案內容。
fn read_account_id_zeroized(path: &Path) -> Result<ZeroizedString, String> {
    let raw = std::fs::read_to_string(path)
        .map_err(|e| format!("read account_id at {} failed: {e}", path.display()))?;
    Ok(ZeroizedString(raw))
}

// ---------------------------------------------------------------------------
// 單一共用純指紋函數（P1 建、P5 復用；覆写②）
// ---------------------------------------------------------------------------

/// account_id → sha256(trim + ASCII 大寫)。
///
/// 為什麼是單一 pub(crate) 純函數：P5 attestation 必須對「同一輸入」用「同一算法」
/// 才能與本腿的 `account_fingerprint_hash` 對齊（PA §5.2 跨腿契約）。正規化
/// `trim()` 去尾換行、`to_ascii_uppercase()` 統一大小寫（IBKR 帳號為大寫英數）。
/// `hex::encode(Sha256)` 恒為 64 lowercase hex → by construction 過 `is_sha256_hex`。
pub(crate) fn ibkr_account_fingerprint_hash(account_id: &str) -> String {
    let normalized = account_id.trim().to_ascii_uppercase();
    let mut hasher = Sha256::new();
    hasher.update(normalized.as_bytes());
    hex::encode(hasher.finalize())
}

/// paper 槽 stat-only 描述符 → sha256。
///
/// 覆写②（E3/CC 裁決，推翻 PA §2.1 content-digest 建議）：描述符**只含 filename +
/// mode + len，絕不讀憑證內容**：
/// ```text
/// "ibkr_secret_slot_v1\n"
/// "paper\tpresent=<bool>\tdir_mode=<0oNNN>\n"
///   for each regular file in paper/ (filename ASCII 升序):
///     "<filename>\tmode=<0oNNN>\tlen=<u64>\n"
/// ```
/// 為什麼 symlink → Err：槽內 symlink 一律拒（TOCTOU / 目錄逃逸，覆写③b）。本函數
/// 為 pub(crate) 供 P5 獨立復用，故自身即做 symlink 拒絕，不倚賴呼叫端先檢查。
#[cfg(unix)]
pub(crate) fn ibkr_paper_slot_fingerprint(paper_slot_dir: &Path) -> Result<String, String> {
    use std::os::unix::fs::PermissionsExt;

    let dir_meta = std::fs::symlink_metadata(paper_slot_dir)
        .map_err(|e| format!("paper slot stat {} failed: {e}", paper_slot_dir.display()))?;
    let present = dir_meta.is_dir();
    let dir_mode = dir_meta.permissions().mode() & 0o777;

    // 收集 regular 檔 (filename, mode, len)；symlink → Err；子目錄等其他型別跳過。
    let mut files: Vec<(String, u32, u64)> = Vec::new();
    for entry in std::fs::read_dir(paper_slot_dir)
        .map_err(|e| format!("paper slot read_dir {} failed: {e}", paper_slot_dir.display()))?
    {
        let entry =
            entry.map_err(|e| format!("paper slot entry read failed in {}: {e}", paper_slot_dir.display()))?;
        let ep = entry.path();
        let em = std::fs::symlink_metadata(&ep)
            .map_err(|e| format!("paper slot lstat {} failed: {e}", ep.display()))?;
        let ft = em.file_type();
        if ft.is_symlink() {
            return Err(format!("paper slot entry is symlink (denied): {}", ep.display()));
        }
        if ft.is_file() {
            let name = entry.file_name().to_string_lossy().into_owned();
            let mode = em.permissions().mode() & 0o777;
            files.push((name, mode, em.len()));
        }
    }
    // 決定性：按 filename ASCII 升序（不倚賴 read_dir 的檔系統順序）。
    files.sort_by(|a, b| a.0.cmp(&b.0));

    let mut descriptor = String::new();
    descriptor.push_str("ibkr_secret_slot_v1\n");
    descriptor.push_str(&format!("paper\tpresent={}\tdir_mode={:#o}\n", present, dir_mode));
    for (name, mode, len) in &files {
        descriptor.push_str(&format!("{}\tmode={:#o}\tlen={}\n", name, mode, len));
    }

    let mut hasher = Sha256::new();
    hasher.update(descriptor.as_bytes());
    Ok(hex::encode(hasher.finalize()))
}

// ---------------------------------------------------------------------------
// 權限 / symlink / 祖先校驗（覆写③，全 fail-closed；#[cfg(unix)]）
// ---------------------------------------------------------------------------

/// 覆写③(c)：祖先目錄 owner-only。`external/` 與 `ibkr/` 皆須 mode==0o700 且
/// owner==euid。
///
/// 為什麼 fail-closed(Err)：可寫的祖先目錄允許他人替換槽/檔（TOCTOU / 目錄逃逸），
/// 凭证信任鏈崩潰 → 整個 base 不可信，回 Err → 呼叫端 denied fallback。用 lstat：
/// symlink 祖先的 mode & 0o777 != 0o700 → 自然 fail-closed。此檢查同時涵蓋覆写③(d)
/// 的 nonexistent-base（stat 失敗即 Err）。
#[cfg(unix)]
fn ensure_ancestor_owner_only(ibkr_base: &Path) -> Result<(), String> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let euid = unsafe { libc::geteuid() } as u32;
    // 檢查 ibkr/（= ibkr_base）與其父 external/。
    let ancestors = [Some(ibkr_base), ibkr_base.parent()];
    for anc in ancestors {
        let path = anc.ok_or_else(|| "ibkr base has no parent (external) dir".to_string())?;
        let meta = std::fs::symlink_metadata(path)
            .map_err(|e| format!("ancestor stat {} failed: {e}", path.display()))?;
        let mode = meta.permissions().mode() & 0o777;
        if mode != 0o700 {
            return Err(format!(
                "ancestor_dir_writable: {} mode={:#o} (require 0o700)",
                path.display(),
                mode
            ));
        }
        if meta.uid() as u32 != euid {
            return Err(format!(
                "ancestor_dir_not_owned: {} uid={} euid={}",
                path.display(),
                meta.uid(),
                euid
            ));
        }
    }
    Ok(())
}

/// 覆写③(b)：槽目錄本身不得為 symlink（lstat 不跟隨）。
///
/// 不存在或非 symlink → Ok（存在性由各槽 eval 處理）；是 symlink → Err（不跟隨，
/// 防目錄逃逸）。
#[cfg(unix)]
fn reject_symlink_slot(dir: &Path) -> Result<(), String> {
    match std::fs::symlink_metadata(dir) {
        Ok(m) if m.file_type().is_symlink() => Err(format!(
            "ibkr secret slot dir is symlink (denied): {}",
            dir.display()
        )),
        _ => Ok(()),
    }
}

/// 判定槽是否 owner-only：目錄 mode==0o700 + owner==euid，且所有 regular 檔
/// mode==0o600 + owner==euid。
///
/// 為什麼槽內 symlink → Err：覆写③(b)「槽內文件含 symlink 亦 Err」（TOCTOU）。子
/// 目錄等其他型別不納入 owner-only 判定（不在 P1 佈局規格內）。
#[cfg(unix)]
fn slot_is_owner_only(dir: &Path, dir_meta: &std::fs::Metadata) -> Result<bool, String> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let euid = unsafe { libc::geteuid() } as u32;
    let mut ok = (dir_meta.permissions().mode() & 0o777) == 0o700 && dir_meta.uid() as u32 == euid;

    for entry in std::fs::read_dir(dir)
        .map_err(|e| format!("read slot dir {} failed: {e}", dir.display()))?
    {
        let entry =
            entry.map_err(|e| format!("read slot entry in {} failed: {e}", dir.display()))?;
        let ep = entry.path();
        let em = std::fs::symlink_metadata(&ep)
            .map_err(|e| format!("lstat {} failed: {e}", ep.display()))?;
        let ft = em.file_type();
        if ft.is_symlink() {
            return Err(format!("ibkr slot entry is symlink (denied): {}", ep.display()));
        }
        if ft.is_file() {
            let file_ok =
                (em.permissions().mode() & 0o777) == 0o600 && em.uid() as u32 == euid;
            ok = ok && file_ok;
        }
    }
    Ok(ok)
}

// ---------------------------------------------------------------------------
// 三槽 posture 評估（#[cfg(unix)]）
// ---------------------------------------------------------------------------

/// readonly 槽：不存在 → Missing（非違規）；present + owner-only → PresentHashed；
/// present + 權限過寬 → Unknown（owner_only=false）。回 (posture, owner_only)。
#[cfg(unix)]
fn eval_readonly_slot(dir: &Path) -> Result<(IbkrSecretSlotPosture, bool), String> {
    let meta = match std::fs::symlink_metadata(dir) {
        Ok(m) => m,
        // 不存在 → Missing；缺席非權限違規 → owner_only 貢獻 true。
        Err(_) => return Ok((IbkrSecretSlotPosture::Missing, true)),
    };
    if !meta.is_dir() {
        // 存在但非目錄（佔位）→ 佈局異常 → Unknown + owner_only=false。
        return Ok((IbkrSecretSlotPosture::Unknown, false));
    }
    let owner_only = slot_is_owner_only(dir, &meta)?;
    if owner_only {
        Ok((IbkrSecretSlotPosture::PresentHashed, true))
    } else {
        Ok((IbkrSecretSlotPosture::Unknown, false))
    }
}

/// paper 槽評估結果。
#[cfg(unix)]
struct PaperEval {
    posture: IbkrSecretSlotPosture,
    owner_only: bool,
    secret_slot_fingerprint: String,
    account_fingerprint_hash: String,
}

/// paper 槽（權威操作槽）：不存在 → Missing（fingerprint/hash 保持 ""，不捏值）；
/// present → 算 stat-only 指紋 + 讀 account_id 算 hash。owner-only 且 account_id
/// 可 hash → PresentHashed；否則 → Unknown（validate 會拒）。
#[cfg(unix)]
fn eval_paper_slot(dir: &Path) -> Result<PaperEval, String> {
    let meta = match std::fs::symlink_metadata(dir) {
        Ok(m) => m,
        Err(_) => {
            // paper 不存在 → Missing；不捏 fingerprint/hash。
            return Ok(PaperEval {
                posture: IbkrSecretSlotPosture::Missing,
                owner_only: true,
                secret_slot_fingerprint: String::new(),
                account_fingerprint_hash: String::new(),
            });
        }
    };
    if !meta.is_dir() {
        return Ok(PaperEval {
            posture: IbkrSecretSlotPosture::Unknown,
            owner_only: false,
            secret_slot_fingerprint: String::new(),
            account_fingerprint_hash: String::new(),
        });
    }

    // 權限 + 槽內 symlink 檢查（symlink → Err）。
    let owner_only = slot_is_owner_only(dir, &meta)?;

    // stat-only 指紋（絕不讀憑證內容）。
    let secret_slot_fingerprint = ibkr_paper_slot_fingerprint(dir)?;

    // account_id：唯一被讀內容的檔；讀→normalize→hash→立即歸零 drop。
    // 缺檔/讀失敗 → hash=""（不捏值），posture 降為 Unknown（fail-closed）。
    let account_id_path = dir.join(IBKR_ACCOUNT_ID_FILENAME);
    let (account_fingerprint_hash, account_ok) = match read_account_id_zeroized(&account_id_path) {
        Ok(guard) => (ibkr_account_fingerprint_hash(guard.as_str()), true),
        Err(_) => (String::new(), false),
    };

    let posture = if owner_only && account_ok {
        IbkrSecretSlotPosture::PresentHashed
    } else {
        IbkrSecretSlotPosture::Unknown
    };

    Ok(PaperEval {
        posture,
        owner_only,
        secret_slot_fingerprint,
        account_fingerprint_hash,
    })
}

/// live 槽（覆写③e）：**永不讀內容**。任何一個 dir entry（regular/symlink/子目錄/
/// 0-byte）→ LivePresentDenied + false；真空目錄或不存在 → LiveAbsentOrEmpty + true。
///
/// 為什麼「不存在」在此可判 true：呼叫端已確認 base 存在+可枚舉（覆写③d），故「live
/// 子目錄不存在」是真 absent，而非找錯目錄。其他 I/O 錯誤（權限）→ 無法證 absent →
/// Err → denied fallback。
#[cfg(unix)]
fn eval_live_slot(dir: &Path) -> Result<(IbkrSecretSlotPosture, bool), String> {
    match std::fs::read_dir(dir) {
        Ok(mut entries) => {
            if entries.next().is_some() {
                Ok((IbkrSecretSlotPosture::LivePresentDenied, false))
            } else {
                Ok((IbkrSecretSlotPosture::LiveAbsentOrEmpty, true))
            }
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            Ok((IbkrSecretSlotPosture::LiveAbsentOrEmpty, true))
        }
        Err(e) => Err(format!("ibkr live slot read_dir {} failed: {e}", dir.display())),
    }
}

// ---------------------------------------------------------------------------
// 純 loader（四件套之一；收 base dir 參，可測繞全域）
// ---------------------------------------------------------------------------

/// 純載入器：從 `.../external/ibkr` base 讀三槽、算兩指紋、組出 contract。
///
/// 為什麼收 dir 而非讀 env：把「路徑解析」與「stat+hash+組裝」拆開，讓 tempdir 測試
/// 能確定性驗三槽 posture，繞過進程級 OnceLock 與全域 env（避免與同 binary 其他
/// env-mutating 測試搶 env → order-fragile；drawdown_revoke 教訓）。
///
/// Err vs Ok(reject) 劃分：base 不可信（祖先可寫 / symlink 槽 / 不存在 / 不可讀）→
/// **Err → 呼叫端 denied fallback**；欄位令 validate() reject（paper 缺 / 權限過寬 /
/// account_id 缺 / live present）→ **Ok(contract)**，由 validate() 統一判 reject。
#[cfg(unix)]
pub(crate) fn load_ibkr_secret_slot_contract_from_base(
    ibkr_base: &Path,
) -> Result<IbkrSecretSlotContractV1, String> {
    // 覆写③(c)+(d)：祖先 owner-only（含 base 存在性）。
    ensure_ancestor_owner_only(ibkr_base)?;

    // 覆写③(d)：base 必須可枚舉。找錯目錄/不可讀絕不能被誤證為「live 已 absent」。
    let _ = std::fs::read_dir(ibkr_base)
        .map_err(|e| format!("ibkr base read_dir {} failed: {e}", ibkr_base.display()))?;

    let readonly_dir = ibkr_base.join("readonly");
    let paper_dir = ibkr_base.join("paper");
    let live_dir = ibkr_base.join("live");

    // 覆写③(b)：三槽目錄本身不得為 symlink。
    reject_symlink_slot(&readonly_dir)?;
    reject_symlink_slot(&paper_dir)?;
    reject_symlink_slot(&live_dir)?;

    let (readonly_posture, readonly_owner_only) = eval_readonly_slot(&readonly_dir)?;
    let paper = eval_paper_slot(&paper_dir)?;
    let (live_posture, live_absent) = eval_live_slot(&live_dir)?;

    // owner_only_permissions：所有 present 槽皆須 owner-only（缺席不算違規）。
    let owner_only_permissions = readonly_owner_only && paper.owner_only;

    Ok(IbkrSecretSlotContractV1 {
        contract_id: IBKR_SECRET_SLOT_CONTRACT_ID.to_string(),
        source_version: 1,
        contract_present: true,
        readonly_slot_posture: readonly_posture,
        paper_slot_posture: paper.posture,
        live_slot_posture: live_posture,
        secret_slot_fingerprint: paper.secret_slot_fingerprint,
        account_fingerprint_hash: paper.account_fingerprint_hash,
        owner_only_permissions,
        // 以下三者為安全方向常量（不從輸入推導）：
        env_var_credential_fallback_denied: true, // 結構性永不從 env 讀憑證
        secret_content_serialized: false,          // 無欄位可容明文
        account_id_serialized: false,              // account_id 只入 hash
        live_secret_absent_or_empty: live_absent,
    })
}

/// 非 unix 平台：無法驗權限/owner → 結構性 fail-closed（覆写③ owner-only 平台前提）。
/// 部署目標為 Linux + 未來 Apple Silicon（皆 unix），此路徑實務不觸發。
#[cfg(not(unix))]
pub(crate) fn load_ibkr_secret_slot_contract_from_base(
    ibkr_base: &Path,
) -> Result<IbkrSecretSlotContractV1, String> {
    let _ = ibkr_base;
    Err(
        "ibkr secret slot loader unsupported on non-unix (permission/owner checks unavailable) \
         / 非 unix 平台不支援（無法驗權限/owner）"
            .to_string(),
    )
}

// ---------------------------------------------------------------------------
// env-resolving wrapper + OnceLock accessor + denied fallback（四件套其餘）
// ---------------------------------------------------------------------------

/// 解析 `external/ibkr` base。
///
/// 覆写①（CC 裁決）：定位機制優先讀 `OPENCLAW_SECRETS_ROOT`，否則
/// `$HOME`（Windows `$USERPROFILE`）`/BybitOpenClaw/secrets`；兩分支再 join
/// `external/ibkr`。
///
/// 為什麼**絕不**讀 `OPENCLAW_SECRETS_DIR`：那是 bybit `secret_files/bybit` 根語義，
/// 與 IBKR 的 secrets 根語義不同（AMD Secret Boundary），混用會定位錯目錄並產出
/// 假的 live-absent。跨平台：不硬編碼 `/home`、`/Users`（HOME/USERPROFILE fallback）。
fn resolve_ibkr_secrets_base() -> Option<PathBuf> {
    let base = if let Ok(root) = std::env::var("OPENCLAW_SECRETS_ROOT") {
        PathBuf::from(root)
    } else {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .ok()?;
        PathBuf::from(home).join("BybitOpenClaw").join("secrets")
    };
    Some(base.join("external").join("ibkr"))
}

/// 解析 base 後委派 pure loader（進程級 OnceLock 的載入來源）。
fn load_ibkr_secret_slot_contract() -> Result<IbkrSecretSlotContractV1, String> {
    let base = resolve_ibkr_secrets_base()
        .ok_or_else(|| "resolve ibkr secrets base failed: HOME/USERPROFILE unset".to_string())?;
    load_ibkr_secret_slot_contract_from_base(&base)
}

/// 進程級快取存取（load-once）；返回 &'static Result 供呼叫端 clone。
/// 首次載入失敗時 warn 一次（OnceLock 保證只發生一次，避免洗版）。
fn ibkr_secret_slot_contract() -> &'static Result<IbkrSecretSlotContractV1, String> {
    IBKR_SECRET_SLOT_CONTRACT.get_or_init(|| {
        let loaded = load_ibkr_secret_slot_contract();
        if let Err(e) = &loaded {
            tracing::warn!(
                error = %e,
                "ibkr secret slot contract load failed; caller uses denied fallback \
                 / IBKR secret slot 載入失敗，呼叫端回退 denied"
            );
        }
        loaded
    })
}

/// fail-closed 回退：任何路徑無法解析 / base 不可信 / symlink 時使用。
///
/// 為什麼全 Unknown + 兩指紋空 + `live_secret_absent_or_empty=false`：絕不捏造
/// accepted=true 的假 PASS；未能證明 live absent 即視為未證（fail-closed）。安全方向
/// 常量（env_var_credential_fallback_denied=true / 兩 serialized=false）照舊。
fn denied_ibkr_secret_slot_contract_fallback() -> IbkrSecretSlotContractV1 {
    IbkrSecretSlotContractV1 {
        contract_id: IBKR_SECRET_SLOT_CONTRACT_ID.to_string(),
        source_version: 1,
        contract_present: false,
        readonly_slot_posture: IbkrSecretSlotPosture::Unknown,
        paper_slot_posture: IbkrSecretSlotPosture::Unknown,
        live_slot_posture: IbkrSecretSlotPosture::Unknown,
        secret_slot_fingerprint: String::new(),
        account_fingerprint_hash: String::new(),
        owner_only_permissions: false,
        env_var_credential_fallback_denied: true,
        secret_content_serialized: false,
        account_id_serialized: false,
        live_secret_absent_or_empty: false,
    }
}

// ===========================================================================
// 測試（全 tempdir 純 loader，不動 OPENCLAW_* 全域；權限測試 #[cfg(unix)]）
// ===========================================================================

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use openclaw_types::ibkr_phase2_runtime::is_sha256_hex;
    use openclaw_types::IbkrSecretSlotContractBlocker as Blocker;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;

    /// 建 `external/ibkr` base（祖先皆 0o700），回傳 ibkr_base 路徑。
    fn make_base(root: &Path) -> PathBuf {
        let external = root.join("external");
        let ibkr = external.join("ibkr");
        fs::create_dir_all(&ibkr).unwrap();
        fs::set_permissions(&external, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&ibkr, fs::Permissions::from_mode(0o700)).unwrap();
        ibkr
    }

    /// 於 base 下建槽目錄（指定 mode），回傳槽路徑。
    fn make_slot(base: &Path, name: &str, mode: u32) -> PathBuf {
        let d = base.join(name);
        fs::create_dir_all(&d).unwrap();
        fs::set_permissions(&d, fs::Permissions::from_mode(mode)).unwrap();
        d
    }

    /// 於槽內寫 account_id（0o600, 指定內容）。
    fn write_account_id(slot: &Path, content: &str) {
        let p = slot.join(IBKR_ACCOUNT_ID_FILENAME);
        fs::write(&p, content).unwrap();
        fs::set_permissions(&p, fs::Permissions::from_mode(0o600)).unwrap();
    }

    fn sha256_hex(s: &str) -> String {
        let mut h = Sha256::new();
        h.update(s.as_bytes());
        hex::encode(h.finalize())
    }

    // --- T1: paper+readonly present + live absent → accepted ---
    #[test]
    fn t1_paper_readonly_present_live_absent_accepted() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        let paper = make_slot(&base, "paper", 0o700);
        write_account_id(&paper, "DU1234567");
        let readonly = make_slot(&base, "readonly", 0o700);
        write_account_id(&readonly, "DU7654321");
        // live 不建 → absent

        let contract = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        let verdict = contract.validate();
        assert!(verdict.accepted, "unexpected blockers: {:?}", verdict.blockers);
        assert_eq!(contract.readonly_slot_posture, IbkrSecretSlotPosture::PresentHashed);
        assert_eq!(contract.paper_slot_posture, IbkrSecretSlotPosture::PresentHashed);
        assert_eq!(contract.live_slot_posture, IbkrSecretSlotPosture::LiveAbsentOrEmpty);
        assert!(is_sha256_hex(&contract.secret_slot_fingerprint));
        assert!(is_sha256_hex(&contract.account_fingerprint_hash));
    }

    // --- T2: live 含 1 檔 → LivePresentDenied + false + reject ---
    #[test]
    fn t2_live_present_denied() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        let paper = make_slot(&base, "paper", 0o700);
        write_account_id(&paper, "DU1234567");
        let live = make_slot(&base, "live", 0o700);
        fs::write(live.join("cred"), "x").unwrap();

        let contract = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        assert_eq!(contract.live_slot_posture, IbkrSecretSlotPosture::LivePresentDenied);
        assert!(!contract.live_secret_absent_or_empty);
        let verdict = contract.validate();
        assert!(verdict.blockers.contains(&Blocker::LiveSlotPresentOrUnknown));
    }

    // --- T3: readonly absent + paper present → readonly Missing; accepted ---
    #[test]
    fn t3_readonly_absent_paper_present_accepted() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        let paper = make_slot(&base, "paper", 0o700);
        write_account_id(&paper, "DU1234567");

        let contract = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        assert_eq!(contract.readonly_slot_posture, IbkrSecretSlotPosture::Missing);
        assert!(contract.validate().accepted, "blockers: {:?}", contract.validate().blockers);
    }

    // --- T4: paper dir 0o755 → owner_only=false; 非 PresentHashed; reject ---
    #[test]
    fn t4_paper_dir_wide_perms_owner_only_false() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        let paper = make_slot(&base, "paper", 0o755);
        write_account_id(&paper, "DU1234567");

        let contract = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        assert!(!contract.owner_only_permissions);
        assert_ne!(contract.paper_slot_posture, IbkrSecretSlotPosture::PresentHashed);
        assert!(contract.validate().blockers.contains(&Blocker::OwnerOnlyPermissionsMissing));
    }

    // --- T5: paper absent → paper Missing; fingerprint=""; reject ---
    #[test]
    fn t5_paper_absent_missing() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());

        let contract = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        assert_eq!(contract.paper_slot_posture, IbkrSecretSlotPosture::Missing);
        assert_eq!(contract.secret_slot_fingerprint, "");
        assert!(contract.validate().blockers.contains(&Blocker::PaperSlotMissingOrUnhashed));
    }

    // --- T6: paper present 但無 account_id → hash=""; reject AccountFingerprintHashInvalid ---
    #[test]
    fn t6_paper_no_account_id_hash_empty() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        make_slot(&base, "paper", 0o700); // 無 account_id

        let contract = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        assert_eq!(contract.account_fingerprint_hash, "");
        assert!(contract.validate().blockers.contains(&Blocker::AccountFingerprintHashInvalid));
    }

    // --- T7: 明文零逃逸 + hash 預計算 + serialized 常量 false ---
    #[test]
    fn t7_plaintext_zero_escape_serialized() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        let paper = make_slot(&base, "paper", 0o700);
        write_account_id(&paper, "DUPLAINTEXT123");

        let contract = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        let json = serde_json::to_string(&contract).unwrap();
        assert!(!json.contains("DUPLAINTEXT123"), "serialized contract leaked plaintext: {json}");
        assert_eq!(contract.account_fingerprint_hash, sha256_hex("DUPLAINTEXT123"));
        assert!(!contract.account_id_serialized);
        assert!(!contract.secret_content_serialized);
    }

    // --- T8: normalize（P5 復用同函數得同 hash）---
    #[test]
    fn t8_account_fingerprint_normalize() {
        let a = ibkr_account_fingerprint_hash("du1234567\n");
        let b = ibkr_account_fingerprint_hash("DU1234567");
        assert_eq!(a, b);
        assert_eq!(a, sha256_hex("DU1234567"));
    }

    // --- T9: 決定性（同 fixture 連載兩次 → 兩指紋逐字相同）---
    #[test]
    fn t9_deterministic() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        let paper = make_slot(&base, "paper", 0o700);
        write_account_id(&paper, "DU1234567");
        // 額外放一檔以驗多檔排序決定性
        let extra = paper.join("ib_config");
        fs::write(&extra, "abc").unwrap();
        fs::set_permissions(&extra, fs::Permissions::from_mode(0o600)).unwrap();

        let c1 = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        let c2 = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        assert_eq!(c1.secret_slot_fingerprint, c2.secret_slot_fingerprint);
        assert_eq!(c1.account_fingerprint_hash, c2.account_fingerprint_hash);
    }

    // --- T10: paper 內含 symlink → Err → denied fallback → reject ---
    #[test]
    fn t10_paper_symlink_entry_err() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        let paper = make_slot(&base, "paper", 0o700);
        write_account_id(&paper, "DU1234567");
        std::os::unix::fs::symlink(paper.join(IBKR_ACCOUNT_ID_FILENAME), paper.join("link")).unwrap();

        assert!(load_ibkr_secret_slot_contract_from_base(&base).is_err());
        // 呼叫端回退：denied fallback 必 reject。
        assert!(!denied_ibkr_secret_slot_contract_fallback().validate().accepted);
    }

    // --- T11: denied fallback 不接受、無假 PASS ---
    #[test]
    fn t11_denied_fallback_not_accepted() {
        assert!(!denied_ibkr_secret_slot_contract_fallback().validate().accepted);
    }

    // --- E3-1: 槽目錄本身是 symlink（readonly/paper/live 各一）→ Err ---
    #[test]
    fn e3_1_slot_dir_symlink_err() {
        for slot in ["readonly", "paper", "live"] {
            let tmp = tempfile::tempdir().unwrap();
            let base = make_base(tmp.path());
            // 真實目標目錄（0o700）於 base 外，讓槽名成為指向它的 symlink。
            let real = tmp.path().join(format!("real_{slot}"));
            fs::create_dir(&real).unwrap();
            fs::set_permissions(&real, fs::Permissions::from_mode(0o700)).unwrap();
            std::os::unix::fs::symlink(&real, base.join(slot)).unwrap();

            assert!(
                load_ibkr_secret_slot_contract_from_base(&base).is_err(),
                "slot={slot} symlink dir must Err"
            );
        }
    }

    // --- E3-2: live 含 0-byte 檔 → LivePresentDenied ---
    #[test]
    fn e3_2_live_zero_byte_present() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        let live = make_slot(&base, "live", 0o700);
        fs::write(live.join("empty"), "").unwrap(); // 0-byte

        let contract = load_ibkr_secret_slot_contract_from_base(&base).unwrap();
        assert_eq!(contract.live_slot_posture, IbkrSecretSlotPosture::LivePresentDenied);
        assert!(!contract.live_secret_absent_or_empty);
    }

    // --- E3-3: live 是 symlink 指向空目錄 → Err（不 false-absent）---
    #[test]
    fn e3_3_live_symlink_to_empty_dir_err() {
        let tmp = tempfile::tempdir().unwrap();
        let base = make_base(tmp.path());
        let empty_real = tmp.path().join("empty_real");
        fs::create_dir(&empty_real).unwrap();
        fs::set_permissions(&empty_real, fs::Permissions::from_mode(0o700)).unwrap();
        std::os::unix::fs::symlink(&empty_real, base.join("live")).unwrap();

        // 絕不因 symlink 指向空目錄而誤判 live absent。
        assert!(load_ibkr_secret_slot_contract_from_base(&base).is_err());
    }

    // --- E3-4: 父目錄 group-writable(0o770) → Err（ibkr/ 與 external/ 各一）---
    #[test]
    fn e3_4_ancestor_group_writable_err() {
        // ibkr/ group-writable
        {
            let tmp = tempfile::tempdir().unwrap();
            let base = make_base(tmp.path());
            fs::set_permissions(&base, fs::Permissions::from_mode(0o770)).unwrap();
            assert!(load_ibkr_secret_slot_contract_from_base(&base).is_err());
        }
        // external/ group-writable
        {
            let tmp = tempfile::tempdir().unwrap();
            let base = make_base(tmp.path());
            fs::set_permissions(base.parent().unwrap(), fs::Permissions::from_mode(0o770)).unwrap();
            assert!(load_ibkr_secret_slot_contract_from_base(&base).is_err());
        }
    }

    // --- E3-5: base 不存在 → Err（denied fallback live_secret_absent_or_empty=false）---
    #[test]
    fn e3_5_nonexistent_base_err() {
        let tmp = tempfile::tempdir().unwrap();
        let nonexistent = tmp.path().join("external").join("ibkr"); // 不建
        assert!(load_ibkr_secret_slot_contract_from_base(&nonexistent).is_err());
        assert!(!denied_ibkr_secret_slot_contract_fallback().live_secret_absent_or_empty);
    }

    // --- E3-6: account_id 讀錯誤路徑 → error 字符串不含明文 ---
    #[test]
    fn e3_6_account_id_read_error_no_plaintext() {
        // 以 root 跑時，root 繞過 file permission → chmod 000 仍可讀 → read 成功、
        // `.unwrap_err()` 會 panic 假紅。trade-core 以非 root(ncyu) 跑不觸發，但為
        // 測試可移植性此處守衛：root 直接跳過（本測試僅驗「讀失敗時 error 不含明文」，
        // 依賴 EACCES，root 環境無此語義）。
        if unsafe { libc::geteuid() } == 0 {
            return;
        }
        let tmp = tempfile::tempdir().unwrap();
        let acct = tmp.path().join(IBKR_ACCOUNT_ID_FILENAME);
        fs::write(&acct, "SECRETLEAK999").unwrap();
        // chmod 000 → 非 root owner 也無法讀 → read 失敗（EACCES）。
        fs::set_permissions(&acct, fs::Permissions::from_mode(0o000)).unwrap();

        // 用 .err() 取 Err：ZeroizedString 刻意不 derive Debug（Debug 會印 account_id
        // 明文，破壞零明文逃逸），故不能用 .unwrap_err()（它要求 Ok 型別 Debug）。
        let err = read_account_id_zeroized(&acct).err().expect("expected read error");
        assert!(!err.contains("SECRETLEAK999"), "error string leaked plaintext: {err}");
        assert!(err.contains(IBKR_ACCOUNT_ID_FILENAME), "error should carry path: {err}");

        // 還原權限讓 tempdir 能清理。
        fs::set_permissions(&acct, fs::Permissions::from_mode(0o600)).ok();
    }

    // --- 額外：env-wrapper 解析（覆写①）；用共用 env 鎖串行 ---
    #[test]
    fn env_wrapper_resolves_secrets_root() {
        let _g = crate::test_env_lock::guard();
        let tmp = tempfile::tempdir().unwrap();
        // OPENCLAW_SECRETS_ROOT/external/ibkr 為 base。
        let base = tmp.path().join("external").join("ibkr");
        fs::create_dir_all(&base).unwrap();
        fs::set_permissions(base.parent().unwrap(), fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&base, fs::Permissions::from_mode(0o700)).unwrap();
        let paper = make_slot(&base, "paper", 0o700);
        write_account_id(&paper, "DU1234567");

        let prev_root = std::env::var("OPENCLAW_SECRETS_ROOT").ok();
        std::env::set_var("OPENCLAW_SECRETS_ROOT", tmp.path());
        // 絕不讀 OPENCLAW_SECRETS_DIR：設一個假值確認被忽略。
        let prev_dir = std::env::var("OPENCLAW_SECRETS_DIR").ok();
        std::env::set_var("OPENCLAW_SECRETS_DIR", "/nonexistent/bybit/root");

        let resolved = resolve_ibkr_secrets_base().unwrap();
        assert_eq!(resolved, base);
        let contract = load_ibkr_secret_slot_contract().unwrap();
        assert_eq!(contract.paper_slot_posture, IbkrSecretSlotPosture::PresentHashed);

        // 還原 env。
        match prev_root {
            Some(v) => std::env::set_var("OPENCLAW_SECRETS_ROOT", v),
            None => std::env::remove_var("OPENCLAW_SECRETS_ROOT"),
        }
        match prev_dir {
            Some(v) => std::env::set_var("OPENCLAW_SECRETS_DIR", v),
            None => std::env::remove_var("OPENCLAW_SECRETS_DIR"),
        }
    }
}
