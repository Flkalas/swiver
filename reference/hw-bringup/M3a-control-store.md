# M3a — Sequential CU control verification

| Field | Value |
|-------|-------|
| **Milestone** | M3a |
| **Goal** | Verify Active **sequential CU** control ownership |
| **Normative** | [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md) · [microcode-spec.md](../hardware/microcode-spec.md) · [cpld-system-controller.md](../hardware/cpld-system-controller.md) |

---

## 1. Concept

Active control is the **sequential CU** ([cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md)).

| Content | Location |
|---------|----------|
| Opcode fetch → operand fetch → execute → retire; access WAIT | **CPLD-CU** sequential FSM |
| Boot + program | SST39 boot ROM or executable RAM on the unified shared bus |

Flash physical map: [rom-architecture.md](../hardware/rom-architecture.md).

---

## 2. Active verify sheet

| Check | Source |
|-------|--------|
| Complete each instruction before the next fetch; no fetch/EX overlap | [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md) |
| Default SYS: ADD/CMP/LDA/STA/LDIO/STIO 3; BEQ both/JMP/STA16 4; HALT/TRAP 2; CALL 9; RET 7; visible WAIT adds cycles | [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md) · [microcode-spec.md](../hardware/microcode-spec.md) |
| Opcode set `0x01–0x0F`; `0x10–0x1F` reserved | [microcode-spec.md](../hardware/microcode-spec.md) §2 |
| CALL/RET: 6 serialized stack byte accesses, redirect last; sequential CU fit pending | [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md) |

---

## 3. M3a sign-off

- [ ] Sequential CU **Design fits** (pending; required before hardware sign-off)
- [ ] **`system_ctrl_cu.jed`** and **`system_ctrl_dp.jed`** burned per [M2a-cpld-decode.md](M2a-cpld-decode.md)
- [ ] CALL/RET lab smoke — nested CALL/RET returns to caller ([M2a-cpld-decode.md](M2a-cpld-decode.md))
- [ ] CALL/RET CU fit and six-access stack ordering — [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md)
- [ ] Verify against sequential SYS / state tables in [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md)
