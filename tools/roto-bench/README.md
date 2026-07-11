# RA Roto — Control Console (`roto-bench`)

A host-side (macOS / Linux) web console that drives the **Roboteq HDC2450, Motor 1**, directly over
USB serial — **no ESP32 required**. It began as a bench bring-up instrument and has grown into a
**viable standalone run-time control path** for a self-contained rotating piece (see
[Running from this console](#running-the-show-from-this-console)).

```
browser (localhost:8791) ──HTTP──► roto_bench.py ──USB serial──► HDC2450 ──► Motor 1
        control + telemetry              (owns the port)         !G / ?… / ^…
```

stdlib + `pyserial` only, no build step:
- **`roto_bench.py`** — serial worker + web server + optional encoder reader (the engine).
- **`ui.html`** — the operator console (served at `/`).
- **`guide.html` · `graphs.html` · `stats.html` · `remote.html`** — the operator guide (`/guide`),
  pop-out live charts (`/graphs`), big telemetry tiles (`/stats`), and a touch phone view (`/remote`).

---

## Quick start

```bash
./run.sh                         # finds Python 3.6+, installs pyserial if needed, launches
# — or manually —
pip install pyserial
python3 roto_bench.py            # auto-detects the HDC2450 USB port
# open http://127.0.0.1:8791
```

It starts **DISARMED**. Pick a run mode → **ARM** → drive. Power the motor from a **current-limited
supply** and keep the controller's hardware E-stop reachable.

### Flags (all pass through `run.sh` too)

| Flag | Effect |
|------|--------|
| `--port PORT` | Pin the serial port (auto-detected otherwise). |
| `--cap N` | Initial speed cap in raw command units `/1000` (default `150` = 15%). |
| `--sim` | **Preview mode** — run the whole UI on synthetic telemetry, **no hardware**. Validates logic/UI, not real motor physics. |
| `--webport N` | HTTP port (default `8791`). |
| `--host ADDR` / `--lan` | Bind address; `--lan` = `--host 0.0.0.0` to reach the console from a phone/tablet on the LAN. Prints a `/remote` URL. |
| `--encoder PORT` | Enable the optional AS5600 encoder bridge at boot (also toggle it live in the UI). |
| `--gear R` | Gear ratio — encoder-shaft revs per fixture rev (default `1.0`). |

## Compatibility (older Macs)

Designed to run on legacy machines — there's **no build step, no native code, and one pure-Python
dependency**, so CPU architecture and OS age barely matter. `run.sh` handles the fiddly parts.

| Piece | Minimum | Notes |
|-------|---------|-------|
| **Python** | **3.6+** | `ThreadingHTTPServer` has a 3.6 fallback; only `pyserial` is required. |
| **Browser** | **Safari 10+** (2016) / any modern Chrome or Firefox | UI avoids ES2020 syntax (no `?.`/`??`) and uses `XMLHttpRequest`, so old Safari doesn't choke. |
| **Serial** | USB CDC (`/dev/cu.usbmodem*`) | Auto-detected; pass `--port` to pin it. |

Kept legacy-safe deliberately: no transpiler, no framework, `ui.html` is served as-is and re-read per
request. If you touch the UI, stick to ES6 (arrow functions/template literals are fine) and avoid
`?.`, `??`, and other ES2020+ features so it keeps running on old Safari.

---

## Run modes

Pick the mode that matches what you're doing; each sets the right safety behavior for you.

| Mode | Behavior | Use for |
|------|----------|---------|
| **JOG** | Hold the slider to run; release = stop. | Setup, positioning, testing. |
| **CRUISE** | Set a speed; it holds. Stall-protected. | Steady running. |
| **DRIFT** | Two-phase self-running sweep (**Run/Stop** — see below). Stall-protected. | Ambient / atmospheric motion. |
| **HOLD** | Maintain position under load; stall-trip off, temperature/I²t still guard. | Holding against a load. |
| **CREEP** | Very slow under load; stall-trip off, anti-stiction kick on start. | Slow loaded creep. |

### DRIFT (two-phase, Run/Stop)
Entering DRIFT arrives **halted** — it does *not* auto-run. Set the pattern, then press **▶ Run drift**;
the global **Stop** halts it. The command is generated server-side (`/api/drift`), cycling:
hold **Side A** (`ta` s) → ramp to **Side B** (`ramp` s) → hold **Side B** (`tb` s) → ramp back → repeat.
- **Side A / Side B speed** — the two target speeds (%, center-zero: right = fwd, left = rev).
- **hold A / hold B** — seconds to dwell at each side.
- **ramp** — seconds to ease between the two sides (`0` = snap).

Every side is clamped to the **speed cap** — set the cap ≥ the larger side or the peaks clip.

---

## Safety (layered)

Fastest / most-local first — a fault stops the motor, it doesn't run it:

1. **PSU current limit** — physical, reset-proof. The real ceiling.
2. **HDC2450 `ALIM` foldback** — controller caps motor current (we run 5 A).
3. **`^RWD` watchdog** — the console streams `!G` every ~66 ms; if the process dies, the controller
   self-stops in ~0.5 s.
4. **Current governor** *(RUN modes, **default ON**)** — closed loop on motor current: feathers the
   command to hold amps just under ~0.85×`ALIM`, so the motor **rides** the ceiling instead of slamming
   it and breaking free. **While the governor is on, the stall/overcurrent trip is suppressed** — the
   governor owns current limiting; I²t + temp + `ALIM` foldback are the backstops. Toggle + "% of limit"
   in **⚙ Settings** (`/api/governor`).
5. **Stall / overcurrent trip** *(RUN modes, **only when the governor is OFF**)* — amps held near the
   limit for `trip_ms` → stop + disarm.
6. **Temperature trip** — max controller temp ≥ threshold → stop. Jam/hold agnostic.
7. **I²t overload trip** — leaky current²·time budget → stop. Catches "holding too hard, too long."
   On by default; the **I²t checkbox** in Settings → Protect disables it (the budget value is kept, the
   accumulator clears) when the proxy fights a legitimately heavy load — temperature stays the real guard.
8. **TRUE STALL trip** *(optional encoder)* — commanded ≥ 10% but the shaft reads ~0 RPM → stop.
   Suppressed in HOLD/CREEP (which legitimately sit near 0 RPM). See the encoder section.
9. **Control-drift alarm** — see below.
10. **Operator layer** — arm toggle, hold-to-run (JOG), browser deadman (JOG), speed cap + slew,
    **soft-stop latch**, **E-STOP** (button or **spacebar**).

On any trip: command → 0, motor **disarmed**, latched until the operator clears it. A red banner +
audible alarm + timestamped alert log. The command card also shows **why** output is held at 0
(DISARMED / DEADMAN / STOPPED / TRIPPED / E-STOP), so "armed but not moving" is never a mystery.

> **Soft-stop latch.** The **Stop** button (`/api/stop`) forces output to 0 in **every** mode — including
> a running DRIFT — while staying **armed**; status shows **STOPPED**. Any fresh command (slider, Go,
> Run drift) releases it. Distinct from E-STOP, which also disarms and latches.

> **Jam vs. hold:** open-loop (no encoder) can't tell a jam from a loaded hold by current alone.
> That's why RUN modes stall-trip on current while HOLD relies on temperature + I²t. The real fix is
> an encoder (closed loop) — the HDC2450 has the inputs for it.

---

## Operating the console (UI)

- **Everything command-related is in percent (0–100%)**, not raw −1000…1000.
- **Center-zero sliders** (jog + drift Side A/B) fill outward from center — green forward, amber reverse.
- **Speed cap enforced in every mode** *and* surfaced: the slider range and the exact-speed box are
  limited to the cap, and a **⚠ at speed cap** note shows when pinned. The engine also clamps to ±cap.
- **HOLD / CREEP effort control** replaces the coarse slider with a Fwd/Rev toggle + a dial scoped
  `0..cap` + fine `−5/−1/+1/+5` nudges and a large "N% fwd/rev" readout — for fine effort in the low band.
- **Arm is a toggle switch** (slides on/off), not a state-labeled button.
- **? Help** toggle in the top bar: point at any control for an inline explanation. Full operator guide
  at **`/guide`**.
- **Top bar**: status · live amps/cmd · ARM · Help · Guide · **E-STOP** (isolated far-right). Clear E-Stop
  / Reset Trip appear only when relevant. **Spacebar = E-STOP** (unless a field is focused).

## Second screen & remote access

- **⧉ Pop out** opens **`/graphs`** (live motion / current / all-telemetry charts) and **`/stats`**
  (big color-coded telemetry tiles) in their own windows — drag either to a second monitor.
- **`--lan`** (or `--host 0.0.0.0`) exposes the console on the network; **`/remote`** is a
  touch-optimized phone view (monitor + E-STOP / Arm / Stop). `--webport N` changes the port. LAN motor
  control is a deliberate security tradeoff — trusted network only.
- **`--sim`** runs the entire UI on synthetic telemetry with **no hardware** — validates logic and the
  UI, not real motor physics.

## Optional: AS5600 encoder (real motion feedback)

An **AS5600 magnetic encoder** on a small Arduino/ESP32 I²C→USB bridge adds real shaft sensing. Enable it
in **⚙ Settings → Encoder** (port + gear ratio + a live debug readout), or at boot with
`--encoder PORT --gear R`. It's a pure sensor — it never commands the motor — and it adds:

- **Fixture RPM** — shaft RPM ÷ gear ratio (the big-wheel speed).
- **TRUE STALL trip** — commanded ≥ 10% but the shaft reads ~0 RPM → stop. The motion check open-loop
  current can't make. Suppressed in HOLD/CREEP.

Endpoints `/api/encoder`, `/api/serial_ports`. Hardware, firmware, and 3D-printed mount:
[`../as5600-reader/`](../as5600-reader/) (`as5600_reader.ino`, `as5600_mount.scad`). This is the interim
toward full controller-side closed loop (encoder on the HDC2450 ENC inputs + `MMOD`).

---

## Advanced — controller profile & control drift

The **Advanced** section (collapsed by default) live-edits the HDC2450's **own** configuration —
`ALIM`, `MXPF/MXPR`, `RWD`, `ATRIG/ATGA/ATGD` — written to controller **RAM** and read back to verify.
Each parameter is described inline. `Save to flash` persists RAM → EEPROM.

**Control-drift detection.** The console continuously compares the controller's live `ALIM`, `RWD`,
`AINA 3`, `AINA 4` against an expected safe baseline. If they diverge — most commonly because a
**controller reset reverted the RAM config** back to factory (100 A limit, analog command re-enabled) —
it raises a **CONTROL DRIFT** critical alarm. **Re-apply safe profile** restores the baseline in one
click. Deliberate edits you make become the new baseline, so it only alarms on drift you didn't intend.

> RAM config is lost on any controller reset. For a run, `Save to flash` so it survives a power cycle.

**Config backup / restore.** *Config snapshot* captures the controller's **current** config as a restore
point and writes it back with one tap — instant recovery if the config drifts or a power cycle reverts it.
**Backup** also downloads a `.json`; **Load file** restores from a previously saved one. Complements
*Re-apply safe profile* (which restores the fixed safe baseline).

---

## Slow-loaded operation (CREEP + characterization)

Very slow motion under load is the hardest regime: open-loop command ≈ voltage only tracks speed at
light load, and slow + loaded draws **high current at near-zero motion** — which electrically looks like
a stall and would false-trip the current-stall protection. Two tools address this today:

- **CREEP mode** — a latched slow mode that **suppresses the current-stall trip** (temperature + I²t
  still protect), plus an **anti-stiction kick**: a brief breakaway boost (`kick` level for `ms`) on
  start-from-stop to overcome static friction, then it settles to your set speed.
- **Characterization log** — records command · amps · volts · temp to CSV (`logs/`, ~5 Hz). Use it to
  find the **breakaway command**, the current at slow-loaded, and whether it creeps smoothly. Measure
  before tuning.
- **Characterization sweep** — an operator-triggered routine (ARM required; aborts instantly on any
  trip / disarm / E-STOP; clamped to the speed cap) that steps the command through a range, records the
  settled amps per step, and computes the **breakaway command** + a **suggested CREEP kick**. Save
  results as named **presets** (`presets/`); the most recent loads on startup as a baseline for
  comparison (display only — it never moves the motor).

These make open-loop slow-loaded *usable*. The **proper** fix is closed loop: add an **encoder** to the
HDC2450's ENC inputs, set `MMOD` = closed-loop speed, and `!G` then commands a target RPM the controller
holds under varying load — which also makes stall detection unambiguous. Encoder + **gearing** (the
highest-leverage mechanical move) are hardware follow-ups (pending parts); CREEP + logging cover the
interim. See the slow-speed plan in the project docs.

## Tuning for a loaded roto

A large, slow, **unbalanced** roto (one that lifts a mass up one side) is the hard case: it draws
**current that varies with angle** — highest while lifting, low or regenerative on the way down. The
number that matters is the **peak-lift current**, and current *is* torque, so if the current limit is
below what the peak needs, it stalls at the hardest angle ("won't lift").

### The workflow

1. **Be on the real supply**, not a current-limited bench PSU — and **fuse & wire** for the current
   you'll run. With a big supply the controller `ALIM` + the trips are now your safety, not the PSU.
   Keep the hardware E-STOP reachable.
2. **Run the guided lift test** (its own card). It holds a slow command and steps `ALIM` up rung by
   rung until measured amps fall *below* the limit — the moment the motor breaks free — and reports
   the **load current**. It requires ARM, aborts on any trip/disarm/E-STOP, auto-stops on over-temp,
   never exceeds your ceiling, and **restores the safe limit** on any non-success stop.
3. **Set `ALIM ≈ peak-lift × 1.3`** in the Advanced profile editor (the test prints the suggestion).
   That gives torque headroom at the worst angle without running wide open.
4. **Verify under load**: run it loaded at your target speed for a few minutes with **CREEP** (stall
   trip suppressed; temp + I²t still guard) and watch the **Max temp** stat. Temp **stabilising** =
   good. Temp **climbing** = you're over the motor's continuous rating at this duty.
5. **Set the guards** with the loaded numbers: stall trip *above* peak-lift, a temperature trip below
   the motor's limit, an I²t budget that tolerates normal lifting but catches a jam. Tune the **CREEP
   kick** to just above the breakaway (from the characterization sweep) so it starts cleanly.
6. **Save to flash** once dialled, so a controller reset can't revert it (and the control-drift alarm
   will catch it if it does).

### When more current isn't the answer

If the lift test hits the ceiling without lifting, or step 4 shows temperature that keeps climbing,
the motor is telling you it's past its **continuous** rating at that duty (slow = no cooling airflow,
near-locked-rotor heat). The real fixes are **more gear reduction** (the highest-leverage move — less
motor current for the same load) or a **run/rest duty cycle** — not just raising `ALIM`. And once an
**encoder** is fitted, closed-loop speed control does this angle-by-angle automatically: it pours in
current at the hard lifting angle and backs off on the descent.

## Running the show from this console

This console is a genuine control path, not only a bench tool — for a **self-contained rotating piece
that doesn't need lighting-console (DMX) integration**, you can run the whole show from it: set a
**DRIFT** pattern (or a CRUISE speed), ARM, and let it run.

To do that reliably:
- **Run on an always-on host** — a mini PC / Raspberry Pi / NUC, **not a laptop that sleeps**. Sleep
  suspends the process → the `^RWD` watchdog stops the motor (safe, but it stops).
- **`Save to flash`** the safe profile so a controller glitch can't revert to 100 A / analog.
- **Current-limited supply + hardware E-stop** wired, always.
- **Good USB cable**; the worker auto-reconnects if the link drops (and the watchdog covers the gap).
- Access is **localhost-only** by default. `--lan` exposes it for phone/tablet control (`/remote`) — a
  deliberate security decision for motor control; do it on a trusted network only.

### vs. the ESP32-POE-ISO firmware (the product)
| | This console | ESP32 firmware |
|---|---|---|
| Host needed | yes (USB-tethered computer) | no (standalone) |
| Show-control input | none (manual / DRIFT) | DMX512 / Art-Net / sACN |
| Network | localhost / LAN | wired Ethernet + PoE + isolation |
| Best for | self-contained piece, bring-up, diagnostics | DMX-integrated installs, rugged deploy |

Both share the same command/telemetry/safety logic — this console proved it on hardware first.

---

## What we've figured out (hardware findings)

- **Serial control works end to end.** Motor 1 runs from `!G 1 <-1000..1000>` over USB; telemetry
  (`?A ?V ?T ?FF ?AI ?PI ?AIC`) reads back. Baud 115200 8N1 confirmed.
- **The legacy rig was DMX → Northlight "Decode8" → 0–5 V analog → HDC2450.** Fully reverse-engineered
  in [`docs/LEGACY-WIRING.md`](../../docs/LEGACY-WIRING.md); the missing analog ground (Decode8 `G` →
  DB25 pin 5) was the dead-rig cause.
- **As-found controller config** cataloged in [`../roto-setup/captures/`](../roto-setup/captures/):
  factory command priority (Serial > RC > Analog), both `AnaCmd` inputs (pins 4 & 17 = ANA3/ANA4)
  targeting Motor 1, real protection (100 A limit, 45 V OV, 5 V UV).
- **`ALIM` accepts a true 5 A limit** (the datasheet's 10 A floor didn't bite).
- **`ATGA` decoded** (`^ATGA cc (aa + mm)`, `mm = mot1·16`): `17` = safety-stop on Motor 1. `ATRIG`
  must be set **below** `ALIM`, which is what makes controller-side stall detection work with foldback.
- **RAM config reverts on controller reset** → the control-drift alarm exists to catch it.

---

## Files
- `roto_bench.py` — engine (worker + HTTP + encoder reader). Flags: `--port`, `--cap`, `--sim`,
  `--webport`, `--host`, `--lan`, `--encoder`, `--gear`.
- `ui.html` — operator console (`/`). Re-read per request — edit freely, no restart needed.
- `guide.html` · `graphs.html` · `stats.html` · `remote.html` — operator guide (`/guide`), pop-out
  charts (`/graphs`), telemetry tiles (`/stats`), phone view (`/remote`).
- `run.sh` — portable launcher (finds Python 3.6+, installs pyserial); passes all flags through.
- `presets/` · `logs/` — saved characterization presets and CSV run logs.

Optional encoder hardware/firmware/mount: [`../as5600-reader/`](../as5600-reader/).
Config commissioning (read/write the controller from JSON manifests, config-only) lives in the sibling
[`../roto-setup/`](../roto-setup/).
