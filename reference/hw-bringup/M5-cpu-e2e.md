# M5 — Integrated CPU E2E (breadboard regression)

| Field | Value |
|-------|-------|
| **Milestone** | M5 |
| **Goal** | Breadboard wiring captured as a **frozen checklist** |
| **Status** | Hardware sign-off pending; CPU simulator is a zero-delay functional model |
| **선행** | M2b–M4b breadboard smoke |

---

## 1. Scope (v1.0)

M5 is **not** a new solder step. After M1–M4b pass on hardware:

1. Photograph / netlist log matches [breadboard-wiring.md](breadboard-wiring.md)
2. F4/F5 trace from [M3b-fetch-execute.md](M3b-fetch-execute.md) matches sequential CU / ISA ([cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md), [microcode-spec.md](../hardware/microcode-spec.md))

Sign-off against frozen fixtures in [fixtures](../fixtures/).

---

## 2. M5 sign-off

- [ ] Composite breadboard matches normative block diagram
- [ ] M3b F4/F5 R0 / branch trace documented (lab log)
- [ ] Control path matches sequential CU ([cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md))

---

## 3. Note

v1.0 SoC control is the **CPLD sequential CU**. CPU functional tests do not validate the full electrical CPU: memory timing, bus contention, glitches, setup/hold, and sequential-CU **Design fits** remain separate hardware gates.
