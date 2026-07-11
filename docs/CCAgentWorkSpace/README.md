# CCAgentWorkSpace — generated role views and history

Development-agent authority is `.codex/agent_registry_v1.json`. Each role is a
capability preset over Conductor / Investigator / Builder / Verifier, not an
independent fictional persona.

## Directory meaning

- `*/profile.md`: generated Adapter view; never edit directly.
- `*/memory.md`: historical durable lessons, loaded only when the task points to
  relevant history. It is not current state or a completion target.
- `*/workspace/reports/`: retained historical evidence. New delegated work does
  not automatically read or append it.
- `Operator/`: historical operator projections; not a second authority.

Current state lives in `TODO.md`. A delegated role receives a Context Interface
capsule, returns one immutable fragment, and does not write memory/report by
default. PM merges fragments into `closure_packet_v1`; `report_sink_v1` may
produce one deterministic task projection after validation.

Regenerate all profile views with:

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py render
```

## Capability presets

| Preset | Primary capability |
|---|---|
| PM | Conductor, routing and closure |
| PA / FA | architecture and functional investigation |
| E1 / E1a | backend or Vanilla frontend implementation |
| E2 / E3 / E4 / E5 | adversarial, security, regression and performance verification |
| CC | typed authority and hard-boundary verification |
| BB / IB | Bybit or IBKR Broker Compatibility Adapter review |
| OPS | read-only operations preflight/postcheck/RCA |
| QC / MIT / AI-E | quant, data/ML and AI-economics verification |
| A3 / QA / R4 | UX, end-to-end and documentation verification |
| TW | task-scoped documentation projection |

Routing is a hybrid risk-DAG. Source implementation keeps the independent
E2→E4 hard edge; other presets activate from task facts. Skips retain reason and
residual risk. No preset gains deploy, broker contact, PG-write, Linux-cargo or
order authority from this directory.
