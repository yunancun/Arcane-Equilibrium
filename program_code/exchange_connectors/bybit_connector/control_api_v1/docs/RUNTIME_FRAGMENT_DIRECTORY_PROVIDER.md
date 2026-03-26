# Runtime Fragment Directory Provider

## Purpose

This provider lets the runtime snapshot generator read normalized fragments from a standard directory instead of requiring three explicit file paths.

## Expected files

Inside the input directory:

- `runtime_status.json` (required)
- `product_family_facts.json` (required)
- `health_telemetry.json` (optional)

## Generate a snapshot from a directory

```bash
python3 scripts/generate_runtime_snapshot_from_directory.py \
  --input-dir examples/runtime_fragments_directory_example \
  --output /tmp/runtime_snapshot.generated.json
```

## Validate the generated snapshot

```bash
python3 scripts/validate_runtime_snapshot.py /tmp/runtime_snapshot.generated.json
```

## Why this matters

This is the bridge from:

- hand-written `/tmp/runtime_snapshot.json`

to:

- real OpenClaw runtime tasks writing normalized fragment files into a stable directory.
