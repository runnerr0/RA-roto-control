---
name: roto
description: Use when working on the RA Roto Control project (host-side control console for the Roboteq HDC2450 motor controller) — building/debugging roto_bench.py or ui.html, running the sim, validating changes, or referencing the HDC2450 serial protocol and safety invariants.
---

# RA Roto Control

## What this project is

A networked motor-speed controller for **Radiant Atmospheres**. It bridges
show-control protocols (DMX512, Art-Net, sACN) → an **ESP32-POE-ISO** (future
firmware) → **RS232 serial** → a **Roboteq HDC2450** brushed-DC motor controller
driving a slow rotating art fixture.

**TODAY** it is driven by a host-side web console:
`tools/roto-bench/roto_bench.py` (Python engine) + `tools/roto-bench/ui.html`
(web UI), talking to the controller over USB serial. Serial is the chosen
control path.

## Key files

- `tools/roto-bench/roto_bench.py` — the engine (`State` class, `Worker` thread
  that owns the serial port, HTTP `Handler`). Keep files under 500 lines where
  practical.
- `tools/roto-bench/ui.html` — the operator console (vanilla JS, polls
  `/api/state` every 150 ms).
- `tools/roto-bench/graphs.html`, `stats.html`, `guide.html` — pop-out pages
  served at `/graphs`, `/stats`, `/guide`.
- `docs/` — `HARDWARE.md`, `ARCHITECTURE.md`, `PERSONAS.md`, `LEGACY-WIRING.md`.

## Dev loop (no hardware needed)

- Run the sim: `python3 tools/roto-bench/roto_bench.py --sim` (add `--webport N`
  to change port; serves at http://127.0.0.1:8791). The sim feeds synthetic
  telemetry so the whole UI runs without a controller.
- **NOTE:** the sim's amps model is a **fake linear function of the command** —
  it validates LOGIC and UI, not real motor physics.
- Always verify UI changes by rendering in a **real browser** (screenshots), not
  just reading code.

## Validation gauntlet (run before claiming anything works)

```
python3 -m py_compile tools/roto-bench/roto_bench.py            # engine compiles
python3 -c "import pathlib;h=pathlib.Path('tools/roto-bench/ui.html').read_text();open('/tmp/ui.js','w').write(h.split('<script>')[1].split('</script>')[0])" && node --check /tmp/ui.js   # JS syntax
grep -nE '\?\?|\?\.' tools/roto-bench/ui.html                   # MUST be empty — legacy-safe JS only (no ES2020 ?? or ?.)
```

Plus an **id/endpoint cross-check**: every `$('id')` referenced must exist as an
`id=` in the HTML; every `/api/<name>` the UI calls must be handled in
`roto_bench.py`.

## HDC2450 serial protocol

115200 8N1, true RS232 via MAX3232, DB25 pins **2 = Tx / 3 = Rx / 5 = GND**.

- `!G 1 <-1000..+1000>` — motor 1 command (signed = speed AND direction,
  0 = stop). Sent **continuously** to feed the watchdog.
- **Runtime queries:** `?A` amps (×10), `?V` volts, `?T` temp, `?FF` fault
  flags, `?BA` supply amps (×10, signed = regen), `?P` applied power, `?M` motor
  command, `?S` encoder speed, `?FS` status flags, `?AI` analog inputs.
- **Config:** `^KEY [idx] value` SetConfig (RAM), `~KEY [idx]` GetConfig,
  `%EESAV` save to flash. Whitelisted keys: ALIM, MXPF, MXPR, RWD, ATRIG, ATGA,
  ATGD, MAC, MDEC, OVL, UVL, AINA.

## Locked safety invariants (do not break)

- **Current governor is DEFAULT ON** — feathers the command to hold amps under
  ~0.85×ALIM; the stall (overcurrent) trip is **SUPPRESSED** while the governor
  is on (the governor owns current limiting); I²t + temperature + ALIM foldback
  are the backstops.
- **`^RWD` command-loss watchdog is the PRIMARY hardware fail-safe:** the console
  streams `!G` continuously; if it goes silent the controller self-stops.
- **Speed cap is enforced in EVERY mode** (engine clamps to ±cap) and the UI
  slider/inputs respect it.
- **Soft-stop latch (`/api/stop`)** forces output to 0 in every mode including
  DRIFT; DRIFT requires an explicit Run (does not auto-run).
- Motor drives to 0 on boot/disarm/e-stop/trip. Never enable the power stage
  before the firmware is commanding STOP.
- **UI JavaScript must be legacy-safe** (old Safari): NO `??` or `?.`; use the
  `D(x,f)` helper and the XHR `api()` (no `fetch`).

## Modes

- **JOG** — hold-to-run.
- **CRUISE** — set speed, holds.
- **DRIFT** — two-phase: hold Side A, ramp to Side B, hold, ramp back (explicit
  Run/Stop).
- **HOLD** — position under load, effort panel.
- **CREEP** — very slow under load, effort panel + anti-stiction kick.
