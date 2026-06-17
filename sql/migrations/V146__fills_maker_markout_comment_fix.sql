-- V146: Correct the trading.fills.maker_markout_bps column COMMENT wording.
-- V146：訂正 trading.fills.maker_markout_bps 欄位 COMMENT 措辭。
--
-- 背景（為何需要本 migration）：
--   V145 的 COMMENT 寫 'Positive = adverse (informed flow)'，措辭誤導。
--   QC/PA Hybrid-C 裁決（2026-06-17）澄清：本欄量測的是 maker_markout_bps =
--   fill_price − reference_price（signed-by-side，@submit），對 close-maker
--   （reference_source='mid_at_submit'）≈ −half_spread —— 成交在 bid/ask 比 mid
--   差半個 spread，故實際符號是負（= 捕捉到的半價差，翻號為正），**這量到的是
--   spread-capture 而非 adverse selection**。真正的 fill-conditional adverse
--   selection 是 fill_sim 的 beta-residual post-fill mid 移動（離線量測），不是
--   本欄。誤導的 COMMENT 會合理化下游把 markout 當逆選擇雙重計入（recorder_mm_verdict
--   舊公式 half_spread − markout − fee 即犯此錯）。
--
--   COMMENT-only：不改 schema、不改型別、不 backfill；純訂正 governance 措辭。
--   COMMENT ON 天生冪等（double-apply no-op）。
--
--   v2 follow-up（非本 migration）：未來新增 maker_adverse_sel_bps 欄 + post-fill mid
--   tracker，可讓 net verdict 完全建立在同一批真實 fill 上（QC/PA 標 defer，非阻塞）。
--
-- 模板來源 / Template source：
--   sql/migrations/templates/schema_guard_template.sql § Guard A
-- 參考實作 / Reference implementations：
--   V145（同欄；本 migration 只訂正其 COMMENT 措辭）

-- ------------------------------------------------------------
-- Schema Guard A — verify trading.fills.maker_markout_bps exists
-- Schema Guard A — 驗證 trading.fills.maker_markout_bps 存在
-- ------------------------------------------------------------
-- Why / 為何：
--   本 migration 只對既有欄位下 COMMENT。若 V145 未套用（欄位不存在），COMMENT ON
--   會失敗於難解的「column does not exist」；Guard A 把失敗點上移到 apply 階段並給出
--   清楚指引（先套 V145）。冪等 double-apply 下亦為 no-op。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'trading'
          AND table_name   = 'fills'
          AND column_name  = 'maker_markout_bps'
    ) THEN
        RAISE EXCEPTION
            'schema_guard A: trading.fills.maker_markout_bps does not exist — '
            'V145 must be applied before V146 (V146 only corrects its COMMENT).';
    END IF;
END $$;

-- ------------------------------------------------------------
-- Body / 主體：訂正 COMMENT（spread-capture，非 adverse selection）。
-- ------------------------------------------------------------
COMMENT ON COLUMN trading.fills.maker_markout_bps IS
    'Signed maker fill markout in bps = fill_price - reference_price (signed-by-side, @submit). '
    'For close-maker (reference_source=''mid_at_submit'') this is ~ -half_spread, i.e. it measures '
    'SPREAD-CAPTURE (negate to get positive captured half-spread), NOT adverse selection. '
    'Fill-conditional adverse selection is measured offline by fill_sim (beta-residual post-fill '
    'mid move), not this column. NULL for taker/paper fills.';
