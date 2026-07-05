# roto-setup — HDC2450 serial config tool

Host-side (macOS/Linux) utility that commissions the **Roboteq HDC2450** into
**analog-command mode** for RA Roto Control, over USB or RS232 serial. It reads,
writes, and **verifies** configuration using the Roboteq ASCII protocol.

It is **config-only** — it never sends a motor command. The values it writes come
from a JSON manifest (`config/hdc2450-analog.json`), so the exact parameters are
data you can review and version, not code.

> Full protocol notes, the library survey this was built from, and the
> ESP32-over-serial design discussion live in [`docs/serial/SERIAL-CONFIG.md`](../../docs/serial/SERIAL-CONFIG.md).

## Why a serial tool if we command over analog?

The **runtime** command path is analog (DAC → op-amp → AnaCmd1) and stays that
way. But the controller still has to be *told* to listen to its analog input and
how to scale it — that's a one-time configuration, normally done in RoboRun+
(Windows). This tool does the same job from the Mac, scriptably and repeatably,
and reads every value back so you catch mistakes on the bench instead of in the
field.

## Install

```bash
pip install pyserial        # only dependency
```

The HDC2450's USB shows up on macOS as `/dev/tty.usbmodem*` with **no driver**
(it's a USB CDC-ACM device). A USB↔RS232 adapter into the DB25 serial pins shows
up as `/dev/tty.usbserial*`. Either works; the tool auto-detects.

## Safety model

| Flag | What it does | Writes? | Persists? |
|------|--------------|:-------:|:---------:|
| `--audit` | Read-only dump of the manifest keys | no | no |
| *(none)* | **Dry-run**: show current → target diff | no | no |
| `--apply` | Write to RAM, then read back & verify each | RAM | no |
| `--apply --save` | As above, then `%EESAV` to flash | RAM | **flash** |

- **Dry-run is the default.** You have to opt in to writing.
- **Every write is verified** by an immediate read-back.
- **Nothing persists** to the controller's flash until you explicitly `--save`,
  so you can write, power-cycle, confirm your fail-safe, and only then commit.
- Manifest items with a `null`/`"TODO"` value are **skipped** — a placeholder can
  never be flashed by accident. (Currently: `AINA`, `ALIM`, `OVL`, `UVL`.)

## Quickstart

```bash
cd tools/roto-setup

# 1. See what's currently on the controller (read-only)
./roto_setup.py --audit

# 2. See what WOULD change (no writes)
./roto_setup.py

# 3. Write to RAM and verify (still not persisted)
./roto_setup.py --apply

# 4. Power-cycle, re-audit, confirm fail-safe. Then commit to flash:
./roto_setup.py --apply --save
```

Pin the port or manifest if needed:

```bash
./roto_setup.py --port /dev/tty.usbmodem1101 --manifest config/hdc2450-analog.json --debug
```

## Before you run it

1. **MOTOR POWER OFF.** This writes config, not motion — but bench-validate with
   the motor stage disconnected, per the project's hardware-first rule.
2. **Fill in the deliberate blanks** in the manifest: `ALIM` (amps limit),
   `OVL`/`UVL` (bus voltage limits), and the `AINA` action bitmask. These have no
   safe defaults, so they're left `null` on purpose.
3. **Treat every mnemonic/value as DRAFT** until you've checked it against the
   HDC2450 config reference (RoboRun+ Configuration tab, or the Advanced Digital
   Motor Controllers user manual). The tool's job is to make a wrong value
   *visible and reversible*, not to guarantee the value is right.

## Exit codes

- `0` — success (audit done / dry-run done / applied & verified / saved)
- `1` — a verify failed, save failed, or a fatal serial/manifest error

## Caveats

- Some config params read back in a normalized form (e.g. you write a percent,
  the controller returns raw counts). A verify "failure" can be legitimate
  scaling — the tool surfaces the mismatch for you to judge rather than hiding it.
- The HDC2450's **USB** is EMI-sensitive under load (motor/relay switching can
  knock it offline). For commissioning that's fine; if you ever want a permanent
  ESP32↔controller serial link, use the **RS232** pins on the DB25 (more robust)
  via a MAX3232 — see the design doc.
