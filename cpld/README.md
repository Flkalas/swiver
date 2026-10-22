# CPLD — toolchain (active)

WinCUPL unpack, OpenOCD, FT232H JTAG probe. **Active CU specification:** sequential FSM — [reference/hardware/cpld-sequential-cu.md](../reference/hardware/cpld-sequential-cu.md). Sequential CU `.pld` **Design fits pending**.

| Path | Role |
|------|------|
| [tools/](tools/) | install-wincupl, install-openocd, jtag-probe, wiring-flash |

**Restore legacy HDL:** `tar -xzf archive/cpld-rev-g-hdl.tar.gz -C cpld` (rev G / historical). Gi1 idx5 normative prose: `archive/gi1-v1.0-normative.tar.gz` (see [MANIFEST.md](../archive/MANIFEST.md)).

**Normative ports / DP:** [reference/hardware/cpld-system-controller.md](../reference/hardware/cpld-system-controller.md)
