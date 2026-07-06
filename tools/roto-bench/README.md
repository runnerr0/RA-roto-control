# RA Roto — Control Console (`roto-bench`)

A host-side (macOS / Linux) web console that drives the **Roboteq HDC2450, Motor 1**, directly over
USB serial — **no ESP32 required**. It began as a bench bring-up instrument and has grown into a
**viable standalone run-time control path** for a self-contained rotating piece (see
[Running from this console](#running-the-show-from-this-console)).

```
browser (localhost:8791) ──HTTP──► roto_bench.py ──USB serial──► HDC2450 ──► Motor 1
        control + telemetry              (owns the port)         !G / ?… / ^…
```

Two files, stdlib + `pyserial` only:
- **`roto_bench.py`** — serial worker + web server (the engine).
- **`ui.html`** — the operator interface (served at `/`).

---

## Quick start

```bash
pip install pyserial
python3 roto_bench.py            # auto-detects the HDC2450 USB port
# open http://127.0.0.1:8791
```

It starts **DISARMED**. Pick a run mode → **ARM** → drive. Power the motor from a **current-limited
supply** and keep the controller's hardware E-stop reachable.

---

## Run modes

Pick the mode that matches what you're doing; each sets the right safety behavior for you.

| Mode | Behavior | Use for |
|------|----------|---------|
| **JOG** | Hold the slider to run; release = stop. | Setup, positioning, testing. |
| **CRUISE** | Set a speed; it holds. Stall-protected. | Steady running. |
| **DRIFT** | Auto slow sweep around a center point. Stall-protected. | Ambient / atmospheric motion. |
| **HOLD** | Maintain position under load; stall-trip off, temperature/I²t still guard. | Holding against a load. |

### DRIFT patterns
DRIFT generates the command server-side: `command = center + amplitude · wave(t)`.
- **amplitude** — sweep size each side of center.
- **center** — bias point. `0` = balanced fwd/rev; `+300` = mostly-forward slow rotation that breathes.
- **period** — seconds per full cycle.
- **waveform** — `sine` (smooth), `triangle` (linear), `saw` (ramp then snap).

Keep the **speed cap ≥ |center| + amplitude** or the peaks clip.

---

## Safety (layered)

Fastest / most-local first — a fault stops the motor, it doesn't run it:

1. **PSU current limit** — physical, reset-proof. The real ceiling.
2. **HDC2450 `ALIM` foldback** — controller caps motor current (we run 5 A).
3. **`^RWD` watchdog** — the console streams `!G` every ~66 ms; if the process dies, the controller
   self-stops in ~0.5 s.
4. **Stall / overcurrent trip** *(RUN modes)* — amps held near the limit for `trip_ms` → stop + disarm.
5. **Temperature trip** — max controller temp ≥ threshold → stop. Jam/hold agnostic.
6. **I²t overload trip** — leaky current²·time budget → stop. Catches "holding too hard, too long."
7. **Control-drift alarm** — see below.
8. **Operator layer** — arm gate, hold-to-run, browser deadman (JOG), command cap + slew, **E-STOP**.

On any trip: command → 0, motor **disarmed**, latched until the operator clears it. A red banner +
audible alarm + timestamped alert log. The command card also shows **why** output is held at 0
(DISARMED / DEADMAN / TRIPPED / E-STOP), so "armed but not moving" is never a mystery.

> **Jam vs. hold:** open-loop (no encoder) can't tell a jam from a loaded hold by current alone.
> That's why RUN modes stall-trip on current while HOLD relies on temperature + I²t. The real fix is
> an encoder (closed loop) — the HDC2450 has the inputs for it.

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

---

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
- Access is **localhost-only** by design. Driving from a phone means binding to the LAN — a deliberate
  security decision for motor control; do it on a trusted network only.

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
- `roto_bench.py` — engine (worker + HTTP). `--port`, `--cap` flags.
- `ui.html` — operator console (edit freely; it's re-read per request, no restart needed).

Config commissioning (read/write the controller from JSON manifests, config-only) lives in the sibling
[`../roto-setup/`](../roto-setup/).
