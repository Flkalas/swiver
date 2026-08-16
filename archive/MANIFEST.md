# Archive manifest

**Frozen:** 2026-07-04  
**Active tree:** `swiver-whitepaper.md` + `reference/**` only — no `docs/` folder.

**Layout:** searchable prose under `archive/` is **`MANIFEST.md` only**. Historical trees and code live in `archive/*.tar.gz` (not indexed as loose files).

Restore: `tar -xzf archive/NAME.tar.gz -C .` from repository root (unless noted). Snapshot trees that used to live under `archive/` restore with `tar -xzf archive/NAME.tar.gz -C archive`.

---

## Active reference (not in tarballs)

| Path | Role |
|------|------|
| [swiver-whitepaper.md](../swiver-whitepaper.md) | Project main document (**v1.0 P12**) |
| [reference/](../reference/) | v1.0 P12 specifications, bring-up, fixtures |
| [reference/hardware/cpld-pipe-cu.md](../reference/hardware/cpld-pipe-cu.md) | **Active pipe CU** |
| [reference/project/BOM.md](../reference/project/BOM.md) | Breadboard BOM |
| [`reference-background/`](../reference-background/) | Peer surveys — **not** Active implementer specs (kept outside `archive/`) |

---

## Bundles

| File | Contents |
|------|----------|
| `hwsim.tar.gz` | Electrical timing simulator |
| `cyclesim.tar.gz` | Micro-phase structural sim |
| `swiver_vm.tar.gz` | Python logic VM |
| `rust_vm.tar.gz` | Rust workspace (`crates/`, `Cargo.toml`, `.cargo/`) |
| `tools.tar.gz` | Generators, verify scripts |
| `hw.tar.gz` | Netlists, fixtures, YAML tests |
| `tests_py.tar.gz` | pytest suite |
| `host_toolchain.tar.gz` | plover_asm, plover_cc, plover_ld, forth, kern, basic, firmware |
| `verilog_sim.tar.gz` | Legacy Verilog tree |
| `research_docs.tar.gz` | `docs/hardware/research/` — Pareto, CPLD viewers |
| `docs_archive.tar.gz` | `docs/archive/` — superseded specs, gemini |
| `developer_docs.tar.gz` | `docs/developer/`, `docs/plans/` — sim guide, implementation plans |
| `fit-study-gpr-fsm.tar.gz` | **Frozen 2026-07-06** — GPR-FSM variant studies (A1/D5a/E1/F2/G), WinCUPL fit logs, desk reports |
| `cpld-rev-g-hdl.tar.gz` | **Frozen 2026-07-06** — rev G dual CPLD HDL (`hdl/`, `netlist/`) — restore before WinCUPL build |
| `gpr4-regfile-research.tar.gz` | **Frozen 2026-07-07** — 4-GPR / P1 / P1M1 / Gi1 feasibility study (`research/gpr4-regfile/`) |
| `p12-era-research.tar.gz` | **Frozen 2026-07-13** — call-ret / cpld-ustep / primitive-one-clock / pe1 / p12 desk studies (fed **v1.0 P12**) |
| `tier-c-single-cpld.tar.gz` | **Superseded 2026-07-06** — single ATF1504 + CW 574×2 (pre rev G); restore `-C archive` |
| `rev-g-normative-snapshot.tar.gz` | **Frozen 2026-07-07** — rev G normative prose before Gi1; restore `-C archive` |
| `rev-g-dual-3gpr.tar.gz` | **Superseded 2026-07-07** — rev G 3-GPR + TFR index; restore `-C archive` |
| `gi1-v1.0-normative.tar.gz` | **Superseded 2026-07-13** — Gi1 idx5 multiphase normative before **v1.0 P12**; restore `-C archive` |
| `pl-dos-fs-interchange-notes.tar.gz` | **Frozen 2026-07-13** — PL-DOS / SD FDD interchange design notes (not Active) |

`pack-bundles.ps1` — helper to rebuild code bundles. `build/`, `target/`, `.venv/` — local artifacts; not bundled.

---

## Legacy paths

| Old path | Current |
|----------|---------|
| `docs/normative/**` | `reference/**` |
| `docs/normative/project/plover-whitepaper.md` | `swiver-whitepaper.md` |
| `docs/project/plover-whitepaper.md` | `swiver-whitepaper.md` |
| `docs/hardware/system-architecture.md` | `reference/hardware/system-architecture.md` |
| `docs/hw-bringup/**` | `reference/hw-bringup/**` |
| `docs/developer/**` | `developer_docs.tar.gz` |
| `docs/hardware/research/**` | `research_docs.tar.gz` |
| `research/gpr4-regfile/**` | `gpr4-regfile-research.tar.gz` |
| `research/call-ret-cu-fit/**`, `pe1/**`, `p12/**`, … | `p12-era-research.tar.gz` |
| `docs/archive/**` | `docs_archive.tar.gz` |
| `BOM.md` (root) | `reference/project/BOM.md` |
| `archive/bundles/**` | `archive/*.tar.gz` |
| `archive/gi1-v1.0-normative/` (loose) | `gi1-v1.0-normative.tar.gz` |
| `archive/rev-g-dual-3gpr/` (loose) | `rev-g-dual-3gpr.tar.gz` |
| `archive/rev-g-normative-snapshot/` (loose) | `rev-g-normative-snapshot.tar.gz` |
| `archive/tier-c-single-cpld/` (loose) | `tier-c-single-cpld.tar.gz` |
| `archive/reference-background/` (loose) | [`reference-background/`](../reference-background/) (repo root; not Active normative) |
| `cpld_fsm/` (full tree) | `cpld/` — **tools only**; HDL in `cpld-rev-g-hdl.tar.gz` |
| `cpld_fsm/fit-study/` (full tree) | `fit-study-gpr-fsm.tar.gz` — restore to `cpld/fit-study` |
| `hwsim/`, `hw/`, `tools/`, … | matching code bundle above |

---

## Agent rules

For **architecture**, **bring-up**, **timing**, or **decode**:

1. Cite **`reference/**` and `swiver-whitepaper.md` only** — not restored tarball content.
2. Do **not** run or quote sim/code from `archive/*.tar.gz` unless the user explicitly asks for historical comparison.
3. **Forbidden as v1.0 SoC truth:** `alu8_decode` on breadboard, Flash `$4000` CW burn, `cpu_cw_direct`, pareto MC reports.
4. Research and developer docs exist only in tarballs — exploration history, not current spec. **No `research/` folder in the active tree** — restore `gpr4-regfile-research.tar.gz` or `p12-era-research.tar.gz` only when comparing history.
5. Do **not** keep unpacked trees under `archive/` in the working tree — pack into `*.tar.gz` and leave this MANIFEST as the only searchable archive index.

### Frozen FSM snapshot (M3a) — Gi1 legacy

Historical Gi1 idx5 prose: `gi1-v1.0-normative.tar.gz` (restore `-C archive`). **Active CU:** [reference/hardware/cpld-pipe-cu.md](../reference/hardware/cpld-pipe-cu.md).

---

## Pack commands (one-time)

```powershell
tar -czf archive/research_docs.tar.gz docs/hardware/research
tar -czf archive/docs_archive.tar.gz docs/archive
tar -czf archive/developer_docs.tar.gz docs/developer docs/plans
tar -czf archive/fit-study-gpr-fsm.tar.gz -C cpld fit-study
tar -czf archive/cpld-rev-g-hdl.tar.gz -C cpld hdl netlist
tar -czf archive/gpr4-regfile-research.tar.gz research
# Snapshot trees that lived under archive/:
tar -czf archive/gi1-v1.0-normative.tar.gz -C archive gi1-v1.0-normative
tar -czf archive/rev-g-dual-3gpr.tar.gz -C archive rev-g-dual-3gpr
tar -czf archive/rev-g-normative-snapshot.tar.gz -C archive rev-g-normative-snapshot
tar -czf archive/tier-c-single-cpld.tar.gz -C archive tier-c-single-cpld
```

Code bundles: see `archive/pack-bundles.ps1`.
