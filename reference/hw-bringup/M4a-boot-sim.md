# M4a — Boot chain (JMP handoff gate)

| Field | Value |
|-------|-------|
| **Milestone** | M4a |
| **Goal** | JMP handoff: boot ROM → RAM `$0800` → **`JMP $0800`** |
| **Status** | Historical logic handoff verified 2026-06-08; sequential CU timing/electrical sign-off pending |
| **Normative** | [boot-jmp-handoff.md](../boot/boot-jmp-handoff.md) |

---

## 1. What was proven

Before breadboard (M4b), the boot chain was checked against the JMP handoff checklist:

1. Boot ROM copies kernel sector to RAM `$0800`
2. SP/RP/GPR pre-init cells written
3. **`JMP $0800`** reaches kernel stub

**Pass criterion for M4b:** reproduce the same byte images on real Flash/SRAM ([fixtures](../fixtures/README.md)).

---

## 2. Frozen images (active repo)

| Image | Document |
|-------|----------|
| Boot ROM `$0000` | [boot-rom.md](../fixtures/boot-rom.md) |
| Reset vector `$FFFC` | [boot-vector.md](../fixtures/boot-vector.md) |
| Kernel smoke `$0800` | [add_imm-sram.md](../fixtures/add_imm-sram.md) (or kernel stub in boot-rom tail) |

v1.0 breadboard control: **sequential CU** ([cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md)). The historical image/handoff check does not prove this schedule or hardware timing. RAM execution uses the unified 64 KiB shared-bus space; reset-vector loading in the CPU helper remains abstract, uncounted initialization.

---

## 3. M4a sign-off

- [x] JMP handoff chain verified (2026-06)
- [ ] M4b hardware burn matches frozen fixtures

---

## 4. Next

→ [M4b-boot-hardware.md](M4b-boot-hardware.md)
