# Scripts Directory Classification Report

**Repository:** BybitOpenClaw  
**Directory Analyzed:** `program_code/exchange_connectors/bybit_connector/scripts/`  
**Analysis Date:** 2026-03-30  
**Total Files:** 257

---

## Executive Summary

All 257 Python files in the `scripts/` directory are either **thin wrapper scripts** (230 files) or **near-duplicate copies** (27 files) of files that exist elsewhere in the repository. **No unique files** were found.

| Category | Count | Percentage | Status |
|----------|-------|-----------|--------|
| WRAPPER | 230 | 89.5% | Safe to remove (if no external dependencies) |
| DUPLICATE_MINOR | 27 | 10.5% | Case-by-case evaluation needed |
| DUPLICATE | 0 | 0.0% | N/A |
| UNIQUE | 0 | 0.0% | N/A |

---

## Detailed Classification

### 1. WRAPPER FILES (230 files)

These are thin compatibility wrappers that use Python's `runpy.run_path()` to import and execute canonical versions from other directories.

**Typical wrapper structure:**
```python
#!/usr/bin/env python3
from pathlib import Path
import runpy
import sys

TARGET = Path(__file__).resolve().parents[3] / "path_to_canonical" / "module_name.py"

if __name__ == "__main__":
    sys.path.insert(0, str(TARGET.parent))
    runpy.run_path(str(TARGET), run_name="__main__")
```

**Distribution by canonical location:**

| Canonical Location | Count |
|--------------------|-------|
| `program_code/ai_agents/bybit_thought_gate/` | 55 |
| `program_code/trading_strategy/bybit_event_driven/` | 52 |
| `program_code/trade_executor/bybit_decision_lease/` | 44 |
| `program_code/exchange_connectors/bybit_connector/misc_tools/` | 21 |
| `program_code/risk_control/bybit_local_models_and_risk/` | 20 |
| `program_code/exchange_connectors/bybit_connector/io_and_persistence/` | 18 |
| `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/` | 17 |
| `helper_scripts/maintenance_scripts/bybit_connector/` | 3 |

**Status:** These files can safely be removed IF no external code references the `scripts/` paths.

---

### 2. DUPLICATE_MINOR FILES (27 files)

These are near-identical copies with minor differences (typically 106-281 lines of diff).

**Distribution by canonical location:**

| Canonical Location | Count |
|--------------------|-------|
| `program_code/market_data_processor/bybit_business_events/` | 26 |
| `program_code/exchange_connectors/bybit_connector/misc_tools/` | 1 |

**Examples with diff sizes:**
- `bybit_business_event_acceptance_contract_check.py` → 106 lines diff
- `bybit_business_event_acceptance_suite.py` → 281 lines diff
- `bybit_business_event_contract_check.py` → 138 lines diff
- `bybit_business_event_extract_from_ws_jsonl.py` → 136 lines diff

**Status:** Requires review to determine if the canonical versions are sufficient or if `scripts/` versions have necessary customizations.

---

## Output Files

Three machine-readable classification files have been generated:

### 1. `scripts_classification.txt` (Pipe-delimited)
```
CATEGORY|SCRIPTS_PATH|CANONICAL_PATH[|DIFF_LINES]
```
Example:
```
WRAPPER|program_code/.../scripts/bybit_ai_cost_log.py|program_code/.../bybit_ai_cost_log.py
DUPLICATE_MINOR_DIFF|program_code/.../scripts/bybit_business_event_acceptance_contract_check.py|program_code/.../bybit_business_event_acceptance_contract_check.py|106
```

### 2. `scripts_classification.csv` (CSV format)
Excel/spreadsheet compatible format with columns:
- CATEGORY
- SCRIPTS_FILE
- CANONICAL_FILE
- DIFF_LINES

### 3. `scripts_classification.json` (JSON format)
Structured JSON with metadata, summary, and detailed file entries.

---

## Key Findings

### Finding 1: Scripts Directory is 100% Derived
Every single file in `scripts/` has a counterpart elsewhere in the repository. This suggests the directory was created as a compatibility layer or convenience collection.

### Finding 2: Wrapper Pattern Dominates
89.5% of files follow the thin wrapper pattern using `runpy.run_path()`. These are straightforward to remove once dependencies are verified.

### Finding 3: Market Data Processor Duplicates
26 of the 27 non-wrapper files are duplicates of market data processor business event files, likely with path/import adjustments for the scripts context.

### Finding 4: Minimal Content Divergence
DUPLICATE_MINOR files have relatively small diffs (100-300 lines), suggesting they're mostly the same code with minor context-specific adjustments.

---

## Recommendations

### Phase 1: Dependency Analysis (CRITICAL)
Before any cleanup, verify:

1. **Search for direct script references:**
   - `grep -r "scripts/" .` in the entire repo
   - Check for hardcoded paths in configuration files
   - Search imports like `from program_code.exchange_connectors.bybit_connector.scripts`

2. **Check build systems and CI/CD:**
   - Verify no Makefiles, build scripts, or CI/CD configs reference `scripts/` paths
   - Check Docker configurations
   - Search deployment scripts

3. **Check CLI entry points:**
   - Verify no command-line tools point directly to scripts
   - Check setup.py/pyproject.toml for entry points

### Phase 2: Remove Wrapper Files (230 files)

Once dependencies are verified:

```bash
# Backup first
cp -r program_code/exchange_connectors/bybit_connector/scripts \
      program_code/exchange_connectors/bybit_connector/scripts.backup

# Remove wrapper files
find program_code/exchange_connectors/bybit_connector/scripts \
  -type f -name "*.py" -exec grep -l "runpy\|run_path" {} \; \
  | xargs rm

# Verify cleanup
ls -la program_code/exchange_connectors/bybit_connector/scripts/
```

**Expected result:** 27 files remaining (the DUPLICATE_MINOR ones)

### Phase 3: Evaluate Duplicate-Minor Files (27 files)

Review each remaining file:
1. Compare with canonical version
2. Check if differences are necessary for the context
3. Either remove (use canonical) or document why custom version is needed

### Phase 4: Update References

Update all code and documentation that references `scripts/` paths to point to canonical locations.

---

## Usage Examples

### Parse the classification in Python:
```python
import csv

with open('scripts_classification.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['CATEGORY'] == 'WRAPPER':
            print(f"Remove: {row['SCRIPTS_FILE']}")
```

### Parse the classification in JSON:
```python
import json

with open('scripts_classification.json', 'r') as f:
    data = json.load(f)
    print(f"Total files: {data['metadata']['total_files']}")
    print(f"Wrappers: {data['summary']['WRAPPER']}")
```

### Filter only UNIQUE files (none):
```bash
grep "^UNIQUE" scripts_classification.txt
```

### Extract all wrapper canonical locations:
```bash
grep "^WRAPPER" scripts_classification.txt | awk -F'|' '{print $3}' | sort -u
```

---

## Technical Notes

### Classification Methodology

1. **Search for same-named files** in `program_code/` and `helper_scripts/`
2. **Detect wrappers** by checking:
   - File size < 30 lines
   - Contains `runpy`, `run_path`, or `__main__`
   - Imports `sys` and uses `runpy.run_path()` pattern
3. **Compare content** using `cmp` for binary equality
4. **Calculate diff size** for near-duplicates

### Canonical Location Priority

The analysis first checks for canonical files in `program_code/`, then in `helper_scripts/`. Canonical locations identified:

- `program_code/ai_agents/`
- `program_code/trading_strategy/`
- `program_code/trade_executor/`
- `program_code/market_data_processor/`
- `program_code/risk_control/`
- `program_code/exchange_connectors/` (subdirectories)
- `helper_scripts/maintenance_scripts/`

---

## Conclusion

The `scripts/` directory appears to be a compatibility/convenience collection serving as a centralized access point for files scattered across multiple modules. It contains no original code and can be safely removed after verifying no external dependencies reference it.

Recommended action: Proceed with Phase 1 (dependency analysis) before cleanup.

