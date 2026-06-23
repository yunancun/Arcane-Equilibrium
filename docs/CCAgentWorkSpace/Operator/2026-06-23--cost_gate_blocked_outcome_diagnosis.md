# Operator Note: Cost Gate Blocked-Outcome Diagnosis

Source checkpoint: `51a1c4ad`

This pass improves the autonomous learning loop after Cost Gate rejects.

Blocked-signal outcome review now records whether a side-cell is:

- sample-insufficient,
- a false-negative candidate after cost,
- gross-positive but still below cost,
- positive but unstable,
- or confirmed blocked after cost.

The important behavior change: gross-positive but net-insufficient blocked
outcomes now become an edge-amplification / friction-reduction engineering task
instead of being archived as generic no-edge.

No authority was granted: no Cost Gate lowering, no probe/order authority, no
runtime mutation, no deployment, and no promotion proof.
