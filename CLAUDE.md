# RA Roto Control — Project Guide (CLAUDE.md)

Networked analog motor-speed controller for **Radiant Atmospheres**. Bridges show-control
protocols (physical DMX512, Art-Net, sACN/E1.31) to a **0–5V analog command** driving a
**Roboteq HDC2450** brushed-DC motor controller, with a web interface for setup, DMX persona
selection, network config, live troubleshooting, and manual override.

Spiritual sibling of **raDMX** (`~/temp/raDMX`) — reuse its patterns: ESPAsyncWebServer
dashboard, DMX persona system, WebSocket telemetry, PlatformIO build targets, OTA.

---

## Locked Decisions (do not re-litigate without cause)

| Decision | Choice | Why |
|----------|--------|-----|
| **Compute host** | Olimex **ESP32-POE-ISO** | Wired Ethernet + PoE + galvanic isolation on one cable; instant boot; watchdog recovery; robust flash (no SD); reuses raDMX. |
| **Motor controller** | Roboteq **HDC2450** (2×150A) | Existing hardware. We use **1 channel** (Motor 1). |
| **Command interface** | **Single 0–5V analog line → AnaCmd1 (DB25 pin 4)** | Datasheet: one analog line does speed **and** direction via center-point (0V=full rev, 2.5V=stop, 5V=full fwd). No separate dir/enable wire needed. |
| **DAC** | **MCP4725** 12-bit I2C @ 3.3V | Native ESP32 DAC (GPIO25/26) is consumed by the Ethernet RMII bus. 12-bit (4096 steps) is 16× finer than native 8-bit — critical for smooth ultra-slow modes. |
| **Analog gain** | Op-amp non-inverting, gain ≈ **1.515** (0–3.3V → 0–5V) | Ref/supply from HDC2450 **5VOut** (DB25 pin 14/25) so full-scale is ratiometric to the controller's own 5V. |
| **Grounding** | Single-point tie: ESP GND = MCP4725 GND = op-amp GND = HDC2450 **DB25 GND (pin 5)** | Datasheet Note 6: do **not** create a second ground path to battery minus. PoE isolation lets ESP ground float to this reference. |
| **Command scaling** | Firmware **personas** (voltage-span compression) + live **web multiplier** | Full-range, half-range, quarter-range ultra-slow modes. See `docs/PERSONAS.md`. |

**Rejected:** Native ESP32 DAC (Ethernet pin conflict). Raspberry Pi host (SD-corruption/boot/isolation
risks in festival deployment; overkill for one motor). 0–10V stage (HDC2450 is 0–5V).

---

## Hardware Signal Chain

```
DMX512 (RS485) ─┐
Art-Net ────────┼─► ESP32-POE-ISO ─I2C─► MCP4725 ─► Op-amp (×1.515) ─► AnaCmd1 (pin 4) ─► HDC2450 ─► Motor
sACN/E1.31 ─────┘        │                (0–3.3V)      (0–5.0V)              │
                         └─ ADC sense ◄── ÷2 divider ◄── (op-amp output tap)  │
                                                                    GND ref = DB25 pin 5
```

Full pinout, BOM, wiring diagram, and electrical validation: **`docs/HARDWARE.md`**.

---

## Operational Rules

- **PlatformIO + Arduino-ESP32**, C++. Match raDMX conventions. Never `npm`/`npx` for firmware.
- **Verify GPIO assignments against the specific Olimex board revision schematic before soldering.**
  Ethernet RMII owns GPIO 0, 12, 18, 19, 21, 22, 23, 25, 26, 27 — never reuse these.
- **Hardware first**: confirm wiring with a multimeter (continuity, then 0/2.5/5V at AnaCmd1 with
  motor power OFF) before trusting firmware. (Hard-won lesson: crossed wires waste days of firmware debugging.)
- **Motor safety**: in analog mode the HDC2450 **holds the last commanded voltage** if the ESP32 hangs —
  its command-loss watchdog only guards *serial*. So: firmware watchdog + a defined **fail-safe voltage**
  (command 2.5V = stop on boot/link-loss/fault) are mandatory, not optional.
- **Never command motor power during bench validation** until the analog chain is scope/meter-verified.
- Keep files under 500 lines. Docs in `docs/`, firmware in `firmware/`, no working files in root.

## Build & Test

```bash
# From firmware/ (once scaffolded)
pio run -e olimex_poe_iso            # build
pio run -e olimex_poe_iso -t upload  # flash
pio device monitor                   # serial console
```

## Project Status

**Phase 0 — Planning & validation (current).** Decisions locked, docs written, wiring validated on paper.
Next: bench-prototype the analog chain (MCP4725 + op-amp) and meter-verify 0/2.5/5V before any firmware
motor command. See `docs/ARCHITECTURE.md` → Roadmap.
