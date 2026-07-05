# Hardware — Wiring, BOM & Electrical Validation

Target host: **Olimex ESP32-POE-ISO**. Motor controller: **Roboteq HDC2450** (using Motor 1 channel only).

---

## 1. HDC2450 interface facts (from datasheet v1.2)

| Fact | Value | Source |
|------|-------|--------|
| Analog command range | **0–5V** | Features List p.1; command modes "0-5V Analog" |
| Analog command → motor | **Center-point**: 0V = full reverse, 2.5V = stop, 5V = full forward | "Full forward & reverse… Selectable min, max, center and deadband in Analog modes" |
| Absolute max on any signal pin | 15V (don't exceed) | Table 6, Absolute Maximum Values |
| Regulated 5V output | DB25 **pin 14** and **pin 25** (5VOut) | Table 4 |
| Analog command default pins | **AnaCmd1 = DB25 pin 4 (ANA3)**, AnaCmd2 = pin 17 (ANA4) | Table 4, Default Config |
| Ground pins (DB25) | pins **1, 5, 9, 13** | Table 4 |
| Command priority (auto-arbitrated) | RS232 → RC Pulse → **Analog** | "Default I/O Configuration" |
| Power Control (enable) wire | Yellow wire, 0–65V; ON = apply VBat via SW1 switch | Fig 9, "Power Wires" |
| Command-loss watchdog | **Serial only** — analog holds last voltage | Features List |
| RS232 telemetry | DB25 pin 2 (TxData) / pin 3 (RxData), true RS232 levels | Table 4 |

> **Config note:** For a **unidirectional** roto (spin one way only) set min/center in Roborun+ so
> 0–5V = 0–100% forward, giving full DAC resolution across the whole speed band. For **bidirectional**
> keep the 2.5V center default. Persona math in `docs/PERSONAS.md` supports both.

---

## 2. ESP32-POE-ISO pin plan

**Ethernet RMII reserves — NEVER reuse:** GPIO 0, 12, 18, 19, 21, 22, 23, 25, 26, 27.

| Function | GPIO | Notes |
|----------|------|-------|
| I2C SDA → MCP4725 | **GPIO13** | Olimex UEXT standard. Verify against board rev. |
| I2C SCL → MCP4725 | **GPIO16** | Olimex UEXT standard. Verify GPIO16 free on your rev. |
| Command-voltage sense (ADC1) | **GPIO36** (SENSOR_VP) | Reads op-amp output via ÷2 divider (0–5V→0–2.5V). Input-only, fine. |
| DMX512 input (RS485 RO) | **GPIO35** | Input-only; UART RX via matrix. MAX485 DE/RE tied to receive. |
| Status LED | **GPIO33** | Not a strapping pin — safe. |
| PwrCtrl relay (optional) | **GPIO32** | Drives relay coil; contacts switch VBat→PwrCtrl wire. |
| E-stop / deadman input (optional) | **GPIO39** | Input-only; external pull-up; maps to HDC2450 DIN or firmware hold. |
| RS232 telemetry (Phase 2) | TX **GPIO14** / RX **GPIO15** | Through MAX3232 to DB25 pin 2/3. Read-only queries. |

> Strapping pins to treat with care: GPIO0, 2, 5, 12, 15. We only use GPIO15 for optional Phase-2
> RS232 RX; keep it floating-safe at boot.

---

## 3. Analog output stage — MCP4725 + op-amp

**Goal:** 12-bit code → clean 0–5.000V into AnaCmd1, referenced to the HDC2450's own 5V.

- **MCP4725** powered at **3.3V** (I2C logic-clean with a 3.3V ESP32). Output span **0–3.3V**, 4096 codes,
  ≈ 0.806 mV/code.
- **Op-amp**, non-inverting, gain **G = 5.0 / 3.3 = 1.515**.
  - `G = 1 + Rf/Rg` → `Rf/Rg = 0.515`. Use **Rf = 5.1 kΩ, Rg = 10 kΩ** → G = 1.51 → 3.30V × 1.51 = **4.98V** max.
  - Trim exact full-scale in firmware by capping the DAC max code (see calibration below).
- **Op-amp supply & reference = HDC2450 5VOut (pin 14/25).** Full-scale is then ratiometric: even if
  5VOut = 4.95V, our max command = 4.95V = "full speed" as the controller interprets it. Elegant and drift-proof.
- Use a **rail-to-rail I/O (RRIO)** op-amp: **MCP6002 / MCP6L92 / OPA340 / TLV9061**. The HDC2450 analog
  input is high-impedance, so the op-amp drives near-zero load and reaches within a few mV of the rail.
- **Output conditioning:** ~**1 kΩ series** resistor + **100 nF** to GND at the op-amp output (RC ≈ 100 µs)
  for glitch/EMI suppression and to protect against accidental shorts. Optional Schottky clamp to the 5V rail.

**Command-voltage sense (troubleshooting feedback):**
Tap the op-amp output through a **÷2 divider (10 kΩ / 10 kΩ)** into **GPIO36 (ADC1)**. The web UI then
shows the **measured** commanded voltage, not just the intended value — closes the loop for diagnosis.

### DAC upgrade path
The op-amp input stage is **0–3.3V-agnostic**. If more resolution ever helps, an external 16-bit DAC
(e.g. DAC8563) drops in with no gain-stage change.

---

## 4. Grounding architecture (critical)

```
        ┌──────────── PoE (isolated) ──────── network switch
        │
   ESP32-POE-ISO  ──GND──┐
        │                │
   MCP4725 GND ──────────┤   single-point signal ground
   Op-amp GND ───────────┤
        │                │
   HDC2450 DB25 GND (pin 5) ◄── the ONE tie point
```

- ESP32 is **PoE-powered and galvanically isolated** from the network, so its ground is free to reference
  the HDC2450 signal ground.
- **Tie all signal grounds to DB25 pin 5 only.** Per datasheet **Note 6**, do NOT run a second ground wire
  from the I/O connector to the battery minus terminal — that creates a ground loop through the motor
  power path (2×150A) and injects noise/hazard into the command line.
- If the optional PwrCtrl relay is used, its **contacts** (switching VBat→Yellow wire) are isolated from the
  ESP by the relay coil — no shared high-current ground.

---

## 5. Wiring diagram (bench prototype, motor power OFF for validation)

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  Olimex ESP32-POE-ISO                                                      │
 │                                                                           │
 │  GPIO13 (SDA) ──────────┐                                                 │
 │  GPIO16 (SCL) ────────┐ │                                                 │
 │  3V3 ───────────────┐ │ │        ┌──────────────┐                        │
 │  GND ─────────────┐ │ │ │        │   MCP4725     │                        │
 │  GPIO36 (ADC)◄──┐ │ │ │ └─SCL──► │  (Vdd=3.3V)   │                        │
 │                 │ │ │ └───SDA──► │              │                        │
 │                 │ │ └─────Vdd──► │  Vout ───────┼──┐                     │
 │                 │ └───────GND──► │  GND ──┐     │  │  0–3.3V             │
 │                 │                └────────┼─────┘  │                     │
 │                 │                         │        ▼                     │
 │                 │                    ┌────┴────────────────┐             │
 │                 │  ÷2 divider        │  Op-amp (RRIO)       │             │
 │                 └──[10k]──┬──[10k]──►│  +in  Vout ──[1k]──┬─┼──► DB25 pin 4 (AnaCmd1)
 │                          GND         │  Rg=10k  Rf=5.1k    │ │            │
 │                                      │  V+ = 5VOut(pin14)  │ [100nF]      │
 │                                      │  GND = DB25 pin 5   │ │            │
 │                                      └─────────────────────┘ GND         │
 │                                                                          │
 │  DB25 pin 5 (GND) ◄──────── single-point signal ground ─────────────────┤
 │  DB25 pin 14 (5VOut) ─────► op-amp V+ / reference                        │
 └──────────────────────────────────────────────────────────────────────────┘

 Optional / Phase 2:
   GPIO32 ─► S8050 ─► KF0602D SSR ─► [VBat → SW1 → SSR → HDC2450 Yellow PwrCtrl]  (remote enable, see §7)
   GPIO14/15 ─► MAX3232 ─► DB25 pin 2/3 (RS232 telemetry: amps, volts, temp, faults)
   GPIO35 ◄─ MAX485 ◄─ DMX512 XLR (physical DMX input)
```

A rendered/visual version of this diagram is available as an Artifact (see project chat).

---

## 6. Bill of Materials (control side)

| Qty | Part | Purpose | Have on hand? |
|-----|------|---------|---------------|
| 1 | Olimex ESP32-POE-ISO | Compute host + Ethernet/PoE | ✅ yes |
| 1 | Roboteq HDC2450 | Motor controller | ✅ yes |
| 1 | MCP4725 breakout (I2C DAC) | 12-bit analog out | ~$1, order |
| 1 | **MCP6002** op-amp (RRIO, DIP-8) | 0–3.3V → 0–5V gain — **must be rail-to-rail output** | order |
| 2 | 10 kΩ resistor | op-amp Rg (1) + divider (pair uses 2 more) | ✅ |
| 1 | 5.1 kΩ resistor | op-amp Rf | ✅ |
| 3 | 10 kΩ resistor | ÷2 sense divider + spare | ✅ |
| 1 | 1 kΩ resistor | output series | ✅ |
| 1 | 100 nF cap | output RC / decoupling | ✅ |
| 1 | DB25 male solder connector + hood | HDC2450 I/O plug | order |
| — | PoE switch/injector (802.3af) | power the Olimex | ✅ likely |
| 1 | **KF0602D** DC-DC SSR (Kyotto; 3–32V in, 3–60V/2A isolated out) | remote PwrCtrl enable (§7) | ✅ yes |
| 1 | **S8050** NPN | buffers SSR input at 5V for margin (§7) | ✅ yes |
| 1 | MAX3232 module (Phase 2) | RS232 telemetry | ✅ bin |
| 1 | MAX485 module (optional) | physical DMX512 input | ✅ bin |

---

## 7. Power-enable (PwrCtrl) via KF0602D SSR — optional, recommended

Lets the ESP32 (and E-stop logic) power the HDC2450 on/off remotely. The **KF0602D** is a Kyotto
KF06-series DC-DC SSR: control **3–32VDC** (1.5 kΩ input), isolated output **3–60VDC / 2A**, 80V
blocking. Isolation keeps the battery/motor domain off our signal ground. HDC2450 idle draw (~150mA @
≤50V) sits far inside the 2A/60V rating — **no heatsink needed** at that current.

**Drive the SSR input from 5V (not 3.3V) for margin.** The KF0602D's 3V control minimum is barely
below a GPIO's 3.3V — fine on the bench, marginal in the field. Buffer it with the **S8050**:

```
  5VOut (pin14) ──► SSR IN(+)
                    SSR IN(−) ──► S8050 collector
  GPIO32 ──[1kΩ]──► S8050 base      (10kΩ base→GND pulldown = off at boot)
                    S8050 emitter ──► signal GND (DB25 pin5)
```
GPIO high → S8050 saturates → ~5V across the SSR input (~3.3mA) → SSR closes.

**Output side (two-layer safety):** keep the mandatory manual **SW1** as master cutoff; put the SSR
**in series** with it on the Yellow wire:
```
  VBat(+) ──► SW1 ──► SSR OUT ──► HDC2450 Yellow / PwrCtrl
```
Controller powers up only when **SW1 closed AND ESP asserts the SSR**. ESP dead/reset → SSR opens →
controller powers down (motor coasts). Paired with the 2.5V fail-safe command = belt-and-suspenders.

**Startup sequence (firmware):** boot → DAC to fail-safe 2.5V (stop) → *then* close SSR to power the
controller, so it reads "stop" the instant it wakes.

---

## 8. Electrical validation checklist

Do these **in order**, motor power **OFF** until step 6:

1. **Continuity** (multimeter): confirm each control wire end-to-end — DAC Vout→op-amp +in, op-amp
   Vout→DB25 pin 4, all grounds→DB25 pin 5, 5VOut(pin14)→op-amp V+. Rule out crossed wires **first**.
2. **Power the Olimex via PoE**; confirm 3.3V rail and I2C ACK from MCP4725 (`i2cdetect`-style scan in firmware).
3. **Power the HDC2450** (SW1 on); confirm **5VOut = ~5.0V** at DB25 pin 14 relative to pin 5.
4. **DAC sweep**: command codes 0 / 2048 / 4095 → meter op-amp output at DB25 pin 4. Expect
   **~0.00V / ~2.50V / ~4.98V**. Record actuals for calibration.
5. **Calibrate** in firmware: set `DAC_MAX_CODE` so full-scale reads exactly 5.000V; set `DAC_STOP_CODE`
   so stop reads exactly 2.500V (bidirectional) — verify against the sense ADC (GPIO36) and the meter agree.
6. **Fail-safe check**: confirm boot, Ethernet-link-loss, and watchdog-reset all drive the **stop voltage**
   (2.5V bidirectional, or configured 0-speed) before enabling motor power.
7. **Only now** connect motor power and verify a gentle low-speed command turns the roto the expected direction.

> Expected max ≈ 4.98V (not a clean 5.00V) is by design — trimmed in firmware, and Roborun+ "max" can be
> set slightly under 5V so the last few mV of op-amp rail are never needed.
