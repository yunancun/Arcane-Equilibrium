# ALR P2-3 Event Consumer Design

The planned consumer wakes from a Rust post-persist PostgreSQL notification and
then re-reads bounded unseen scanner rows. It cannot learn on a timer or cron.
One instance is protected by both database and runtime-file locks.

The source design does not create a database role, credential, unit file, or
process. Those actions require the later prestart security review.
