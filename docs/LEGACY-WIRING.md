# Legacy Wiring — As-Found (DMX → Analog → HDC2450)

> **Scope: LEGACY ONLY.** This documents the *original, field-modified* control rig as
> physically found on the bench — **not** the new ESP32-POE-ISO serial design (see `HARDWARE.md`).
> The harness was field-stripped/rebuilt at Burning Man and is **suspect**; treat every
> connection here as "observed, needs meter confirmation," not "correct."

---

## 1. Legacy signal chain

```
DMX512 (XLR) ─► Northlight "Decode8" ─► analog voltage (0–5V) ─► HDC2450 DB25 (Main / P1) ─► Motor(s)
                8-ch DMX→0-5/0-10V         + signal ground ─────►
                (externally powered)
```

The Decode8 is an 8-channel DMX-to-analog decoder (Northlight Systems, `Decode8.pdf`). Each
DMX slot → one 0–5V or 0–10V output on a screw terminal, plus a common `G`. This is the analog
command path the project **later rejected** in favor of RS232 serial.

---

## 2. HDC2450 Main connector (DB25 / P1) — orientation

Per datasheet **Figure 11 / Table 4** (HDC2450 Motor Controller Datasheet v1.2):

- The connector is a **DB25**. The **13-pin row is pins 1–13**; the **12-pin row is pins 14–25**.
- Molded corner numbers: **1, 13** (13-pin row ends) and **14, 25** (12-pin row ends).
- **As-viewed on the bench:** 13-pin row on **top**, **pin 1 at the left**. Then:
  - Top row, left→right: `1, 2, 3, 4 … 13`
  - Bottom row, left→right: `14, 15, 16 … 25`
- **Cross-check that locks orientation:** the single wired top-row pin is 4th from the left =
  **pin 4 = AnaCmd1** (analog command, Motor 1). A DMX→analog rig driving Motor 1 must use pin 4,
  so the orientation is confirmed by function, not just by counting.

### Relevant HDC2450 DB25 pins (Table 4)

| Pin | Function (default) | Notes |
|-----|--------------------|-------|
| 1, 5, 9, 13 | **Ground** | the ONLY grounds on the connector; all in the 13-pin row |
| 2 | RS232 **TxData** | serial (telemetry path in new design) |
| 3 | RS232 **RxData** | serial |
| **4** | **AnaCmd1** — analog cmd, Motor 1 | also RC3 / ANA3 / DIN3 |
| 14, 25 | **+5V Out** | 200 mA total budget; NOT a ground |
| 15 | RCRadio1 | also RC1 / **ANA1** / DIN1 |
| 16 | RCRadio2 | also RC2 / **ANA2** / DIN2 |
| **17** | **AnaCmd2** — analog cmd, Motor 2 | also RC4 / ANA4 / DIN4 |

Absolute max on any analog/digital signal pin: **15V** (Table 6). Analog input usable range:
**0–5.1V** (Table 8). → the Decode8 **must** be jumpered to its **0–5V** range (J2 closed), never 0–10V.

---

## 3. As-found wiring (traced 2026-07-05) — CONFIRMED

Harness traced from the **Decode8 output terminals** (screw terminals 1–8 + `G`) to the HDC2450 DB25:

| Decode8 output terminal | → DB25 pin | HDC2450 function (default) |
|-------------------------|-----------|----------------------------|
| **2** | **15** | ANA1 (RCRadio1) |
| **3** | **16** | ANA2 (RCRadio2) |
| **4** | **4**  | **AnaCmd1 → Motor 1** |
| **5** | **17** | **AnaCmd2 → Motor 2** |
| **G** (bottom terminal) | *loose — not landed* | **analog common → belongs on DB25 pin 5 (GND)** |

### Findings

1. **The loose wire = Decode8 `G`, the single analog common for all 8 outputs.** With it
   disconnected, **all four analog inputs float** — the controller has no 0V reference, so every
   command is meaningless. **This is the failure.** *Fix: land Decode8 `G` on **DB25 pin 5**.* One
   wire references all four signals; correct single-point ground (Decode8 is externally powered /
   isolated → no ground loop; consistent with datasheet Note 6).
2. **Both analog-command inputs are driven** — out 4 → pin 4 (AnaCmd1, Motor 1) and out 5 → pin 17
   (AnaCmd2, Motor 2). This is a **two-motor** analog rig.
3. **⚠ Config caveat for pins 15/16 (out 2/out 3).** These are **ANA1/ANA2**, which default to
   **RC-radio** inputs and are **ignored in analog mode** unless the stored controller config
   assigns them an action. So out 4 / out 5 are the real motor commands; out 2 / out 3 are either
   vestigial or depend on a non-default config. Read `~AINA` / `~CPRI` over serial to confirm what
   the controller actually does with ANA1/ANA2 before assuming they matter.

### Bring-back-to-life order
1. Land Decode8 `G` → DB25 **pin 5**.
2. Confirm Decode8 jumpers **J2 closed (0–5V)**, **J3 open (proportional)** — see §4.
3. Power up unloaded, e-stop reachable (§4 fail-safe warning).
4. Drive Decode8 **ch 4** → Motor 1, **ch 5** → Motor 2 should respond.

---

## 4. Decode8 jumper settings required for this to be safe/correct

From `Decode8.pdf`:

| Jumper | Set to | Why |
|--------|--------|-----|
| **J2** | **Closed = 0–5V** | HDC2450 analog input maxes at ~5V; 0–10V would overrange/damage |
| **J3** | **Open = Dim/proportional** | Closed = relay snap (stop-or-full only); motor needs proportional |
| **J1** | signal-loss behavior — see ⚠ | Open = decays to 0V; Closed = holds last value |

**⚠ Fail-safe gap (inherent to the analog path):** with center-stop mapping
(`0V = full reverse, 2.5V = STOP, 5V = full forward`), **0V is NOT stop — it is full reverse.**
So on DMX loss: J1-open → decoder drives 0V → **full reverse**; J1-closed → **holds last command**.
*Neither Decode8 mode produces a clean stop.* The HDC2450 `^RWD` command-loss watchdog guards the
**serial** port only, not the analog line. This is exactly why the project pivoted to serial. On the
bare legacy rig, keep the motor unloaded and an e-stop reachable — a yanked DMX cable does not stop it.

---

## 5. Verify before trusting (MOTOR POWER OFF)

Buzz continuity from each DB25 pin to the Decode8 screw terminals and record the real map:

- [ ] pin 4  → which Decode8 output channel? (= Motor 1 command)
- [ ] pin 17 → which Decode8 output channel? (confirms dual-motor)
- [ ] pins 15/16 → decoder outputs, or jumpered to decoder `G`?
- [ ] **floating wire → trace far end.** If it lands on Decode8 `G`, it is the missing analog
      ground → terminate on **DB25 pin 5**.
- [ ] Confirm Decode8 jumpers: **J2 closed (0–5V)**, **J3 open (proportional)**.
- [ ] Note the DMX start address set on the decoder.

### Chain integrity check (with serial console attached)
`?AI 1` and `?AI 2` report the mV the controller sees on each analog input. Feed a mid DMX level
(~2.5V expected) and confirm `?AI` tracks the meter — that proves DMX byte → decoder → DB25 → input.

---

## Sources
- Roboteq **HDC2450 Motor Controller Datasheet v1.2** (Jul 20 2010): Figure 11 (connector pin
  locations), Table 4 (Main connector pinout), Table 6 (abs max), Table 8 (I/O signal specs).
- Northlight Systems **8-Channel DMX-to-0–10V Decoder** manual (`docs/Decode8.pdf`).
- Project: `docs/HARDWARE.md`, `docs/serial/SERIAL-CONFIG.md`, `tools/roto-setup/config/hdc2450-analog.json`.
