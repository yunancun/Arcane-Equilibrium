# Repository Inventory Summary

Created: 2026-04-28

## Totals

- Git-visible files: 2076
- Non-test/context-or-review files: 1821
- In-scope code/config/schema/script files: 844
- Context files: 977
- Excluded files: 255

## Review Scope

- context: 977
- excluded: 255
- in_scope: 844

## In-Scope Categories

- deployment_configuration: 55
- migration_schema: 28
- operator_script: 65
- runtime_code: 696

## In-Scope Reasons

- database_schema_or_migration: 28
- dependency_requirements: 2
- docker_or_service_config: 2
- operator_or_maintenance_script: 65
- program_code: 2
- program_code_ai_agents: 55
- program_code_exchange_connectors: 247
- program_code_local_model_tools: 27
- program_code_market_data_processor: 26
- program_code_ml_training: 26
- runtime_or_repo_config: 51
- rust_runtime: 313

## In-Scope Risk Buckets

- P0_candidate: 442
- P1_candidate: 107
- P2_candidate: 295

## Exclusion Reasons

- archived_agent_artifact: 1
- archived_documentation: 33
- backup_or_binary_archive: 1
- generated_or_build_artifact: 1
- test_or_test_support: 219

## Top-Level File Counts

- .claude: 42
- .claude.json: 1
- .codex: 29
- .gitignore: 1
- CLAUDE.md: 1
- OPENCLAW_INVENTORY_CONSOLIDATED.md: 1
- README.md: 1
- SKILLS_TODO.md: 1
- TODO.md: 1
- backup_files: 1
- backups: 1
- budget_config.toml: 1
- docker: 1
- docker_projects: 22
- docs: 786
- engine.toml: 1
- helper_scripts: 77
- memory: 71
- program_code: 600
- requirements-ml.txt: 1
- research_notes: 1
- rust: 374
- scripts: 1
- settings: 26
- sql: 32
- stored_data: 1
- venvs: 1

## File Extensions

- .md: 943
- .py: 533
- .rs: 359
- .txt: 42
- .sh: 35
- .sql: 33
- .json: 27
- .docx: 22
- .html: 21
- .toml: 17
- .js: 10
- .yml: 7
- .onnx: 6
- [none]: 5
- .plist: 4
- .tsv: 3
- .lock: 2
- .yaml: 2
- .css: 1
- .dump: 1
- .example: 1
- .legacy: 1
- .pdf: 1

## Worktree Status

- clean: 2068
- modified: 1
- untracked: 7

## Generated Files

- `docs/audit/inventory_manifest.tsv`: all Git-visible files with classification.
- `docs/audit/non_test_manifest.tsv`: non-excluded audit inventory.
- `docs/audit/excluded_manifest.tsv`: files excluded from code audit, including tests and build/archive outputs.

## Classification Caveats

- Classification is path- and extension-based. It is suitable for audit planning, not a security conclusion.
- `P0_candidate` means the path name indicates live trading, exchange, order, fill, position, risk, or secret relevance. It does not imply a confirmed bug.
- Documentation and historical audit files are marked as context unless they are current audit artifacts.
- Secrets are not opened in this inventory pass.
