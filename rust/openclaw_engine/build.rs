//! MODULE_NOTE
//! 模塊用途：P0-1c boot/build SHA 可觀測面 —— 編譯期嵌入 git SHA 與 build 時間。
//! 主要函數：main（emit `cargo:rustc-env=OPENCLAW_BUILD_GIT_SHA` / `OPENCLAW_BUILD_TIME`）。
//! 依賴：git CLI（缺席時 fallback "unknown"，絕不使 build 失敗）、chrono（build 時間格式化）。
//! 硬邊界：僅產生編譯期常量；不觸碰任何 runtime 行為、不讀寫任何交易面資源。
//!
//! 為什麼需要：2026-07-03 冷審計 P0-1 實錘「重啟未 rebuild 無人發現」——運行中
//! binary 不攜帶自己的 git 世代，無法對表部署 HEAD。此處嵌入的 SHA 經 startup
//! banner、boot_history.jsonl、IPC `get_state` 三面暴露（見 src/boot_observability.rs）。

use std::process::Command;

/// 執行 git 子命令並回傳 trim 後的 stdout。
///
/// 為什麼 fail-soft：git 不在 PATH、非 repo、非零退出等任何失敗一律回 None，
/// build 本身絕不因 git 缺席而失敗（跨平台 / 離線 build 環境約束）。
fn git_stdout(args: &[&str]) -> Option<String> {
    let output = Command::new("git").args(args).output().ok()?;
    if !output.status.success() {
        return None;
    }
    let stdout = String::from_utf8(output.stdout).ok()?;
    let trimmed = stdout.trim().to_string();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed)
    }
}

fn main() {
    // 不變量：一旦 emit 任何 rerun-if-changed，cargo 默認「整包任何檔案變更即
    // 重跑 build.rs」的行為會被取代，故必須顯式列出全部觸發面（含 build.rs 自身）。
    println!("cargo:rerun-if-changed=build.rs");

    let sha = git_stdout(&["rev-parse", "HEAD"]).unwrap_or_else(|| "unknown".to_string());
    println!("cargo:rustc-env=OPENCLAW_BUILD_GIT_SHA={sha}");

    // build 時間：UTC RFC3339 秒級。只在 build.rs 重跑時刷新（HEAD 未變的純增量
    // 編譯不刷新，屬預期 —— 世代判準是 SHA，時間僅為輔助證據）。
    let build_time = chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true);
    println!("cargo:rustc-env=OPENCLAW_BUILD_TIME={build_time}");

    // rerun 觸發面（worktree-safe：用 `--git-path` 解析真實路徑，主樹與 linked
    // worktree 都正確）：
    //   HEAD         — 切分支 / detached HEAD
    //   當前分支 ref  — 同分支新 commit（`rev-parse HEAD` 值變化的主路徑）
    //   packed-refs  — git gc 打包後 loose ref 檔消失、值轉入 packed-refs
    for name in ["HEAD", "packed-refs"] {
        if let Some(path) = git_stdout(&["rev-parse", "--git-path", name]) {
            println!("cargo:rerun-if-changed={path}");
        }
    }
    if let Some(head_ref) = git_stdout(&["symbolic-ref", "-q", "HEAD"]) {
        if let Some(path) = git_stdout(&["rev-parse", "--git-path", &head_ref]) {
            println!("cargo:rerun-if-changed={path}");
        }
    }
}
