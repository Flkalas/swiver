# Software roadmap (VM OS stack)

**Related:** [software-memory-layout.md](software-memory-layout.md)

Swiver v0.1 software milestones **S0–S7** on logic VM (developer), then hardware bring-up (M1–M5).

## Phase overview

| Phase | Milestones | Goal |
|-------|------------|------|
| **S0** | docs, regression harness | Index + memory map + `run_sw_regression.py` |
| **Phase 1** | S1–S3 | Assembler, CALL/RET, Forth core |
| **Phase 2** | S4–S6 | Forth OS, subset C, C microkernel |
| **Phase 3** | S7 (PL-DOS) | vFDD, PLFS, `.PLR`, Forth shell |

## Milestone index

| ID | Deliverable | Doc | Test gate |
|----|-------------|-----|-----------|
| S0 | Roadmap, layout, regression script | this file | baseline regression |
| S1 | `plover_asm` | [plover-asm.md](plover-asm.md) | milestone checklist |
| S2 | CALL/RET ISA (pipe CU) | [calling-convention-v0.1.md](calling-convention-v0.1.md) | pipe CU CALL/RET smoke |
| S3 | Forth core | [forth-system.md](forth-system.md) | milestone checklist, `forth_boot.yaml` |
| S3c | Normative asm Forth | forth-system §normative | `breadboard ISA` |
| S4 | Forth OS services | [forth-os-services.md](forth-os-services.md) | milestone checklist |
| S5 | `plover_cc` | **Static-allocation Subset C** — [subset-c.md](subset-c.md) | milestone checklist |
| S6 | C kernel | **Cooperative / polling microkernel** — [os-kernel.md](os-kernel.md) | milestone checklist, `os_boot.yaml` |
| S7a | vFDD driver | [virtual-fdd.md](virtual-fdd.md) | milestone checklist |
| S7b | PLFS | [plover-fat.md](plover-fat.md) | milestone checklist |
| S7c | `.PLR` loader | [program-loader.md](program-loader.md) | milestone checklist |
| S7d | PL-DOS shell | [dos-shell.md](dos-shell.md), [pl-dos-roadmap.md](pl-dos-roadmap.md) | `dos_boot.yaml` |

## Hardware cross-links

| Software | Hardware |
|----------|----------|
| S2 CALL/RET | M3a + [cpld-pipe-cu.md](../hardware/cpld-pipe-cu.md) §5.1 desk |
| S7 vFDD | [mailbox-protocol.md](../copro/mailbox-protocol.md), [rp2350-coprocessor.md](../copro/rp2350-coprocessor.md) |
| Boot / PL-DOS | [bootloader.md](../boot/bootloader.md) |

## Verification

Each milestone: add tests → cumulative `regression tests/` PASS → git commit. See [tests/README.md](../tests/README.md).

### S5 — Subset C philosophy

v1.0 hardware has **no stack-pointer register** and **no frame-pointer datapath**. **S5 Subset C** targets a restricted dialect: **no unbounded recursion**, and all locals/parameters are **statically allocated** in fixed RAM cells ([subset-c.md](subset-c.md), [plover-whitepaper.md](../../plover-whitepaper.md) §2.3.1).

### S6 — Microkernel philosophy

**S6** adopts a **cooperative** scheduling model and **polling-only I/O** — no preemptive multitasking and no IRQ drivers on the normative breadboard ([os-kernel.md](os-kernel.md), [plover-whitepaper.md](../../plover-whitepaper.md) §9.1).
