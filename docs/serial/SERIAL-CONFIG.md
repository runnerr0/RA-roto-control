# HDC2450 Serial — Config, Libraries & ESP32-over-Serial

Compiled notes for the serial track: the Roboteq ASCII protocol, the host-side
config tool, a survey of existing libraries we can borrow from, and a worked
design for **optionally adding an ESP32↔HDC2450 serial link**.

Raw research log: [`raw/`](./raw/). House rules from `CLAUDE.md` apply.

> **Scope note.** The *runtime motor command* path is and stays **analog**
> (DAC → op-amp → AnaCmd1). Serial enters the picture two ways: (1) a one-time
> **host-side config** tool to commission the controller, and (2) an *optional*
> **ESP32 serial link** for telemetry / config-assert / (maybe) command. Section
> 6 weighs that second one.

---

## 1. Roboteq ASCII protocol cheat-sheet

HDC2450 is an *Advanced Digital Motor Controller*; the whole family shares one
ASCII command set. Link is **115200 baud, 8N1, no flow control**; every command
is terminated with a carriage return (`\r`). The controller **echoes** commands
by default and replies `+` (accepted) or `-` (rejected) to writes.

| Verb | Meaning | Example | Reply |
|------|---------|---------|-------|
| `^`  | **SetConfig** — write a config param (to RAM) | `^ACTR 1 2500` | `+` / `-` |
| `~`  | **GetConfig** — read a config param | `~ACTR 1` | `ACTR=2500` |
| `!`  | RuntimeCommand — motor/output command | `!G 1 500` | `+` / `-` |
| `?`  | RuntimeQuery — live operating value | `?A 1` | `A=...` |
| `%`  | Maintenance | `%EESAV` (save RAM→flash) | — |

Handy queries: `?FID` (firmware id, good "is anyone home?" check), `?A` (amps),
`?V` (volts: internal/battery/5V-out), `?T` (temperature), `?FF` (fault flags),
`?S`/`?BS` (speed), `?AI` (analog inputs).

Key gotchas:
- **Config is RAM-first.** `^` changes are volatile until `%EESAV`. Good — it
  lets us test and power-cycle before committing.
- **Echo on by default.** Parse tolerantly (our tool does) or disable with
  `^ECHOF 1` (itself a config param, so only if you mean to persist it).
- The HDC2450 command-loss **watchdog guards serial only, not analog** — which is
  exactly why the firmware owns the analog fail-safe (see `ARCHITECTURE.md`).

---

## 2. How the HDC2450 presents to a host

- **USB:** enumerates as a native **USB CDC-ACM** device — Linux `/dev/ttyACM*`,
  macOS `/dev/tty.usbmodem*`, **no driver install** on macOS. Not an FTDI chip.
- **RS232:** true ±RS232 levels on the DB25 (`TxOut` / `RxIn`), **not** 3.3V TTL.
  A TTL device (ESP32) needs a **MAX3232**-class level shifter to talk to it.
- **Reliability:** the forum record flags the HDC2450's **USB as EMI-sensitive
  under load** — motor/relay switching can knock the USB link offline. RS232 is
  the more robust link. Fine either way for bench commissioning; matters if we
  make a *permanent* ESP32 serial link (§6).

Refs: Roboteq forum "HDC2450 on linux with usb" (cdc_acm / ttyACM0), "HDC2450
serial communication" (115200 8N1), and the freshdesk "serial communication with
Roboteq controller and Arduino" note (RS232 levels + inversion → needs adapter).

---

## 3. Existing libraries we can borrow from

None is a drop-in for *our* design (we command via analog, and these are mostly
runtime *serial command* drivers). Value is the **serial framing + the config
command semantics** we can crib. All share the ASCII set above; only the specific
config item indices/defaults differ by controller + firmware.

| Project | Lang | Why it's useful here |
|---------|------|----------------------|
| [Miker2808/PyRoboteq](https://github.com/Miker2808/PyRoboteq) (`pip install PyRoboteq`) | Python | Clean pyserial wrapper + command table. Basis for our host tool's framing. Tested on SDC2130/SBL2360T. |
| [brettpac/Roboteq-Linux-API](https://github.com/brettpac/Roboteq-Linux-API) | C++ | Port of Roboteq's own `RoboteqDevice` (SetConfig/GetConfig/SetCommand/GetValue + `sample.cpp`). The authoritative reference for how each `^`/`~` exchange behaves. |
| [rbonghi/roboteq_control](https://github.com/rbonghi/roboteq_control) | C++/ROS | Explicitly manages *all* params, GPIO, and **analog ports** over serial; lists HDC24xx. Best reference for the config side. |
| [g/roboteq](https://github.com/g/roboteq) (`roboteq_driver`) | C++/ROS | Supports HDC24xx; example runs `/dev/ttyACM0 @ 115200` — matches our link exactly. Clean framing reference. |
| [niclaslind/arduino-roboteq](https://github.com/niclaslind/arduino-roboteq) | C++/Arduino | **PlatformIO-ready** (`lib_deps`), matches our firmware stack. Exposes `readConvertedAnalogCommand` — reads back the analog command the controller *actually sees*. Candidate base for a firmware `RoboteqLink` (§6). |

---

## 4. Config parameter map (analog mode)

The concrete param list lives in the tool's manifest:
[`tools/roto-setup/config/hdc2450-analog.json`](../../tools/roto-setup/config/hdc2450-analog.json).

Intent, grouped:

- **Command source:** `CPRI` (priority slots) so **Analog is sole authority**,
  serial left free for telemetry.
- **Analog input shaping:** `AMOD` (mode), `AINA` (action = Motor Cmd ch1),
  `AMIN`/`ACTR`/`AMAX` (mV for reverse/stop/forward), `ADB` (deadband), `APOL`.
- **Motor:** `MMOD` (open-loop), `MXMD` (mix off), `MAC`/`MDEC` (ramps),
  `MDIR` (direction).
- **Protection (set deliberately):** `ALIM` (amps), `OVL`/`UVL` (bus volts).

> Every mnemonic/value there is **DRAFT** until verified against the HDC2450
> config reference. `ACTR=2500` (2.5V stop) should equal the firmware's fail-safe
> voltage; `ADB` should be coordinated with `SafetyStage` so the two deadbands
> don't fight; `MAC`/`MDEC` should be coordinated with the persona/slew limiter so
> the *gentler* ramp governs ultra-slow modes.

---

## 5. Host-side config tool

[`tools/roto-setup/`](../../tools/roto-setup/) — pyserial, config-only, dry-run by
default, verify-on-write, RAM-until-`--save`. See its
[README](../../tools/roto-setup/README.md). This replaces the need to boot RoboRun+
in a Windows VM just to flip the controller into analog mode.

---

## 6. Design: should the ESP32 also talk serial to the HDC2450?

Today the ESP32 only drives the controller through the analog chain. Adding a
serial link is worth reasoning about because it closes two gaps the current design
*names but can't fill from the analog side*: **no controller-side telemetry**
(real amps/temp/faults) and **no controller-side command-loss watchdog**.

### Hardware cost (common to all options)

The DB25 serial port is **RS232**, the ESP32 is **3.3V TTL** → we need a
**MAX3232** (or equiv) level shifter. Two ESP32 GPIOs for UART TX/RX. Reuse the
existing **single-point ground** (DB25 pin 5, already our analog reference) for
the serial ground — no new ground path.

**Pin constraint (hard):** RMII Ethernet owns GPIO 0,12,18,19,21,22,23,25,26,27 —
never reuse. Already spoken for: 35 (DMX RX), 36 (sense ADC), 39 (E-stop),
32 (PwrCtrl), 13/16 (I2C, to confirm). Candidate UART pins **to verify against the
Olimex ESP32-POE-ISO Rev M schematic**: **TX = GPIO33**, **RX = GPIO34** (34 is
input-only, fine for RX; TX must be a full output). Confirm before soldering.

### Options

**Option A — Analog command + serial telemetry/config-assert  *(recommended)***
Keep the locked analog command path. Add serial as a **read-only telemetry** feed
(`?A ?V ?T ?FF ?S`) and an optional **boot-time config-assert** (re-push the
analog-mode config + protection limits over `^`, so a controller that got reset or
mis-flashed comes back known-good without RoboRun+).
- *Pros:* purely additive; doesn't re-open the locked analog decision; serial is
  **not** in the motor-command critical path, so USB/EMI flakiness can't stop the
  motor; directly fills the telemetry gap the `Telemetry`/`Diagnostics` modules
  already pencil in (`ARCHITECTURE.md` Phase 2/5).
- *Cons:* still no controller-side command-loss watchdog (analog command remains
  watchdog-less — firmware fail-safe still mandatory); adds the MAX3232 + 2 pins.

**Option B — Serial *command* (replace the analog chain)**
Drop MCP4725 + op-amp; command with `!G 1 x` (±1000).
- *Pros:* simpler BOM (no DAC, no op-amp gain math, no ratiometric-5V dance);
  digital precision (finer than 12-bit DAC) — nice for ultra-slow; **built-in
  RS232 watchdog** (`RWD`) gives the controller-side command-loss stop the analog
  path lacks.
- *Cons:* **re-opens a locked decision**; serial-under-load reliability risk
  (mitigated by RS232 vs USB, but real); loses the dead-simple isolated single
  analog line; you must *stream* commands within the watchdog window (that's the
  fail-safe working as intended, but it's a behavioral shift); more firmware in
  the motion-critical path.

**Option C — Serial config-only, from the ESP32**
ESP32 does the one-time/occasional config over serial instead of the host tool.
- *Pros:* fewest moving parts *if* you don't want a host laptop at the controller.
- *Cons:* still needs the MAX3232 + pins for a job the host tool already does over
  USB with no added hardware. Low value unless there's a field re-config need.

### Recommendation

**Option A.** It's additive, respects the locked analog command path and the
paper-validated safety story, and it's the highest-value / lowest-risk way to get
real controller telemetry and self-healing config. It also leaves the physical
link in place, so a later A/B of **B** (serial command) is a firmware change, not
a hardware change. If bench testing later shows the analog watchdog gap is
unacceptable, revisit **B** deliberately (it would be a real decision, logged in
`CLAUDE.md`, not a drift).

### Firmware sketch (if we do A)

A `RoboteqLink` module mirroring the existing module style, feeding the existing
`Telemetry` module rather than the command path:

```
UART2 (TX33/RX34) ──MAX3232── DB25 RS232 (TxOut/RxIn, GND=pin5)
        │
   RoboteqLink
     ├─ begin(uart, baud=115200)
     ├─ assertConfig(manifest)   // optional, boot-time ^ + verify (mirrors roto_setup.py)
     ├─ poll()                   // periodic ?A ?V ?T ?FF ?S -> struct
     └─ Telemetry <- {battV, amps, tempC, faultFlags, rpm}
```

- **Read-only by default.** No `!` commands in Option A — the analog chain still
  commands the motor, so a serial glitch degrades telemetry, never motion.
- `readConvertedAnalogCommand` (from the arduino-roboteq lib) is a great
  cross-check: compare what the controller *thinks* its analog command is against
  our `SenseADC` measurement of the op-amp output — a cheap integrity check on the
  whole analog chain.
- Poll slowly (e.g. 5–10 Hz); keep the UART off the RMII pins; share the
  single-point ground.

---

## 7. Open questions / TODO

- [ ] Verify all §4 mnemonics/values against the HDC2450 config reference.
- [ ] Nail down the `AINA` action bitmask encoding (Motor Cmd, ch1).
- [ ] Fill `ALIM`, `OVL`, `UVL` from the actual motor + bus specs.
- [ ] Confirm `%EESAV` needs no safety argument on this firmware rev.
- [ ] Confirm **TX33/RX34** free on the Olimex POE-ISO **Rev M** schematic.
- [ ] Decide A vs B vs C. (Leaning A — telemetry + config-assert, analog stays.)
- [ ] If A: pick a MAX3232 breakout; add serial port to the DB25 hood pinout in
      `HARDWARE.md`.
- [ ] Once decided, add `RoboteqLink` to the `ARCHITECTURE.md` module map and fold
      Phase-2 telemetry into the roadmap explicitly.
