#!/usr/bin/env bash
set -euo pipefail

BASE="/home/ncyu/srv/program_code/exchange_connectors/bybit_connector"
RUN="$BASE/scripts/run_with_trading_env.sh"

cd "$BASE"

$RUN python3 scripts/bybit_public_microstructure_builder.py
$RUN python3 scripts/bybit_public_microstructure_contract_check.py

$RUN python3 scripts/bybit_local_market_friction_builder.py
$RUN python3 scripts/bybit_local_market_friction_contract_check.py

$RUN python3 scripts/bybit_local_risk_envelope_gate.py
$RUN python3 scripts/bybit_local_risk_envelope_contract_check.py

$RUN python3 scripts/bybit_local_trade_eligibility_builder.py
$RUN python3 scripts/bybit_local_trade_eligibility_contract_check.py

$RUN python3 scripts/bybit_local_trade_eligibility_handoff_builder.py
$RUN python3 scripts/bybit_local_trade_eligibility_handoff_contract_check.py

$RUN python3 scripts/bybit_local_judgment_final_audit.py
$RUN python3 scripts/bybit_local_judgment_final_audit_contract_check.py

$RUN python3 scripts/bybit_thought_gate_input_builder.py
$RUN python3 scripts/bybit_thought_gate_input_contract_check.py

$RUN python3 scripts/bybit_thought_gate_policy_builder.py
$RUN python3 scripts/bybit_thought_gate_policy_contract_check.py

$RUN python3 scripts/bybit_local_trigger_model_builder.py
$RUN python3 scripts/bybit_local_trigger_model_contract_check.py

$RUN python3 scripts/bybit_thought_gate_decision_builder.py
$RUN python3 scripts/bybit_thought_gate_decision_contract_check.py

$RUN python3 scripts/bybit_ai_prompt_prep_builder.py
$RUN python3 scripts/bybit_ai_prompt_prep_contract_check.py

$RUN python3 scripts/bybit_ai_request_envelope_builder.py
$RUN python3 scripts/bybit_ai_request_envelope_contract_check.py

$RUN python3 scripts/bybit_ai_invocation_attempt_builder.py
$RUN python3 scripts/bybit_ai_invocation_attempt_contract_check.py
