# RP2354B Coprocessor Board — Design Whitepaper

**Version:** 0.1 (draft) · **Date:** 2026-06-12  
**Status:** Planning — pin map **draft** until schematic lock  
**Package target:** Raspberry Pi **RP2354B** (QFN-80, 10×10 mm, **2 MB stacked flash**)

**Normative software contract:** [mailbox-protocol.md](mailbox-protocol.md) (software v0.1)  
**System context:** [system-architecture.md](../hardware/system-architecture.md) v1.0  
**Related:** [rp2350-coprocessor.md](rp2350-coprocessor.md) · [display-console.md](display-console.md) · [audio-apu.md](audio-apu.md) · [input-hid.md](input-hid.md) · [virtual-fdd.md](virtual-fdd.md)

---

## 1. Executive summary

Swiver v1.0 keeps the **8-bit TTL CPU as bus master**. A separate **RP2354B** board acts as a **Mailbox coprocessor**: the CPU talks only through MMIO **`$FF00–$FFFB`** (252 bytes, polling, **no IRQ**). The copro renders HDMI, mixes PSG audio, hosts USB HID, and serves virtual floppy sectors from microSD.

This whitepaper defines **electrical interfaces, GPIO budget, power, PCB constraints, firmware split, and bring-up gates** for a production-oriented RP2354B daughterboard (or integrated 3.3 V PCB region).

| Item | Decision |
|------|----------|
| MCU | **RP2354B** — same pinout as RP2350B, **48 user GPIO**, **internal 2 MB flash** (no external QSPI NOR) |
| CPU link | **Mailbox parallel tap** — **not** full 16-bit address/data bus snoop |
| CPU interface pins | **20 GPIO** (8 data + 8 offset + 4 control) |
| Copro functions | vFDD (SPI SD) · VDU (HSTX DVI/HDMI) · APU (1× PWM) · HID (USB host) |
| GPIO budget (recommended) | **~37 / 48** used · **~11 spare** |
| Milestone | **M4b** stretch — [M4b-boot-hardware.md](../hw-bringup/M4b-boot-hardware.md) G3–G4 |

**RP2354B vs RP2350B:** Identical GPIO map. RP2354B eliminates external QSPI flash and associated BOM/routing; firmware stores in on-chip 2 MB.

---

## 2. Scope

### 2.1 In scope

- RP2354B schematic, layout, and connector definition for Swiver copro role
- Mailbox hardware mirror of [mailbox-protocol.md](mailbox-protocol.md)
- vFDD storage (microSD over SPI)
- VDU pipeline per [display-console.md](display-console.md)
- APU per [audio-apu.md](audio-apu.md)
- HID USB host per [input-hid.md](input-hid.md)
- Debug (SWD, optional UART), power, reset

### 2.2 Out of scope (v0.1)

| Item | Reason |
|------|--------|
| CPU address/data **snoop** / shadow RAM DMA | Out of scope — Mailbox-only copro (§6.2) |
| Serial UART module (`SIG 0xD4`) | Separate **CPU slot** peripheral — [serial-module.md](serial-module.md) |
| PCM streaming (`MB_CMD 0x58–0x5F`) | Reserved v0.2 |
| Gamepad / HID extension (`0x44–0x4F`) | Reserved |
| IRQ to CPU | Normative: **polling only** |

---

## 3. System context

```text
  ┌─────────────────────────────────────────────────────────────┐
  │  Swiver CPU board (master)                                   │
  │  8-bit TTL · 2 MHz · MMIO LDIO/STIO                          │
  │  MAILBOX_EN + A[7:0] + D[7:0] + MEM_RD/WR + CLK              │
  └──────────────────────────┬──────────────────────────────────┘
                             │ Copro connector (§5)
  ┌──────────────────────────▼──────────────────────────────────┐
  │  RP2354B copro board                                         │
  │  Core0: Mailbox · vFDD · APU · HID                           │
  │  Core1: VDU compose · HSTX 640×480@60                        │
  │  Local: microSD · USB-A host · HDMI · audio jack · SWD       │
  └─────────────────────────────────────────────────────────────┘
```

The CPU **never** maps RP2354B SRAM. All copro state (framebuffers, HID FIFOs, SD cache) lives in RP2354B internal memory.

**Integration modes:**

| Mode | CPU rail | Data path | Reference |
|------|----------|-----------|-----------|
| **A — Breadboard bring-up** | 5 V TTL | `SN74LVC8T245` ×1 (CPU side) | — |
| **B — 3.3 V PCB** | 3.3 V LVC | Direct `D[7:0]` to RP2354B | [BOM-3v3.md](../../BOM-3v3.md) |

Mode A is for M4b smoke on existing 5 V breadboard; Mode B is the production PCB target.

---

## 4. Functional requirements

### 4.1 Mailbox (mandatory)

| Requirement | Source |
|-------------|--------|
| Mirror `MB_STATUS` … `MB_BUFFER` (`$FF00–$FFFB`) | [mailbox-protocol.md](mailbox-protocol.md) §1 |
| Set **Busy** during vFDD/VDU work; **DataReady** when CPU may consume | §3–4 |
| **Error** on media/timeout fault; CPU clears via `CMD_NOP` | §4 |
| **No IRQ** — CPU polls `MB_STATUS` | [system-architecture.md](../hardware/system-architecture.md) |

Decode on CPU board (already normative):

```text
MAILBOX_EN = (A >= 16'hFF00) && (A < 16'hFFFC)
```

`$FFFC–$FFFF` is **never** mailbox ([memory-map.md](../hardware/memory-map.md)).

### 4.2 vFDD

| Requirement | Value |
|-------------|-------|
| Sector size | 512 bytes |
| Access | `CMD_READ` / `CMD_WRITE` + `MB_AUX` = drive_id |
| Storage | microSD, FAT-ish image file or raw `.img` (firmware choice) |
| Multi-transfer | 512 B via 2×248 B + 16 B extension — firmware TBD |

### 4.3 VDU

| Parameter | Value |
|-------------|-------|
| Text | **40×25**, 8×8 font |
| Render target | **320×240 RGB565 @ 30 Hz** (double buffered) |
| HDMI output | **640×480 @ 60 Hz** — 2×2 spatial + 2× temporal hold |
| Interface | HSTX / DVI-compatible HDMI sink |

See [display-console.md](display-console.md) for compositing rules (`VDU_MODE`, MODE_BOTH chroma key).

### 4.4 APU

| Parameter | Value |
|-------------|-------|
| Channels | 4 — ch0–2 square, ch3 noise |
| Mix rate | 22.05 kHz, 8-bit mono |
| Output | **1× PWM** + RC filter → 3.5 mm jack |
| Policy | Silent drop during vFDD Busy |

### 4.5 HID

| Parameter | Value |
|-------------|-------|
| Devices | USB keyboard + mouse (HID boot protocol) |
| Queues | Key 64 · Mouse 32 — drop oldest |
| Delivery | Mailbox `0x40–0x43`; status bits 4–5 |
| Policy | Silent drop during vFDD Busy |

---

## 5. CPU copro connector

### 5.1 Signal list (normative for board spin)

| Signal | Dir (from CPU) | Width | Description |
|--------|----------------|-------|-------------|
| `D[7:0]` | Bidir | 8 | Data bus (3.3 V or via 245) |
| `A[7:0]` | Out | 8 | Byte offset within `$FF00` window |
| `MAILBOX_EN` | Out | 1 | Active when CPU accesses `$FF00–$FFFB` |
| `MEM_RD` | Out | 1 | Read strobe (from CW / glue) |
| `MEM_WR` | Out | 1 | Write strobe |
| `CLK` | Out | 1 | **2 MHz** system clock (`net_clk2`) for sample timing |
| `GND` | — | ≥2 | Common ground, low-inductance return |
| `+3V3` | — | 0–1 | Optional reference only if copro self-powered |

**Not routed to RP2354B:** `A[15:8]` (fixed `$FF` inside window), full CPU address bus, `/CE`, `Y_OE`, opcode, phase.

Suggested connector: **2×10 pin header, 2.54 mm** (20 signals + key/GND) or **FFC 24-pin** on integrated PCB.

### 5.2 Bus timing assumptions

| Parameter | Value | Notes |
|-----------|-------|-------|
| CPU clock | **2.000 MHz** `CLK_SYS` (single source) | [system-architecture.md](../hardware/system-architecture.md) |
| `CLK_SYS` period | **500 ns** | ALU / EX budget @ 2.000 MHz |
| Mailbox access | `LDIO` / `STIO` MMIO cycle | Firmware must sample/setup within MEM_RD/WR window |
| RP2354B core clock | ≥ **150 MHz** typical | Headroom for GPIO IRQ-less polling |

Firmware on RP2354B should treat the mailbox interface as a **fast GPIO peripheral** (or PIO state machine) clocked from `CLK` and qualified by `MAILBOX_EN`.

### 5.3 Electrical (Mode A — 5 V breadboard)

```text
  CPU D[7:0] (5 V) ←→ SN74LVC8T245 ←→ RP2354B D[7:0] (3.3 V)
  DIR/OE: glue from MEM_RD/WR + MAILBOX_EN
  A[7:0], MAILBOX_EN, MEM_RD, MEM_WR, CLK: 3.3 V CMOS to RP2354B
       (5 V-tolerant inputs on RP2354B — verify series R if driven from 5 V glue)
```

**Recommendation for Mode A:** Level-shift **data only** via 245; drive **control/address from 3.3 V glue** on a small interposer, or use **series 330 Ω + RP2354B 3.3 V CMOS inputs** with verified VI spec.

### 5.4 Electrical (Mode B — 3.3 V PCB)

Direct LVC connection — **no 245**. Optional **33 Ω** series on `D[7:0]` per [BOM-3v3.md](../../BOM-3v3.md) bus damping practice.

---

## 6. GPIO budget

### 6.1 Summary

| Block | GPIO min | GPIO recommended | Core |
|-------|----------|------------------|------|
| Mailbox CPU link | 20 | 20 | Shared / Core0 poll |
| vFDD SPI + SD | 4 | 5 (+CD) | Core0 |
| VDU HSTX (DVI) | 4 | 4 | Core1 |
| APU PWM | 1 | 1 | Core0 |
| USB (DP/DM) | 0* | 0* | Core0 |
| USB VBUS / OC | 0 | 2 | Core0 |
| SWD | 2 | 2 | — |
| UART debug | 0 | 2 | Core0 |
| Status LED | 0 | 1 | Core0 |
| **Total** | **31** | **37** | |
| **RP2354B available** | **48** | **48** | |
| **Spare** | **17** | **11** | |

\* USB D+/D− use **dedicated USB pins** (not counted in the 48 user GPIO pool).

### 6.2 Interface choice

v1.0 uses a **Mailbox parallel tap** (20 GPIO) — not a full 16-bit address/data bus snoop.

| Interface | GPIO (approx.) | Role |
|-----------|----------------:|------|
| **Mailbox tap (normative)** | 20 | `D[7:0]` + offset `A[7:0]` + EN/RD/WR/CLK — [rp2350-coprocessor.md](rp2350-coprocessor.md) |
| Full bus snoop (not used) | 28+ | Would require A[15:0] + control; exceeds spare budget with HSTX/SPI |

---

## 7. Draft pin map (RP2354B QFN-80)

> **Draft — lock at schematic review.** HSTX pins must stay on HSTX-capable pads (datasheet §1.2.3, GPIO 12–19 bank).

| Function | Signal | Draft GPIO | Alt function |
|----------|--------|------------|--------------|
| **Mailbox** | `MB_D0` … `MB_D7` | GPIO0–7 | — |
| | `MB_A0` … `MB_A7` | GPIO8–15 | — |
| | `MAILBOX_EN` | GPIO16 | |
| | `MEM_RD` | GPIO17 | |
| | `MEM_WR` | GPIO18 | |
| | `CLK_IN` | GPIO19 | |
| **HSTX / HDMI** | `HSTX_CK` | GPIO14 | HSTX (move MB if clash — prefer dedicated HSTX bank) |
| | `HSTX_D0` | GPIO15 | HSTX |
| | `HSTX_D1` | GPIO16 | **Conflict** — resolve in schematic |
| | `HSTX_D2` | GPIO17 | **Conflict** — resolve in schematic |
| **SPI0 / SD** | `SD_SCK` | GPIO18 | SPI0 SCK — **Conflict** |
| | `SD_MOSI` | GPIO19 | SPI0 TX |
| | `SD_MISO` | GPIO20 | SPI0 RX |
| | `SD_CS` | GPIO21 | SPI0 CS |
| | `SD_CD` | GPIO22 | Card detect |
| **APU** | `APU_PWM` | GPIO23 | PWM |
| **Debug** | `UART_TX` | GPIO24 | UART1 TX |
| | `UART_RX` | GPIO25 | UART1 RX |
| **LED** | `LED_STATUS` | GPIO26 | |
| **USB host** | `USB_VBUS_EN` | GPIO27 | |
| | `USB_OVCUR` | GPIO28 | |
| **SWD** | `SWCLK` / `SWDIO` | dedicated | Debug header |

**Pin map revision rule:** Allocate **HSTX 12–15** (or 12–19 subset per mode) first, then **SPI on 20–23**, then **Mailbox on 0–11 + 16–19** using **remaining** pads. The table above intentionally shows a **clash** to force schematic-time separation — expected outcome:

```text
  HSTX:     GPIO12, 13, 14, 15
  Mailbox:  GPIO0–7 (D), GPIO8–11 + GPIO26–29 (A), GPIO16–19 (ctrl) — example
  SPI SD:   GPIO20–22 (+ CD GPIO23)
  PWM:      GPIO24
  UART:     GPIO25–26
  LED/USB:  GPIO27–28
```

Final assignment recorded in `hw/copro/rp2354b.pin` (TBD at schematic lock).

---

## 8. Subsystem design notes

### 8.1 Mailbox firmware mirror

RP2354B maintains a **shadow struct** in SRAM:

```c
typedef struct {
    uint8_t status;   // MB_STATUS
    uint8_t cmd;      // MB_CMD (WO from CPU)
    uint8_t param;    // MB_PARAM
    uint8_t aux;      // MB_AUX
    uint8_t buffer[248];
} mailbox_shadow_t;
```

**Read path (CPU → copro):** CPU drives address offset + `MEM_RD`; copro drives `D[7:0]` with shadow byte.  
**Write path:** CPU writes data; copro latches into shadow; **watch `MB_CMD`** writes to dispatch handlers.

Reference stub: [`firmware/rp2350/mailbox_stub/main.c`](../../firmware/rp2350/mailbox_stub/main.c).

### 8.2 vFDD — microSD

| Item | Recommendation |
|------|----------------|
| Interface | **SPI0** (simple bring-up) or **SDIO 1-bit** (future — more pins) |
| Socket | Push-push microSD, 3.3 V signalling |
| Card detect | GPIO input, pull-up, optional |
| Filesystem | Firmware: block read/write to LBA; host prepares `.img` |
| Power | Separate 100 nF at socket; bulk 10 µF on 3.3 V |

During sector DMA to/from `MB_BUFFER`, set **`MB_ST_BUSY`**; block APU/HID command acceptance (silent drop).

### 8.3 VDU — memory budget

| Asset | Size (approx.) |
|-------|----------------|
| FB0 + FB1 RGB565 320×240 | 2 × 153 600 B ≈ **300 KiB** |
| Text matrix 40×25 + attrs | &lt; 2 KiB |
| Font 8×8 (256 chars) | 2 KiB |
| HID + APU queues | &lt; 4 KiB |

RP2354B SRAM **520 KiB** — sufficient with headroom for stack/heap.

Core1 loop: compose 320×240 @ 30 Hz → upscale to 640×480 scan-out @ 60 Hz via HSTX ([display-console.md](display-console.md) §3).

### 8.4 APU — analogue output

```text
  GPIO PWM (22.05 kHz effective) ──► RC low-pass (~3.3 kHz) ──► 3.5 mm jack
  Optional: 100 nF AC coupling, 10 kΩ load reference
```

Verify with **1 kHz square** on scope at jack ([audio-apu.md](audio-apu.md) §5).

### 8.5 HID — USB host

| Item | Recommendation |
|------|----------------|
| Stack | TinyUSB host mode |
| Connector | USB-A receptacle, ESD (USBLC6), **VBUS switch** |
| Power | Copro USB input **or** powered hub — document max current (500 mA class) |
| Reports | Boot keyboard + boot mouse → ASCII / button + dx/dy queues |

---

## 9. Power and clock

### 9.1 Power tree

```text
  VBUS 5 V (USB-C) ──► AP2112K-3.3 (≥600 mA) ──► RP2354B IOVDD / DVDD
                    └──► (optional) separate LDO for SD VDD if inrush heavy
```

| Rail | Spec |
|------|------|
| RP2354B core | 1.1 V internal — DVDD pins per datasheet |
| IO | **3.3 V** — all GPIO, USB, HSTX IO banks |
| Decoupling | **100 nF × every IOVDD/DVDD pair** + **10 µF bulk** near chip ([BOM-3v3.md](../../BOM-3v3.md) #41 pattern) |

**Estimated load:** RP2354B + SD + HDMI + USB host peaks **~300–450 mA** at 3.3 V — size LDO ≥ **600 mA**.

### 9.2 Clock sources

| Source | Use |
|--------|-----|
| Internal ROSC / XOSC | RP2354B system clock — **12 MHz crystal recommended** on `XIN`/`XOUT` for USB |
| `CLK_IN` (2 MHz) | Mailbox sample — **async to USB/HSTX**; use synchronizers |

### 9.3 Reset

| Signal | Implementation |
|--------|----------------|
| `RUN` | 10 kΩ pull-up, tactile reset, 100 nF debounce |
| Power-on | RC delay if USB VBUS ramp slow |

---

## 10. PCB guidelines

| Topic | Guideline |
|-------|-----------|
| Layers | **4-layer** preferred: SIG–GND–PWR–SIG (HSTX + USB impedance control) |
| HSTX / TMDS | Controlled **100 Ω** differential where possible; keep traces short to HDMI connector |
| USB | **90 Ω** differential D+/D−; ESD near connector |
| Mailbox bus | Group `D[7:0]` + `A[7:0]` equal length ±5 mm; ground return under connector |
| SD SPI | ≤ 50 mm traces; series 33 Ω on CLK optional |
| Thermal | QFN-80 exposed pad — **stitch vias** to GND plane |
| Debug | **2×3 SWD** + **1×4 UART** on board edge |

**Form factors:**

1. **Daughterboard** — 50×50 mm, mounts beside breadboard CPU, 2×10 to CPU mailbox tap.
2. **Mezzanine** — stacks on 3.3 V CPU PCB via FFC.

---

## 11. Firmware architecture

### 11.1 Core split (normative)

| Core | Responsibilities |
|------|------------------|
| **Core0** | Mailbox GPIO/PIO handler · vFDD SPI · TinyUSB HID · APU PWM mix · `MB_STATUS` updates |
| **Core1** | VDU text/bitmap compose · HSTX scan-out · `VDU_VSYNC` / frame flip |

Inter-core: **FIFO + shared mailbox shadow** in SRAM; Core0 sets VDU “dirty” flags; Core1 consumes.

### 11.2 Boot

RP2354B boots from **internal 2 MB flash** — no external QSPI. UF2 or `picotool` programming over USB bootloader.

### 11.3 Build / SDK

- **Pico SDK 2.x** (RP2350 family)
- Target: `RP2354B`
- UF2 name / board ID: define in `boards/plover_copro/` (TBD)

---

## 12. BOM sketch (copro board only)

| Ref | MPN / description | Qty | Notes |
|-----|-------------------|-----|-------|
| U1 | **RP2354B** QFN-80 | 1 | 2 MB internal flash |
| U2 | AP2112K-3.3 or MP2359 buck | 1 | ≥600 mA |
| J1 | USB-C receptacle | 1 | Power + USB device boot |
| J2 | USB-A receptacle | 1 | HID host |
| J3 | HDMI Type-A or DVI-D | 1 | HSTX output |
| J4 | microSD socket | 1 | Push-push |
| J5 | Copro header 2×10 | 1 | To CPU |
| J6 | SWD 2×3 | 1 | Debug |
| J7 | 3.5 mm audio jack | 1 | APU |
| Y1 | 12 MHz crystal | 1 | USB stability |
| Passives | 100 nF, 10 µF, 33 Ω, 10 kΩ | per decoupling table | |
| Analog | RC low-pass for PWM | 1 set | Tune on bench |

Full integration BOM: [BOM-3v3.md](../../BOM-3v3.md) #40–41 when merged onto CPU PCB.

---

## 13. Verification and bring-up

Aligned with [M4b-boot-hardware.md](../hw-bringup/M4b-boot-hardware.md):

| Gate | Test | Pass criteria |
|------|------|---------------|
| **P1** | RP2354B powers, SWD attach | ID OK, UART banner |
| **P2** | Mailbox loopback (CPU absent) | Firmware writes/reads shadow regs |
| **G3** | CPU `CMD_READ` sector 0 | RAM `$0800` matches fixture; `MB_STATUS` Idle |
| **G4** | Boot `JMP $0800` + pre-init | SP/RP/GPR per [boot-jmp-handoff.md](../boot/boot-jmp-handoff.md) |
| **V1** | HDMI | 640×480 stable; 40×25 text |
| **A1** | APU | 1 kHz on scope |
| **H1** | HID | `KEY`/`MOUSE?` smoke via USB |

Simulation cross-check:

---

## 14. Open items (TBD)

| ID | Item | Owner |
|----|------|-------|
| T1 | Final GPIO pin lock + `hw/copro/rp2354b.pin` | HW |
| T2 | Mailbox sampling: GPIO bit-bang vs **PIO** SM | FW |
| T3 | 512 B sector multi-transfer tail 16 B encoding | FW / protocol |
| T4 | Mode A 5 V control-line level strategy | HW |
| T5 | USB host power budget vs bus-powered copro | HW |
| T6 | KiCad sheet + net names ↔ [hw-schematic.md](../hardware/hw-schematic.md) convention | HW |
| T7 | Core1 HSTX mode line-up (DVI vs HDMI level shifter) | HW |

---

## 15. Document index

| Need | Document |
|------|----------|
| Register map / commands | [mailbox-protocol.md](mailbox-protocol.md) |
| Video timing | [display-console.md](display-console.md) |
| Audio | [audio-apu.md](audio-apu.md) |
| Input | [input-hid.md](input-hid.md) |
| Storage API | [virtual-fdd.md](virtual-fdd.md) |
| Copro contract (short) | [rp2350-coprocessor.md](rp2350-coprocessor.md) |
| CPU memory map | [memory-map.md](../hardware/memory-map.md) |
| Boot gates | [M4b-boot-hardware.md](../hw-bringup/M4b-boot-hardware.md) |
| Firmware stub | [`firmware/rp2350/mailbox_stub/main.c`](../../firmware/rp2350/mailbox_stub/main.c) |
