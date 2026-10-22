# Swiver ALU viewer implementation

Scope: phase 1 only — reconcile the physical 12-chip ALU, extend cyclesim's
zero-delay simulation foundation, and serve a Korean local web viewer.
The P12 ISA/FSM, CPU integration, and propagation delays remain out of scope.

- [x] Independent read-only model/engine and UI reviews through Orca.
- [x] Freeze circuit/snapshot API after review.
- [x] Implement engine/ALU and web assets with disjoint ownership.
- [x] Integrate loopback-only standard-library HTTP server and CLI.
- [x] Exhaustive ALU inputs, chip truth tables, four-state engine, existing tests.
- [x] Independent review and Playwright interaction/failure checks.
- [x] Preserve legacy/new screenshots at 1440×900 and 1280×800; inspect visually.
- [x] Document corrections, execution, and limitations; commit by concern.

Preserve unrelated user edits, untracked files, and uv symlink configuration.
All electrical calculation runs in Python. Browser code displays snapshots.
Coordinator owns final integration, fixes, verification, and scoped commits.
