# Hardware — Wiring, BOM & Bring-up

Host: **Olimex ESP32-POE-ISO**. Motor controller: **Roboteq HDC2450** (Motor 1 channel).
Control path: **RS232 serial** via a **MAX3232** level shifter.

---

## 1. HDC2450 serial interface facts (from datasheet v1.2 + Roboteq command set)

| Fact | Value | Source |
|------|-------|--------|
| Serial pins (DB25) | **pin 2 = TxData**, **pin 3 = RxData**, true RS232 levels | Table 4 |
| Ground pins (DB25) | 1, 5, 9, 13 | Table 4 |
| Regulated 5V out | DB25 pin 14 / pin 25 (powers the SSR input, §5) | Table 4 |
| Default baud | 115200, 8N1 (set to match Roborun+) | Roboteq serial spec |
| Speed command | `!G <ch> <-1000..+1000>` — signed: -1000 rev, 0 stop, +1000 fwd | Roboteq command set |
| Command-loss watchdog | `^RWD <ms>` — controller stops motor if silent this long (**serial only**) | Features List |
| Command priority | RS232 → RC → Analog (serial wins) | "Default I/O Configuration" |
| Telemetry queries | `?A` amps, `?V` volts, `?T` temp, `?FF` fault flags, `?S` speed | Roboteq command set |
| Abs max on signal pins | 15V (RS232 pins spec'd for external ±15V) | Table 6 |

> Commands terminate with **CR (`\r`)**. We send `^ECHOF 1` (echo off) at connect for clean reply
> parsing, and `^RWD 500` so the controller self-stops within 500 ms of losing our command stream.

---

## 2. ESP32-POE-ISO pin plan

**Ethernet RMII reserves — NEVER reuse:** GPIO 0,12,17,18,19,21,22,23,25,26,27.

| Function | GPIO | Notes |
|----------|------|-------|
| HDC2450 UART **TX** | **GPIO14** | → MAX3232 T1IN → DB25 **pin 3** (controller Rx). Output-capable, non-strapping. |
| HDC2450 UART **RX** | **GPIO13** | ← MAX3232 R1OUT ← DB25 **pin 2** (controller Tx). Non-strapping. |
| DMX512 input (RS485 RO) | **GPIO35** | Optional physical DMX; input-only, UART RX via matrix. |
| PwrCtrl enable | **GPIO32** | → S8050 → KF0602D SSR (§5). |
| E-stop / deadman | **GPIO39** | Optional; input-only; external pull-up. |
| Status LED | **GPIO33** | Non-strapping. |

Firmware uses **UART1** (`HardwareSerial(1)`) remapped to GPIO13/14. Verify these are free on your
exact Olimex revision before soldering.

---

## 3. Serial link — MAX3232

```
  ESP32 GPIO14 (TX) ──► T1IN   T1OUT ──► DB25 pin 3   (HDC2450 RxData)
  ESP32 GPIO13 (RX) ◄── R1OUT  R1IN  ◄── DB25 pin 2   (HDC2450 TxData)
  ESP32 3V3 ─────────► VCC     GND  ──► signal ground (DB25 pin 5)
                        (4× 100nF charge-pump caps per MAX3232 datasheet)
```
Most MAX3232 breakout modules include the four charge-pump capacitors. Powered at 3.3V from the ESP,
its logic side is 3.3V-clean; its line side drives proper RS232 to the HDC2450.

---

## 4. Grounding

- ESP32 is **PoE-powered and galvanically isolated** from the network; its ground references the
  HDC2450 signal ground.
- **Tie ESP GND ↔ MAX3232 GND ↔ DB25 pin 5 only.** Per datasheet **Note 6**, do NOT run a second
  ground from the I/O connector to battery minus — that creates a ground loop through the 2×150A
  motor power path.
- The optional PwrCtrl SSR (§5) is isolated, so its battery-domain side never touches signal ground.

---

## 5. Power-enable (PwrCtrl) via KF0602D SSR — optional, recommended

Lets the ESP32 (and E-stop logic) power the HDC2450 on/off remotely. **KF0602D**: control 3–32VDC
(1.5 kΩ input), isolated output 3–60VDC / 2A, 80V blocking. HDC2450 idle draw (~150mA @ ≤50V) sits
far inside rating — no heatsink needed.

**Drive the SSR input from 5V (not 3.3V) for margin**, buffered by the **S8050**:
```
  5VOut (pin14) ──► SSR IN(+)
                    SSR IN(−) ──► S8050 collector
  GPIO32 ──[1kΩ]──► S8050 base      (10kΩ base→GND pulldown = off at boot)
                    S8050 emitter ──► signal GND (DB25 pin5)
```
**Output side (two-layer safety):** keep the mandatory manual **SW1** as master cutoff; put the SSR
in series with it: `VBat(+) → SW1 → SSR OUT → HDC2450 Yellow/PwrCtrl`. Controller powers up only when
SW1 closed **and** the ESP asserts the SSR. ESP dead/reset → SSR opens → controller powers down.

---

## 6. Wiring diagram (bench bring-up)

```
 ┌────────────────────────────────────────────────────────────────────────────┐
 │  Olimex ESP32-POE-ISO                    ┌──────────┐                         │
 │                                          │ MAX3232  │                         │
 │  GPIO14 (TX) ───────────────► T1IN ─────►│          │──T1OUT──► DB25 pin 3 ──┐ │
 │  GPIO13 (RX) ◄─────────────── R1OUT ◄────│          │◄─R1IN─── DB25 pin 2 ──┤ │
 │  3V3 ────────────────────────► VCC       │          │                        │ │
 │  GND ────────────────────────► GND ──────┴──────────┴──► DB25 pin 5 (GND) ───┤ │
 │                                                                              │ │
 │                                                              ┌───────────────▼─┐
 │  GPIO32 ─► S8050 ─► KF0602D SSR ─► [VBat→SW1→SSR→Yellow]     │  Roboteq HDC2450 │
 │  GPIO39 ◄─ E-stop (optional)                                 │  M1+/M1- ─► Motor│
 │  GPIO35 ◄─ MAX485 ◄─ DMX512 XLR (optional)                   └──────────────────┘
 └────────────────────────────────────────────────────────────────────────────┘
       Ethernet + power in over one isolated PoE cable (top of the Olimex).
```

A rendered/visual wiring diagram is available as an Artifact (see project chat).

---

## 7. Bill of Materials (control side)

| Qty | Part | Purpose | Have? |
|-----|------|---------|-------|
| 1 | Olimex ESP32-POE-ISO | Compute host + Ethernet/PoE | ✅ |
| 1 | Roboteq HDC2450 | Motor controller | ✅ |
| 1 | **MAX3232** module (w/ charge-pump caps) | ESP UART ↔ HDC2450 RS232 | ✅ bin |
| 1 | DB25 male → screw-terminal breakout | mate the HDC2450 I/O without soldering a bare DB25 | order |
| — | 802.3af PoE switch/injector | power the Olimex | ✅ likely |
| 1 | **KF0602D** DC-DC SSR (Kyotto) | remote PwrCtrl enable (§5) | ✅ |
| 1 | **S8050** NPN + 1kΩ + 10kΩ | buffers SSR input at 5V | ✅ |
| 1 | MAX485 module + XLR | optional physical DMX512 input | ✅ bin |
| 1 | E-stop switch (latching) | optional hardware E-stop | order if wanted |

**No longer on the control path:** MCP4725 DAC, MCP6002 op-amp, gain/sense resistors — the serial pivot
removed the analog stage. Keep the DAC/op-amp for another project.

---

## 8. Bring-up checklist

Do these **in order**, motor power **OFF** until step 6:

1. **MAX3232 wiring** — meter continuity: GPIO14→T1IN, T1OUT→pin3, pin2→R1IN, R1OUT→GPIO13, 3V3→VCC,
   GND→pin5. Confirm caps present on the module.
2. **Power the HDC2450 logic** (SW1 on; VBat ≥ 9V — a bench supply is fine, **motor need not be connected**).
3. **Link check** — from the ESP serial console (or a manual test), send `?FID\r`; expect the firmware
   version string back. This proves TX, RX, ground, baud, and levels all work before any motor command.
4. **Watchdog check** — confirm `^RWD 500` is accepted; stop sending `!G` and verify the controller
   reports command-loss / would stop (it will already be at 0).
5. **Telemetry check** — `?V` / `?T` return sane battery volts and temperature; note the value scaling
   and fix `SerialController::poll()` if the Roboteq units differ from the assumed ×10 (TODO in code).
6. **Motor-in-the-loop** — connect motor power; command a gentle `!G 1 100` (10%) and confirm direction,
   then `!G 1 0` stop, then `!G 1 -100` reverse. Verify slew and e-stop behave.

> The web UI's **override** slider (0=rev, 50=stop, 100=fwd) is the easy way to drive steps 6 by hand.
