# MIT Design - ALR P2-4 PIT Scanner Dataset

Date: 2026-07-09
Verdict: `PIT_RESEARCH_ONLY`
Mode: `ROLE_FALLBACK_SINGLE_SESSION`

Input rows are immutable ALR source hashes ordered by source timestamp. The
dataset fixes an `as_of_ts` at the last selected source, derives features only
from that closed source set, and partitions chronological source identities
into train/validation/OOS partitions with explicit purge and embargo markers.
The row sets must be disjoint and their hashes retained.

Because no after-cost outcome label is present, the emitted
`pit_dataset_manifest_v1` is `research_only`, never `dataset_ready`. P2-4 may
run the existing statistical selector over scanner recurrence descriptors but
cannot call a supervised outcome trainer on fabricated fills or labels.
