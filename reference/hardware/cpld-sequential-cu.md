# CPLD Sequential CU — v1.0 (Active)

**Status:** Active normative CU specification — non-pipelined in-order
**Date:** 2026-10-23
**Physical implementation:** sequential CU PLD, WinCUPL **Design fits**, wiring and lab timing **pending**
**Related:** [system-architecture.md](system-architecture.md) · [control-and-decode.md](control-and-decode.md) · [microcode-spec.md](microcode-spec.md) · [memory-map.md](memory-map.md)

This specification supersedes the [historical P12 pipe design](cpld-pipe-cu.md). Existing ISA encodings, R0/MBR datapath, flag semantics, MMIO addresses and software return-stack layout remain unchanged.

---

## 1. Execution and memory contract

1. **Non-pipelined in-order:** complete the current instruction before fetching the next opcode. Instruction order alone does not imply this; non-overlap is an explicit additional requirement.
2. **Unified memory:** one mapped **64 KiB** address space and one shared 8-bit instruction/data bus serve opcode fetch, operand fetch, RAM data, stack and MMIO. RAM is executable. Flash boot overlays and Run mode follow [memory-map.md](memory-map.md).
3. **One phase per SYS:** opcode fetch, each operand-byte fetch and execute/stack accesses occupy separate counted `CLK_SYS` ticks. Operand fetch never overlaps execution. There is no prefetch, IF/EX overlap, branch bubble, port-conflict stall or pipe fallback.
4. **Visible waiting:** the functional simulator exposes `request_wait()` to insert `WAIT` ticks. This hook does not implement physical ready/timeout sensing or establish a hardware WAIT generator; that design and qualification remain pending. A WAIT does not fetch, retire or repeat a memory/MMIO side effect; the pending phase completes once when advanced.
5. **Datapath:** ALU A ← R0 (`q_a`), ALU B ← MBR (`net_mbr`); `reg_we` is the single CU→DP G-IC wire. Hold the operand through execution. ADD/CMP update flags; CMP suppresses R0 write and bus output enable while the physical ALU result remains SUB. BEQ tests the existing Z flag.
6. **Physical gate:** WinCUPL **Design fits** on the implemented sequential CU and measured shared-bus timing are required. The ATF1504 64-macrocell part rating or a design estimate proves neither.

## 2. Phases and transitions

| Phase | Work in this SYS |
|-------|------------------|
| `FETCH_OPCODE` | Read current mapped memory at PC into IR; decode instruction format |
| `FETCH_OPERAND` | Read one instruction operand byte into its latch; repeat for a second byte when required |
| `EXECUTE` | ALU, branch redirect, HALT or reserved-op trap; retire upon instruction completion |
| `MEM_READ` / `MEM_WRITE` | One data/MMIO byte access; complete and retire the memory instruction |
| `STACK_RP_LO` / `STACK_RP_HI` | Read RP low/high; validate on high-byte completion |
| `STACK_DATA_LO` / `STACK_DATA_HI` | Write CALL return-PC low/high or read RET return-PC low/high |
| `STACK_WRITE_RP_LO` / `STACK_WRITE_RP_HI` | Write updated RP low/high; final high-byte write retires and redirects |
| `WAIT` | One visible extra tick without architectural progress; resume the pending phase |

```text
reset initialization -> FETCH_OPCODE -> FETCH_OPERAND (0..2) -> completion phase
completion phase = EXECUTE, MEM_READ/MEM_WRITE, or six CALL/RET stack byte phases
successful completion -> FETCH_OPCODE (on the next SYS)
EXECUTE HALT or stack error -> stopped
pending phase -> WAIT (as required) -> pending phase
```

Decode is combinational phase selection, not an invented extra SYS. ALU/branch/HALT/trap instructions retire in EXECUTE; memory instructions retire in MEM_READ/MEM_WRITE; CALL/RET retire on the final stack access. The next instruction's fetch occurs on a later tick. HALT retains PC at its opcode and retires in EXECUTE before stopping. The existing reserved-op TRAP policy is a no-op retirement after advancing PC by one byte; it continues to the next opcode and assigns no new ISA encoding. A taken BEQ/JMP commits PC in EXECUTE, then fetches its target; BEQ not taken has the same phase count. No discarded prefetch is charged.

## 3. CALL/RET byte sequencing

RP is the 16-bit little-endian RAM cell `$0F00/$0F01`; the return-stack body is `$F600–$FEEF`, growing upward from `$F600`. There is no architected hardware RP register. Temporary implementation latches do not change the ISA. Valid RP values are aligned two-byte boundaries from `$F600` through the full-stack sentinel `$FEF0`; malformed pointers halt at the RP-high validation tick before any stack writes. CALL at `$FEF0` overflows; RET at `$FEF0` may pop the last occupied cell.

After fetching all instruction bytes, perform **exactly six shared-bus byte accesses** on the successful path:

| Order | CALL | RET |
|------:|------|-----|
| 1 | Read RP low at `$0F00` | Read RP low at `$0F00` |
| 2 | Read RP high at `$0F01`; validate push capacity | Read RP high at `$0F01`; validate pop availability |
| 3 | Write return-PC low at RP | Read return-PC low at RP−2 |
| 4 | Write return-PC high at RP+1 | Read return-PC high at RP−1 |
| 5 | Write updated RP low (`RP+2`) to `$0F00` | Write updated RP low (`RP−2`) to `$0F00` |
| 6 | Write updated RP high to `$0F01`; retire and PC ← abs16 target | Write updated RP high to `$0F01`; retire and PC ← popped word |

CALL's return PC is the address after its three-byte instruction. RET's PC source is the popped word, not MBR. The final write and redirect complete the instruction; they do not fetch the target opcode. Stack overflow/underflow stops execution without successful retirement. No atomic rollback of earlier byte accesses is implied.

## 4. Counted SYS costs

These are **default logical counts for successful accesses**, excluding additional WAIT. They are not measured clock speeds, physical timing acceptance or proof of CPLD fit.

| Instruction | Instruction-byte fetches | Execute/stack phases | Total SYS |
|-------------|------------------------:|---------------------:|----------:|
| ADD / CMP | 2 | 1 | **3** |
| LDA / STA / LDIO / STIO | 2 | 1 | **3** |
| BEQ, taken or not / JMP / STA16 | 3 | 1 | **4** |
| HALT / reserved-op trap | 1 | 1 | **2** |
| CALL | 3 | 6 | **9** |
| RET | 1 | 6 | **7** |

There is no cold/warm-stream discount. Total SYS = the table count + explicit WAIT ticks. Stopping faults may terminate before the successful-path count; traces must show which accesses completed.

The simulator reset-vector helper is **uncounted functional initialization**. Reading the reset vector in that helper is not a claim that physical reset consumes zero cycles. A hardware reset sequence and its timing remain to be specified/verified before physical bring-up acceptance.

## 5. Per-op control intent

| Class | Separate execute/stack behavior |
|-------|---------------------------------|
| ADD | R0 + MBR → R0; `Y_OE`, `REG_WE`, `FLG_WE` |
| CMP | R0 − MBR → flags; `FLG_WE`; no R0 write |
| LDA / LDIO | Shared-bus `MEM_RD` and R0 write on completed access |
| STA / STIO / STA16 | Shared-bus `MEM_WR` of R0 on completed access |
| BEQ | Test existing Z; conditional `PC_LOAD_EN`; flags unchanged |
| JMP | Unconditional final `PC_LOAD_EN` from abs16 latch |
| CALL / RET | Six accesses in §3; final redirect and retirement |
| HALT | Retire and stop in separate EXECUTE; PC remains at HALT opcode |
| Reserved-op trap | Retire as the existing no-op policy in separate EXECUTE; continue at next byte |

`REG_WE` reaches CPLD-DP through G-IC `reg_we`. Direct ALU controls retain the normative names in [control-and-decode.md](control-and-decode.md). Reserved encodings remain reserved; trap behavior does not assign a new opcode.

## 6. Trace and verification contract

Each `step()` advances exactly one counted SYS and records its phase, bus activity, address/value, control strobes and completion/error status. `last_trace.state` is the emitted tick; `CpuM3b.state` identifies the pending next real phase. Each completed memory SYS has one `BusAccess(kind, address, value)`; WAIT has none. The trace fields `stage.fetch_active` and `stage.execute_active` are mutually exclusive. Fetch ticks have only fetch activity; execute, data-memory and stack ticks have only execute activity; WAIT has neither. The optional `bus_access` carries the actual single-byte transaction. Memory/MMIO effects correspond to actual completed accesses rather than synthetic activity flags.

Verify RAM instruction execution through the same current-map read path as data, exact ordinary/branch/stack SYS counts, CALL/RET byte access order, return PC and RP updates, HALT stop, reserved-op no-op retirement, overflow/underflow, WAIT side-effect suppression and absence of fetch/execute overlap. Functional tests validate the executable abstraction; they do not validate electrical timing.

## 7. Timing, wiring and fit acceptance

**2 MHz (500 ns)** is a design target, **not a measured sequential pass**. The former P12 IF/EX path estimates, IPC assumptions, pin/MC projections and fit discussion remain solely in the [superseded P12 record](cpld-pipe-cu.md). ALU-only combinational values also do not establish the new full control/bus path.

Before hardware acceptance, produce the sequential CU PLD, confirm WinCUPL **Design fits**, review shared-bus ownership/enables, hardware WAIT generation and temporary stack/address latches, then measure fetch, execute, memory/MMIO, stack and branch setup/hold with actual loading. Record explicit WAIT requirements where needed and update the schedule. Fit and timing remain **pending** until those checks pass; no macrocell estimate substitutes for the fitter result.
