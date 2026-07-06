# RA Roto Control

Networked motor-speed controller for **Radiant Atmospheres**. Show-control protocols
(**DMX512, Art-Net, sACN/E1.31**) feed an **ESP32-POE-ISO** that translates them to **RS232 serial**
commands driving a **Roboteq HDC2450** brushed-DC motor controller — with a web interface for setup, DMX
personas, network config, live telemetry, and manual override. Sibling project to [raDMX](../raDMX).

**Everything drives the motor over serial** — and it has proven to be an excellent control interface.
One signed command (`!G 1 <-1000..+1000>`) is speed *and* direction, the controller's own command-loss
watchdog self-stops the motor if the sender goes silent, and it streams back real telemetry (amps,
volts, temp, faults) — all with **no DAC, op-amp, or calibration**. That's why the whole design
converges on one path:

```
DMX512 / Art-Net / sACN ─► ESP32-POE-ISO ─► RS232 serial (!G) ─► HDC2450 ─► roto motor
```

The [host control console](tools/roto-bench/README.md) already drives that serial link on real hardware;
the ESP32 is the networked front-end that will feed the same serial path (a follow-up, pending parts).

## What it does

```
DMX512 / Art-Net / sACN ─► ESP32-POE-ISO ─► MAX3232 ─► RS232 ─► HDC2450 ─► roto motor
                                │  ◄── telemetry (amps, volts, temp, faults) ──┘
                                └──── web UI: config · personas · override · diagnostics
```

- **One motor**, commanded over serial: `!G 1 <-1000..+1000>` — one signed value is speed **and**
  direction (0 = stop). No DAC, no op-amp, no calibration.
- **DMX personas** incl. **ultra-slow modes** (compressed command ranges) + a live **multiplier**.
  See [`docs/PERSONAS.md`](docs/PERSONAS.md).
- **Wired Ethernet + PoE + galvanic isolation** (Olimex ESP32-POE-ISO) for rugged festival deployment.
- **Layered fail-safe** — the HDC2450's own `^RWD` command-loss watchdog stops the motor if the ESP32
  goes silent (works on serial, unlike analog), backed by firmware STOP + slew limiting.
- **Real telemetry** — motor amps, battery voltage, temperature, and fault flags in the web dashboard.

## Hardware

- **Host:** Olimex ESP32-POE-ISO
- **Motor controller:** Roboteq HDC2450 (Motor 1 channel)
- **Link:** ESP32 UART → MAX3232 → HDC2450 RS232 (DB25 pins 2/3), shared ground on pin 5
- **Optional:** KF0602D SSR for remote power-enable; MAX485 + XLR for physical DMX512 input

Full pinout, wiring diagram, BOM, and bring-up checklist: [`docs/HARDWARE.md`](docs/HARDWARE.md).

## Firmware

PlatformIO + Arduino-ESP32. Serial control core, Art-Net/sACN parsers, layered fail-safe, and a minimal
async web dashboard — **compiles clean** for the ESP32-POE-ISO (RAM 13.6%, Flash 67.9%).

```bash
cd firmware
pio run -e olimex_poe_iso            # build
pio run -e olimex_poe_iso -t upload  # flash
```

## Host tools (bench / bring-up)

Python tools that talk to the HDC2450 directly over USB — no ESP32 required — for commissioning and
bench control. Require `pyserial`.

- **[`tools/roto-setup/`](tools/roto-setup/)** — config tool. Read (`--audit`) or write + verify
  (`--apply`, RAM by default) controller configuration from JSON manifests. **Config-only: never issues a
  motor command.** As-found config catalogs live under `captures/`.
- **[`tools/roto-bench/`](tools/roto-bench/)** — a localhost web **control console** (`roto_bench.py` +
  `ui.html`). Drives Motor 1 over serial with named run modes (**JOG / CRUISE / DRIFT / HOLD**, DRIFT =
  auto slow-sweep patterns), layered safety (arm gate, command cap + slew, browser deadman, E-STOP,
  **overcurrent/stall + temperature + I²t auto-trip**, **control-drift detection**), live telemetry +
  motion/load graphs + alerts, and an Advanced live profile editor. **Also a viable standalone run-time
  control path** for a self-contained piece — see [`tools/roto-bench/README.md`](tools/roto-bench/README.md).

```bash
pip install pyserial
python3 tools/roto-setup/roto_setup.py --audit      # read controller config (safe)
python3 tools/roto-bench/roto_bench.py              # web console at http://127.0.0.1:8791
```

> **Safety:** the bench console commands a real 2×150 A motor controller. Power the motor from a
> current-limited supply, keep the controller's hardware E-stop reachable, and read
> [`tools/roto-bench/`](tools/roto-bench/) before first use.

## Docs

| Doc | Contents |
|-----|----------|
| [`CLAUDE.md`](CLAUDE.md) | Project guide, locked decisions, operational rules |
| [`docs/HARDWARE.md`](docs/HARDWARE.md) | Pinout, MAX3232 wiring, BOM, bring-up checklist |
| [`docs/PERSONAS.md`](docs/PERSONAS.md) | DMX persona definitions + command scaling |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Firmware module map, protocols, safety model, roadmap |

## Status

**Serial control + safety proven on hardware — via the host console.** Motor 1 runs over `!G` from the
[control console](tools/roto-bench/README.md) with a 5 A current limit and layered auto-trip protection
(overcurrent/stall, temperature, I²t) plus control-drift detection. Telemetry, `ALIM`/`ATGA` config, and
the `^RWD` watchdog are all validated. The legacy DMX→analog rig is reverse-engineered in
[`docs/LEGACY-WIRING.md`](docs/LEGACY-WIRING.md).

The **ESP32-POE-ISO firmware** (the product — adds Ethernet/PoE + DMX/Art-Net/sACN) compiles clean;
next step is porting the proven console logic into firmware. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
