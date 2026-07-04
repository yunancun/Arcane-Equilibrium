//! MODULE_NOTE
//! 模塊用途：probe_ledger.jsonl 的 rotation / retention 引擎側實作（P1-10，
//!   operator D9 裁定：主檔達 50MB 輪轉為 `probe_ledger.<UTCts>Z.jsonl` 段檔，
//!   段檔保留 14 天）。與 Python 側 `cost_gate_learning_lane/ledger_rotation.py`
//!   共用同一段名契約與同一把輪轉鎖，兩側寫者互認段檔、互斥輪轉。
//! 主要函數：maybe_rotate_ledger（append 前輪轉+清理入口）、retained_ledger_paths
//!   （retention 窗內讀取視圖，供 writer cache 全量重讀跨段）。
//! 依賴：std + libc::flock（Unix 檔案系統 advisory lock）。部署目標為 Linux
//!   runtime 與未來 Apple Silicon，兩者皆 Unix，flock 可用。
//!
//! 硬邊界（並發安全論證）：
//!   - 輪轉 = flock 互斥下的 `rename`。rename 在同一檔案系統內原子且不改被移動
//!     檔的 inode：持有舊 append fd 的寫者（本 writer task 的 BufWriter /
//!     Python open("a")）續寫舊段不丟行，之後按路徑重開的寫者落在新主檔。
//!   - flock 的鎖檔 = `<ledger>.rotate.lock`，與 Python 側逐字相同。跨語言
//!     flock(2) 對同一 inode 互斥，故「引擎輪轉」與「Python lane 輪轉」不會
//!     double-rotate，也不會兩側同時挑到同一段名 rename 互相覆蓋（段名撞名
//!     race 被鎖收口，非靠 TOCTOU 僥倖）。
//!   - 進程崩潰時 flock 隨 fd 關閉由 kernel 自動釋放，不留永久卡死輪轉的殘鎖。
//!   - retention 只刪除嚴格匹配 `<stem>.<UTCts>Z(_seq)?.jsonl` 的段檔，永不觸碰
//!     lane 目錄下其他 artifact；讀取視圖按檔名時間戳排除過期段，語義與磁盤
//!     清理時點解耦（段檔未被及時 unlink 也不回到視圖）。

use std::fs;
use std::io;
use std::os::unix::io::AsRawFd;
use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};

// P1-10 / D9 裁定值：50MB 輪轉閾值 + 14d retention。生產側不提供 env 旋鈕
// （避免假參數）；測試以顯式參數注入小閾值。
pub(crate) const ROTATE_THRESHOLD_BYTES: u64 = 50 * 1024 * 1024;
pub(crate) const RETENTION_DAYS: i64 = 14;

const JSONL_SUFFIX: &str = ".jsonl";

/// 段名時間戳格式：YYYYMMDDTHHMMSSZ（與 Python `_TS_FORMAT` 逐字一致）。
fn format_segment_ts(now: DateTime<Utc>) -> String {
    // chrono %Y%m%dT%H%M%SZ 等價；用 strftime 保證與 Python strptime 契約對齊。
    now.format("%Y%m%dT%H%M%SZ").to_string()
}

fn ledger_stem(ledger_path: &Path) -> String {
    let name = ledger_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or_default();
    match name.strip_suffix(JSONL_SUFFIX) {
        Some(stem) => stem.to_string(),
        None => name.to_string(),
    }
}

/// 解析段檔名 → (時間戳字串, 序號)。非匹配段名回 None。
/// 契約：`<stem>.<8位日期>T<6位時間>Z(_<seq>)?.jsonl`。
fn parse_segment_name(stem: &str, name: &str) -> Option<(String, u64)> {
    let rest = name.strip_prefix(stem)?.strip_prefix('.')?;
    let body = rest.strip_suffix(JSONL_SUFFIX)?;
    // body = "<8>T<6>Z" 或 "<8>T<6>Z_<seq>"
    let (ts_part, seq) = match body.split_once('_') {
        Some((ts, seq_text)) => (ts, seq_text.parse::<u64>().ok()?),
        None => (body, 0u64),
    };
    // ts_part 必為 15 字元：8 位日期 + 'T' + 6 位時間 + 'Z'。
    let bytes = ts_part.as_bytes();
    if bytes.len() != 16
        || bytes[8] != b'T'
        || bytes[15] != b'Z'
        || !bytes[..8].iter().all(u8::is_ascii_digit)
        || !bytes[9..15].iter().all(u8::is_ascii_digit)
    {
        return None;
    }
    Some((ts_part.to_string(), seq))
}

fn parse_segment_ts(ts_text: &str) -> Option<DateTime<Utc>> {
    let naive = chrono::NaiveDateTime::parse_from_str(ts_text, "%Y%m%dT%H%M%SZ").ok()?;
    Some(DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc))
}

/// 枚舉 lane 目錄下全部匹配段檔，回 (ts_text, seq, path)。
fn iter_segments(ledger_path: &Path) -> Vec<(String, u64, PathBuf)> {
    let dir = match ledger_path.parent() {
        Some(dir) => dir,
        None => return Vec::new(),
    };
    let stem = ledger_stem(ledger_path);
    let read_dir = match fs::read_dir(dir) {
        Ok(rd) => rd,
        Err(_) => return Vec::new(),
    };
    let mut out = Vec::new();
    for entry in read_dir.flatten() {
        let name = entry.file_name();
        let name = match name.to_str() {
            Some(n) => n,
            None => continue,
        };
        if let Some((ts_text, seq)) = parse_segment_name(&stem, name) {
            out.push((ts_text, seq, dir.join(name)));
        }
    }
    out.sort_by(|a, b| (a.0.as_str(), a.1).cmp(&(b.0.as_str(), b.1)));
    out
}

/// 讀取視圖：retention 窗內段檔（升冪）+ 主檔（若存在）。
/// 為什麼按檔名時間戳而非 mtime：段檔時間戳=輪轉時刻，是兩側寫者共同的確定性
/// 契約；mtime 會被 touch / 備份工具漂移。
pub(crate) fn retained_ledger_paths(ledger_path: &Path) -> Vec<PathBuf> {
    retained_ledger_paths_at(ledger_path, RETENTION_DAYS, Utc::now())
}

pub(crate) fn retained_ledger_paths_at(
    ledger_path: &Path,
    retention_days: i64,
    now: DateTime<Utc>,
) -> Vec<PathBuf> {
    let cutoff = now - chrono::Duration::days(retention_days);
    let mut out = Vec::new();
    for (ts_text, _seq, path) in iter_segments(ledger_path) {
        match parse_segment_ts(&ts_text) {
            Some(parsed) if parsed >= cutoff => out.push(path),
            _ => {}
        }
    }
    if ledger_path.exists() {
        out.push(ledger_path.to_path_buf());
    }
    out
}

fn rotation_lock_path(ledger_path: &Path) -> PathBuf {
    let name = ledger_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or_default();
    ledger_path.with_file_name(format!("{name}.rotate.lock"))
}

/// flock(LOCK_EX) 互斥 guard。持鎖時間僅覆蓋 re-stat + rename + retention 清理。
/// Drop 時解鎖並關 fd（進程崩潰時 kernel 亦自動釋放，無殘鎖）。
struct RotationLock {
    file: fs::File,
}

impl RotationLock {
    fn acquire(lock_path: &Path) -> io::Result<Self> {
        if let Some(parent) = lock_path.parent() {
            fs::create_dir_all(parent)?;
        }
        let file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(lock_path)?;
        // flock(2) 阻塞式 LOCK_EX：與 Python fcntl.flock(LOCK_EX) 對同一 inode
        // 互斥。EINTR 重試。
        loop {
            let ret = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) };
            if ret == 0 {
                break;
            }
            let err = io::Error::last_os_error();
            if err.raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            return Err(err);
        }
        Ok(Self { file })
    }
}

impl Drop for RotationLock {
    fn drop(&mut self) {
        // 顯式解鎖（fd 關閉也會釋放，這裡明確化語義）。失敗無可挽回，忽略。
        unsafe {
            libc::flock(self.file.as_raw_fd(), libc::LOCK_UN);
        }
    }
}

/// 挑選下一個不存在的段檔路徑（同秒撞名 → bump `_seq`）。鎖內調用，路徑判定
/// 期間不會被另一側輪轉者插隊。
fn next_segment_path(ledger_path: &Path, ts_text: &str) -> PathBuf {
    let stem = ledger_stem(ledger_path);
    let mut candidate = ledger_path.with_file_name(format!("{stem}.{ts_text}{JSONL_SUFFIX}"));
    let mut seq = 0u64;
    while candidate.exists() {
        seq += 1;
        candidate = ledger_path.with_file_name(format!("{stem}.{ts_text}_{seq}{JSONL_SUFFIX}"));
    }
    candidate
}

fn sweep_expired_segments(ledger_path: &Path, retention_days: i64, now: DateTime<Utc>) -> u64 {
    let cutoff = now - chrono::Duration::days(retention_days);
    let mut deleted = 0u64;
    for (ts_text, _seq, path) in iter_segments(ledger_path) {
        match parse_segment_ts(&ts_text) {
            Some(parsed) if parsed >= cutoff => continue,
            None => continue,
            _ => {}
        }
        match fs::remove_file(&path) {
            Ok(()) => deleted += 1,
            // 另一側輪轉者剛清掉同一過期段，冪等跳過。
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(_) => {}
        }
    }
    deleted
}

/// 輪轉結果摘要。`rotated=true` 代表主檔已被 rename 走，呼叫端須重開 append fd。
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub(crate) struct RotationOutcome {
    pub(crate) rotated: bool,
    pub(crate) segment_path: Option<PathBuf>,
    pub(crate) expired_deleted: u64,
}

/// append 前調用：主檔達閾值即在 flock 互斥下輪轉，並在同一把鎖下做 retention
/// 清理。fast path 只做一次 stat（不掃目錄、不取鎖），per-append 開銷可忽略；
/// retention 掃描只在真正輪轉時發生。
pub(crate) fn maybe_rotate_ledger(
    ledger_path: &Path,
    threshold_bytes: u64,
    retention_days: i64,
    now: DateTime<Utc>,
) -> RotationOutcome {
    let size = match fs::metadata(ledger_path) {
        Ok(meta) => meta.len(),
        // 檔案不存在 = 尚未寫過，no-op。
        Err(_) => return RotationOutcome::default(),
    };
    if size < threshold_bytes {
        return RotationOutcome::default();
    }
    let lock = match RotationLock::acquire(&rotation_lock_path(ledger_path)) {
        Ok(lock) => lock,
        // 取鎖失敗（權限/fs 異常）：放棄本次輪轉，下次 append 再試。不 panic：
        // ledger 持續成長是可觀測缺陷，但阻斷 append（丟學習證據）更糟。
        Err(_) => return RotationOutcome::default(),
    };
    // 鎖下複核：並發輪轉者可能剛把主檔轉走（路徑上是新的小主檔或不存在）。
    let size = match fs::metadata(ledger_path) {
        Ok(meta) => meta.len(),
        Err(_) => return RotationOutcome::default(),
    };
    if size < threshold_bytes {
        return RotationOutcome::default();
    }
    let ts_text = format_segment_ts(now);
    let target = next_segment_path(ledger_path, &ts_text);
    if fs::rename(ledger_path, &target).is_err() {
        // rename 失敗（罕見：跨 fs / 權限）：放棄，主檔留原地下次再試。
        return RotationOutcome::default();
    }
    let expired_deleted = sweep_expired_segments(ledger_path, retention_days, now);
    drop(lock);
    RotationOutcome {
        rotated: true,
        segment_path: Some(target),
        expired_deleted,
    }
}

/// 段檔枚舉（升冪），供 writer 整合測試檢視輪轉是否發生。
#[cfg(test)]
pub(crate) fn rotated_segment_paths_for_test(ledger_path: &Path) -> Vec<PathBuf> {
    iter_segments(ledger_path)
        .into_iter()
        .map(|(_, _, path)| path)
        .collect()
}

/// 供 writer 判定「持有的 append fd 是否仍指向當前主檔」：以 (dev, ino) 比對。
/// rotation 後主檔 inode 變化，writer 據此重開 fd。
pub(crate) fn ledger_identity(ledger_path: &Path) -> Option<(u64, u64)> {
    use std::os::unix::fs::MetadataExt;
    fs::metadata(ledger_path)
        .ok()
        .map(|meta| (meta.dev(), meta.ino()))
}

/// 便利：以生產閾值/retention + 當前 UTC 輪轉（writer append 前調用）。
pub(crate) fn maybe_rotate_ledger_default(ledger_path: &Path) -> RotationOutcome {
    maybe_rotate_ledger(
        ledger_path,
        ROTATE_THRESHOLD_BYTES,
        RETENTION_DAYS,
        Utc::now(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::TempDir;

    fn now_fixed() -> DateTime<Utc> {
        DateTime::parse_from_rfc3339("2026-07-04T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc)
    }

    fn write_rows(path: &Path, keys: &[&str]) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        let mut file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .unwrap();
        for key in keys {
            writeln!(file, "{{\"attempt_id\":\"{key}\"}}").unwrap();
        }
    }

    #[test]
    fn below_threshold_is_noop() {
        let tmp = TempDir::new().unwrap();
        let ledger = tmp.path().join("probe_ledger.jsonl");
        write_rows(&ledger, &["a1"]);
        let outcome = maybe_rotate_ledger(&ledger, 10_000, RETENTION_DAYS, now_fixed());
        assert!(!outcome.rotated);
        assert!(ledger.exists());
    }

    #[test]
    fn missing_ledger_is_noop() {
        let tmp = TempDir::new().unwrap();
        let ledger = tmp.path().join("probe_ledger.jsonl");
        let outcome = maybe_rotate_ledger(&ledger, 1, RETENTION_DAYS, now_fixed());
        assert_eq!(outcome, RotationOutcome::default());
    }

    #[test]
    fn rotation_triggers_and_preserves_rows() {
        let tmp = TempDir::new().unwrap();
        let ledger = tmp.path().join("probe_ledger.jsonl");
        write_rows(&ledger, &["a1", "a2"]);
        let outcome = maybe_rotate_ledger(&ledger, 1, RETENTION_DAYS, now_fixed());
        assert!(outcome.rotated);
        let segment = outcome.segment_path.clone().unwrap();
        assert_eq!(
            segment.file_name().unwrap().to_str().unwrap(),
            "probe_ledger.20260704T120000Z.jsonl"
        );
        assert!(!ledger.exists());
        // 段檔內容 = 輪轉前主檔全部行。
        let content = fs::read_to_string(&segment).unwrap();
        assert_eq!(
            content.lines().collect::<Vec<_>>(),
            vec!["{\"attempt_id\":\"a1\"}", "{\"attempt_id\":\"a2\"}"]
        );
        // 主檔缺席時再呼叫 = no-op。
        assert!(!maybe_rotate_ledger(&ledger, 1, RETENTION_DAYS, now_fixed()).rotated);
    }

    #[test]
    fn segment_name_collision_bumps_seq() {
        let tmp = TempDir::new().unwrap();
        let ledger = tmp.path().join("probe_ledger.jsonl");
        write_rows(&ledger, &["a1"]);
        let first = maybe_rotate_ledger(&ledger, 1, RETENTION_DAYS, now_fixed());
        write_rows(&ledger, &["a2"]);
        let second = maybe_rotate_ledger(&ledger, 1, RETENTION_DAYS, now_fixed());
        assert_eq!(
            first
                .segment_path
                .unwrap()
                .file_name()
                .unwrap()
                .to_str()
                .unwrap(),
            "probe_ledger.20260704T120000Z.jsonl"
        );
        assert_eq!(
            second
                .segment_path
                .unwrap()
                .file_name()
                .unwrap()
                .to_str()
                .unwrap(),
            "probe_ledger.20260704T120000Z_1.jsonl"
        );
    }

    #[test]
    fn retention_sweep_deletes_only_expired_segments() {
        let tmp = TempDir::new().unwrap();
        let ledger = tmp.path().join("probe_ledger.jsonl");
        // 33 天前（過期）與 3 天前（保留）。
        let expired = tmp.path().join("probe_ledger.20260601T000000Z.jsonl");
        let fresh = tmp.path().join("probe_ledger.20260701T000000Z.jsonl");
        let unrelated = tmp
            .path()
            .join("sealed_horizon_evidence_20260601T000000Z.jsonl");
        let malformed = tmp.path().join("probe_ledger.not-a-ts.jsonl");
        for p in [&expired, &fresh, &unrelated, &malformed] {
            write_rows(p, &["x"]);
        }
        write_rows(&ledger, &["a1"]);
        let outcome = maybe_rotate_ledger(&ledger, 1, 14, now_fixed());
        assert!(outcome.rotated);
        assert_eq!(outcome.expired_deleted, 1);
        assert!(!expired.exists());
        // 未過期段、無關檔案、不匹配段名契約者一律不動。
        assert!(fresh.exists());
        assert!(unrelated.exists());
        assert!(malformed.exists());
    }

    #[test]
    fn retained_view_excludes_expired_even_if_not_deleted() {
        let tmp = TempDir::new().unwrap();
        let ledger = tmp.path().join("probe_ledger.jsonl");
        let expired = tmp.path().join("probe_ledger.20260601T000000Z.jsonl");
        let fresh = tmp.path().join("probe_ledger.20260701T000000Z.jsonl");
        write_rows(&expired, &["old"]);
        write_rows(&fresh, &["mid"]);
        write_rows(&ledger, &["new"]);
        let files = retained_ledger_paths_at(&ledger, 14, now_fixed());
        assert_eq!(files, vec![fresh, ledger]);
    }

    #[test]
    fn ledger_identity_changes_after_rotation() {
        let tmp = TempDir::new().unwrap();
        let ledger = tmp.path().join("probe_ledger.jsonl");
        write_rows(&ledger, &["a1", "a2"]);
        let before = ledger_identity(&ledger);
        assert!(before.is_some());
        maybe_rotate_ledger(&ledger, 1, RETENTION_DAYS, now_fixed());
        // 主檔已被轉走 → 身份消失（新主檔尚未建立）。
        assert!(ledger_identity(&ledger).is_none());
        write_rows(&ledger, &["b1"]);
        let after = ledger_identity(&ledger);
        assert!(after.is_some());
        assert_ne!(before, after);
    }
}
