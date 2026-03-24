#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

files=(
  scripts/bybit_ai_cost_log.py
  scripts/bybit_query_budget_policy.py
  scripts/bybit_local_trigger_model_builder.py
  scripts/bybit_thought_gate_input_builder.py
  scripts/bybit_thought_gate_policy_builder.py
)

echo "===== BACKUP ====="
for f in "${files[@]}"; do
  cp "$f" "$f.bak_repair_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== FIX HELPER IMPORT ORDER ====="
for f in "${files[@]}"; do
  helper="$(grep -E '^from bybit_mainline_cleanup_helpers import ' "$f" || true)"
  if grep -q '^from __future__ import annotations$' "$f" && [ -n "$helper" ]; then
    awk -v helper="$helper" '
      $0 == helper { next }
      {
        print
        if ($0 == "from __future__ import annotations") {
          print helper
        }
      }
    ' "$f" > "$f.tmp"
    mv "$f.tmp" "$f"
    echo "fixed_import_order: $f"
  else
    echo "skipped_import_order: $f"
  fi
done

echo
echo "===== REPAIR LOCAL_TRIGGER PRUNE POSITION ====="
f="scripts/bybit_local_trigger_model_builder.py"

# 先删掉所有错误位置的 prune 语句
sed -i '/^[[:space:]]*warning_flags = prune_freshness_warning_flags(locals(), warning_flags)[[:space:]]*$/d' "$f"

# 找 warning_flags 这个 dict key 所在行
key_ln="$(grep -n '^[[:space:]]*"warning_flags": warning_flags,' "$f" | tail -n 1 | cut -d: -f1)"
if [ -z "${key_ln:-}" ]; then
  echo "KEY_LINE_NOT_FOUND"
  exit 1
fi

# 在它前面向上找最近一个“4空格缩进 + 以 { 结尾”的顶层 dict 起点
anchor_ln="$(awk -v key="$key_ln" '
  NR < key {
    if ($0 ~ /^    / && $0 !~ /^        / && $0 ~ /\{$/) {
      ln = NR
    }
  }
  END { print ln+0 }
' "$f")"

if [ "$anchor_ln" -eq 0 ]; then
  echo "ANCHOR_LINE_NOT_FOUND"
  exit 1
fi

# 在顶层 dict 起点前插入 prune
sed -i "${anchor_ln}i\\
    warning_flags = prune_freshness_warning_flags(locals(), warning_flags)\\
" "$f"

echo "key_ln=$key_ln"
echo "anchor_ln=$anchor_ln"

echo
echo "===== VERIFY LOCAL_TRIGGER HEAD ====="
nl -ba "$f" | sed -n '1,45p'

echo
echo "===== VERIFY LOCAL_TRIGGER FRESHNESS BLOCK ====="
nl -ba "$f" | sed -n '358,372p'

echo
echo "===== VERIFY LOCAL_TRIGGER REPORT BLOCK ====="
nl -ba "$f" | sed -n "$((anchor_ln-2)),$((anchor_ln+6))p"
nl -ba "$f" | sed -n '488,505p'

echo
echo "===== PY_COMPILE RECHECK ====="
python3 -m py_compile \
  scripts/bybit_mainline_cleanup_helpers.py \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_query_budget_policy.py \
  scripts/bybit_local_trigger_model_builder.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py
