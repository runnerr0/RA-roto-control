#!/usr/bin/env python3
"""
roto_bench.py — bench/run control console for the Roboteq HDC2450.

Drives Motor 1 over USB serial (`!G`) from a localhost web UI (ui.html) with
production-minded safety and live, RAM-only profile editing.

Safety model (layered):
  * One worker thread owns the serial port. Each ~66 ms tick it sends `!G 1 <cmd>`
    (feeds the controller ^RWD watchdog), samples `?A` amps EVERY tick, evaluates
    trips, then does ONE auxiliary op (telemetry read, profile read, or a queued
    config write). The `!G` stream is never starved.
  * TRIPS (any -> command 0, motor DISARMED, latched until operator reset):
      - Overcurrent / STALL: amps held >= trip_amps for trip_ms. RUN intent only
        (in HOLD, holding current is expected -> stall trip suppressed).
      - TEMPERATURE: max controller temp >= temp_trip. Always on. Jam/hold agnostic.
      - I2t OVERLOAD: leaky current^2 * time accumulator >= heat_budget. Always on.
        Catches "holding too hard too long" AND jams without needing to know which.
  * Command forced 0 unless armed & !estop & !tripped & (momentary: browser fresh).
  * PROFILE EDIT: the UI can write controller config (^KEY) live, RAM-only, verified
    by read-back. %EESAV (flash) only via an explicit separate action.

Disambiguation note: open-loop (no encoder) cannot tell a jam from a loaded hold by
current alone. RUN/HOLD intent + temperature + I2t is the pragmatic answer; an encoder
(closed loop) is the real fix. See docs.

localhost only.  Run:  ./roto_bench.py   then open http://127.0.0.1:8791
"""
import argparse
import glob
import json
import math
import sys
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

try:
    from http.server import ThreadingHTTPServer            # Python 3.7+
except ImportError:                                        # Python 3.6 fallback
    from http.server import HTTPServer
    from socketserver import ThreadingMixIn

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

try:
    import serial
except ImportError:
    serial = None

BAUD = 115200
CMD_PERIOD = 1 / 15
DEADMAN_S = 0.6
DEFAULT_CAP = 150
MAX_CAP = 1000
SLEW_PER_TICK = 30
AMP_LIMIT = 5.0
TRIP_AMPS_DEFAULT = 4.5
TRIP_MS_DEFAULT = 800
TEMP_TRIP_DEFAULT = 70.0     # degC; 0 disables
HEAT_BASELINE = 2.0          # amps below which the I2t bucket leaks
HEAT_BUDGET_DEFAULT = 600.0  # A^2*s; ~28 s at 5 A; 0 disables
BACKOFF_DOWN = 0.03          # command-scale decrease per tick while over-torque
BACKOFF_UP = 0.006           # slow recovery per tick once relieved (no oscillation)
HOST, PORT = "127.0.0.1", 8791
UI_FILE = Path(__file__).parent / "ui.html"
PRESET_DIR = Path(__file__).parent / "presets"
PORT_GLOBS = ["/dev/cu.usbmodemRTQ*", "/dev/cu.usbmodem*", "/dev/cu.usbserial*",
              "/dev/ttyACM*", "/dev/ttyUSB*"]
# aux ops round-robined one-per-tick: telemetry (?) + profile reads (~)
AUX = ["?V", "?T", "?FF", "?BA", "?P", "?M", "?S", "?FS", "?AI", "?PI", "?AIC",
       "~ALIM 1", "~MXPF 1", "~MXPR 1", "~RWD", "~ATRIG 1", "~ATGA 1", "~ATGD 1",
       "~AINA 3", "~AINA 4", "~MAC 1", "~MDEC 1", "~OVL", "~UVL"]
CONFIG_WHITELIST = {"ALIM", "MXPF", "MXPR", "RWD", "ATRIG", "ATGA", "ATGD",
                    "MAC", "MDEC", "OVL", "UVL", "AINA"}
FAULT_BITS = [(0x01, "OVERHEAT"), (0x02, "OVERVOLT"), (0x04, "UNDERVOLT"),
              (0x08, "SHORT"), (0x10, "ESTOP"), (0x20, "SEPEX-FAULT"),
              (0x40, "MOSFET-FAIL"), (0x80, "STARTUP-CFG")]
FS_BITS = [(0x01, "serial"), (0x02, "pulse"), (0x04, "analog"), (0x08, "pwr-off"),
           (0x10, "STALL"), (0x20, "AT-LIMIT"), (0x80, "script")]


class State:
    def __init__(self, cap):
        self.lock = threading.Lock()
        self.target = 0.0
        self.applied = 0.0
        self.cap = cap
        self.armed = False
        self.estop = False
        self.mode = "momentary"          # derived report: momentary | latched
        self.intent = "run"              # derived report: run | hold
        self.run_mode = "jog"            # jog | cruise | drift | hold
        self.osc_amp = 150.0             # DRIFT amplitude (command units)
        self.osc_period = 20.0           # DRIFT period (seconds)
        self.osc_center = 0.0            # DRIFT center/bias (command units)
        self.osc_wave = "sine"           # sine | triangle | saw
        self.expected = {"ALIM 1": "50", "RWD": "500", "AINA 3": "0", "AINA 4": "0"}
        self.mon = {}                    # live values of the drift-watched params
        # --- overtorque backoff: relieve command when pinned at the current limit --- #
        self.backoff_on = True
        self.backoff_amps = 4.0          # engage when motor amps >= this (A)
        self.backoff_ms = 400            # sustained this long before backing off
        self.backoff_scale = 1.0         # live command multiplier (1=full, 0=fully relieved)
        self.backoff_active = False
        self.creep_kick = 150.0          # CREEP anti-stiction breakaway level (command units)
        self.creep_kick_ms = 400         # CREEP kick duration (ms)
        self.logging = False             # characterization CSV logging on/off
        self.log_name = ""
        self.log_rows = 0
        self.events = []                 # event lines to drop into the log (tests, config changes)
        self.tripped = False
        self.trip_reason = ""
        self.trip_amps = TRIP_AMPS_DEFAULT
        self.trip_ms = TRIP_MS_DEFAULT
        self.temp_trip = TEMP_TRIP_DEFAULT
        self.heat_budget = HEAT_BUDGET_DEFAULT
        self.heat_now = 0.0
        self.last_contact = 0.0
        self.connected = False
        self.deadman = True
        self.tele = {}
        self.raw = {}
        self.profile = {}                # last-read controller config values
        self.config_queue = []           # pending {key,idx,val} or {flash:True}
        self.config_log = []             # recent write results
        # --- characterization sweep (server-side, runs inside Worker) --- #
        self.sweep_active = False        # operator-triggered sweep running
        self.sweep_status = "idle"       # idle | starting | running... | done | aborted
        self.sweep_step = 25             # command increment per step
        self.sweep_dwell = 1.5           # seconds per step (settle + average)
        self.sweep_max = 300             # top command level (clamped to cap)
        self.sweep_dir = "fwd"           # fwd | rev | both
        self.sweep_progress = 0.0        # 0..1 fraction of levels completed
        self.sweep_level = 0             # command level currently under test
        self.sweep_results = []          # [{cmd, amps}] from the last sweep
        self.sweep_breakaway = None      # est. breakaway command
        self.sweep_kick = None           # suggested CREEP kick (magnitude)
        self.baseline = None             # most-recent/loaded preset (display only)
        # --- guided LIFT TEST (steps ALIM up under a held command) ------- #
        self.lift_active = False
        self.lift_status = "idle"
        self.lift_alim_start = 50        # 5.0 A (0.1A units)
        self.lift_alim_step = 25         # +2.5 A per rung
        self.lift_alim_max = 250         # 25.0 A safety ceiling
        self.lift_dwell = 3.0            # seconds per rung
        self.lift_cmd = 200              # slow command held during the test
        self.lift_temp_limit = 65.0      # auto-stop temperature (degC)
        self.lift_results = []           # [{alim, amps, temp, lifted}]
        self.lift_alim_cur = 0           # ALIM (A) currently under test
        self.lift_peak_amps = None       # detected load current once it lifts
        self.lift_lifted = False         # did it break free within the ceiling

    def snapshot(self):
        with self.lock:
            try:                                 # report the ACTUAL controller ALIM as the limit
                live_lim = float(self.mon.get("ALIM 1") or self.profile.get("ALIM") or 0) / 10.0
            except (TypeError, ValueError):
                live_lim = 0.0
            if live_lim <= 0:
                live_lim = AMP_LIMIT
            return {
                "target": self.target, "applied": round(self.applied), "cap": self.cap,
                "armed": self.armed, "estop": self.estop, "mode": self.mode, "intent": self.intent,
                "run_mode": self.run_mode, "osc_amp": self.osc_amp, "osc_period": self.osc_period,
                "osc_center": self.osc_center, "osc_wave": self.osc_wave,
                "expected": dict(self.expected), "mon": dict(self.mon),
                "creep_kick": self.creep_kick, "creep_kick_ms": self.creep_kick_ms,
                "backoff_on": self.backoff_on, "backoff_amps": self.backoff_amps,
                "backoff_ms": self.backoff_ms, "backoff_scale": round(self.backoff_scale, 3),
                "backoff_active": self.backoff_active,
                "logging": self.logging, "log_name": self.log_name, "log_rows": self.log_rows,
                "tripped": self.tripped, "trip_reason": self.trip_reason,
                "trip_amps": self.trip_amps, "trip_ms": self.trip_ms,
                "temp_trip": self.temp_trip, "heat_budget": self.heat_budget,
                "heat_now": round(self.heat_now, 1), "amp_limit": round(live_lim, 1),
                "connected": self.connected, "deadman": self.deadman,
                "tele": dict(self.tele), "profile": dict(self.profile),
                "config_log": list(self.config_log[:8]),
                "sweep_active": self.sweep_active, "sweep_status": self.sweep_status,
                "sweep_step": self.sweep_step, "sweep_dwell": self.sweep_dwell,
                "sweep_max": self.sweep_max, "sweep_dir": self.sweep_dir,
                "sweep_progress": round(self.sweep_progress, 3), "sweep_level": self.sweep_level,
                "sweep_results": list(self.sweep_results),
                "sweep_breakaway": self.sweep_breakaway, "sweep_kick": self.sweep_kick,
                "baseline": dict(self.baseline) if self.baseline else None,
                "lift_active": self.lift_active, "lift_status": self.lift_status,
                "lift_alim_start": self.lift_alim_start, "lift_alim_step": self.lift_alim_step,
                "lift_alim_max": self.lift_alim_max, "lift_dwell": self.lift_dwell,
                "lift_cmd": self.lift_cmd, "lift_temp_limit": self.lift_temp_limit,
                "lift_results": list(self.lift_results), "lift_alim_cur": self.lift_alim_cur,
                "lift_peak_amps": self.lift_peak_amps, "lift_lifted": self.lift_lifted,
            }

    def push_event(self, text):          # queue an event line for the CSV log (append is atomic)
        self.events.append(text)
        if len(self.events) > 400:
            del self.events[:200]


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def build_levels(step, mx, direction, cap):
    """Signed command levels for a characterization sweep, clamped to cap.
    step, 2*step, ... up to min(mx, cap); negated for rev; fwd+rev for both."""
    step = max(1, int(step))
    mx = int(min(mx, cap))
    fwd = list(range(step, mx + 1, step))
    if not fwd and mx > 0:
        fwd = [mx]
    rev = [-x for x in fwd]
    if direction == "rev":
        return rev
    if direction == "both":
        return fwd + rev
    return fwd


def compute_breakaway(results, step):
    """Breakaway heuristic: the first level whose averaged amps exceeds 1.3x the
    amps at the lowest non-zero step (first clear sign of real load/motion).
    Suggested CREEP kick = |breakaway| + one step of margin. Returns (cmd, kick)."""
    pts = [r for r in results if r["cmd"] > 0] or [r for r in results if r["cmd"] < 0]
    pts = sorted(pts, key=lambda r: abs(r["cmd"]))
    if len(pts) < 2:
        return None, None
    base = abs(pts[0]["amps"])
    breakaway = None
    for r in pts[1:]:
        if base > 0 and abs(r["amps"]) > 1.3 * base:
            breakaway = r["cmd"]
            break
    if breakaway is None:                       # never crossed -> use the top level
        breakaway = pts[-1]["cmd"]
    kick = int(round(abs(breakaway) + max(1, int(step))))
    return breakaway, kick


def preset_names():
    if not PRESET_DIR.exists():
        return []
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def most_recent_preset():
    if not PRESET_DIR.exists():
        return None
    files = sorted(PRESET_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def safe_preset_name(name):
    return "".join(c for c in name if c.isalnum() or c in "-_")[:40]


def wave(name, phase):
    """Unit waveform in [-1, 1] for the DRIFT oscillator."""
    if name == "triangle":
        return (2 / math.pi) * math.asin(math.sin(phase))
    if name == "saw":
        return 2 * ((phase / (2 * math.pi)) % 1.0) - 1
    return math.sin(phase)


def decode(query, value, tele):
    parts = value.split(":")

    def ints():
        out = []
        for p in parts:
            try:
                out.append(int(p))
            except ValueError:
                out.append(None)
        return out

    if query == "?A":
        a = ints()
        if a and a[0] is not None:
            tele["amps_m1"] = a[0] / 10.0
    elif query == "?V":
        v = ints()
        if len(v) >= 2 and v[1] is not None:
            tele["volts_batt"] = v[1] / 10.0
        if len(v) >= 3 and v[2] is not None:
            tele["volts_5v"] = v[2] / 1000.0
    elif query == "?T":
        tele["temp"] = [x for x in ints() if x is not None]
    elif query == "?FF":
        f = ints()
        if f and f[0] is not None:
            tele["faults"] = [n for bit, n in FAULT_BITS if f[0] & bit]
    elif query == "?AI":
        tele["ain"] = ints()
    elif query == "?PI":
        tele["pin"] = ints()
    elif query == "?AIC":
        tele["aic"] = ints()
    elif query == "?BA":                 # supply/battery amps, x10, signed (regen = negative)
        a = ints()
        if a and a[0] is not None:
            tele["batt_amps"] = a[0] / 10.0
    elif query == "?P":                  # applied motor power/PWM, -1000..1000
        p = ints()
        if p and p[0] is not None:
            tele["power"] = p[0]
    elif query == "?M":                  # motor command the controller is acting on, -1000..1000
        m = ints()
        if m and m[0] is not None:
            tele["mcmd"] = m[0]
    elif query == "?S":                  # encoder speed RPM (real once an encoder is fitted)
        s = ints()
        if s and s[0] is not None:
            tele["speed"] = s[0]
    elif query == "?FS":                 # status flags (serial/analog mode, stall, AT-LIMIT...)
        f = ints()
        if f and f[0] is not None:
            tele["status"] = [n for bit, n in FS_BITS if f[0] & bit]
            tele["at_limit"] = bool(f[0] & 0x20)


class Worker(threading.Thread):
    def __init__(self, state, port):
        super().__init__(daemon=True)
        self.state = state
        self.port = port
        self._ser = None
        self._qi = 0
        self._halt = threading.Event()

    def stop(self):
        self._halt.set()

    def _open(self):
        self._ser = serial.Serial(self.port, BAUD, timeout=0.05, bytesize=8,
                                  parity="N", stopbits=1, xonxoff=False, rtscts=False)
        time.sleep(0.2)
        self._ser.reset_input_buffer()

    def _txrx(self, line, want_prefix):
        self._ser.write((line + "\r").encode("ascii"))
        self._ser.flush()
        deadline = time.time() + 0.05
        buf = b""
        while time.time() < deadline:
            chunk = self._ser.read(128)
            if chunk:
                buf += chunk
                deadline = time.time() + 0.02
            elif buf:
                break
        if not want_prefix:
            return None
        for raw in buf.replace(b"\r", b"\n").split(b"\n"):
            s = raw.decode("ascii", "replace").strip()
            if s.startswith(want_prefix):
                return s
        return None

    def _sample_amps(self):
        reply = self._txrx("?A", "A=")
        if reply and "=" in reply:
            val = reply.split("=", 1)[1]
            try:
                return int(val.split(":")[0]) / 10.0, val
            except ValueError:
                return None, val
        return None, None

    def _open_log(self):
        d = Path(__file__).parent / "logs"
        d.mkdir(exist_ok=True)
        name = "roto-" + time.strftime("%Y%m%d-%H%M%S") + ".csv"
        f = open(d / name, "w")
        f.write("time,elapsed_s,mode,target,applied,amps,volts,temp,heat,tripped,trip_reason,event\n")
        with self.state.lock:
            self.state.log_name = name
            self.state.log_rows = 0
        return f

    def _write_config(self, key, idx, val):
        cmd = f"^{key}" + (f" {idx}" if idx else "") + f" {val}"
        self._txrx(cmd, None)
        rb = self._txrx(f"~{key}" + (f" {idx}" if idx else ""), key + "=")
        readback = rb.split("=", 1)[1] if rb and "=" in rb else None
        ok = readback is not None and (readback.strip() == str(val).strip()
                                       or self._num_eq(readback, val))
        return readback, ok

    @staticmethod
    def _num_eq(a, b):
        try:
            return int(a) == int(float(b))
        except (ValueError, TypeError):
            return False

    def run(self):
        applied = 0.0
        osc_phase = 0.0
        over_since = None
        kick_start = None
        logf = None
        log_tick = 0
        log_t0 = 0.0
        # characterization sweep locals (persist across ticks)
        sweep_running = False
        sweep_levels = []
        sweep_idx = 0
        sweep_phase = "ramp"
        sweep_sum = 0.0
        sweep_n = 0
        sweep_t0 = 0.0
        sweep_results = []
        # guided lift-test locals (persist across ticks)
        lift_running = False
        lift_alim = 0
        lift_phase = "set"
        lift_t0 = 0.0
        lift_sum = 0.0
        lift_n = 0
        lift_results = []
        lift_pinned = False
        backoff_scale = 1.0
        backoff_since = None
        while not self._halt.is_set():
            try:
                if self._ser is None:
                    self._open()
                    with self.state.lock:
                        self.state.connected = True

                now = time.monotonic()
                with self.state.lock:
                    target, cap = self.state.target, self.state.cap
                    run_mode = self.state.run_mode
                    osc_amp, osc_period = self.state.osc_amp, self.state.osc_period
                    osc_center, osc_wave = self.state.osc_center, self.state.osc_wave
                    armed, estop, tripped = self.state.armed, self.state.estop, self.state.tripped
                    trip_amps, trip_ms = self.state.trip_amps, self.state.trip_ms
                    temp_trip, heat_budget, heat_now = self.state.temp_trip, self.state.heat_budget, self.state.heat_now
                    deadman = (now - self.state.last_contact) > DEADMAN_S
                    temps = self.state.tele.get("temp") or []
                    at_limit = bool(self.state.tele.get("at_limit"))
                    backoff_on = self.state.backoff_on
                    backoff_amps, backoff_ms = self.state.backoff_amps, self.state.backoff_ms
                    creep_kick, creep_kick_ms = self.state.creep_kick, self.state.creep_kick_ms
                    do_log = self.state.logging
                    sweep_active = self.state.sweep_active
                    sweep_step, sweep_dwell = self.state.sweep_step, self.state.sweep_dwell
                    sweep_max, sweep_dir = self.state.sweep_max, self.state.sweep_dir
                    lift_active = self.state.lift_active
                    lift_alim_start, lift_alim_step = self.state.lift_alim_start, self.state.lift_alim_step
                    lift_alim_max, lift_dwell = self.state.lift_alim_max, self.state.lift_dwell
                    lift_cmd, lift_temp_limit = self.state.lift_cmd, self.state.lift_temp_limit
                momentary = (run_mode == "jog")           # hold-to-run
                # CREEP: slow loaded creep looks like a stall, so suppress the current-stall
                # trip (like HOLD) and rely on temperature + I2t. The lift test does the
                # same on purpose — it sits AT the limit while stalled until it breaks free.
                intent = "hold" if (run_mode in ("hold", "creep") or lift_active) else "run"

                # --- fast amps + trip evaluation --------------------------- #
                amps, amps_raw = self._sample_amps()
                trip_reason = None

                # I2t leaky accumulator (both intents)
                if amps is not None and heat_budget > 0:
                    heat_now = max(0.0, heat_now + (amps * amps - HEAT_BASELINE ** 2) * CMD_PERIOD)
                    if heat_now >= heat_budget:
                        trip_reason = f"I2t overload: heat {heat_now:.0f} >= {heat_budget:.0f} A2s"

                # temperature (both intents, ground truth)
                if not trip_reason and temp_trip > 0 and temps and max(temps) >= temp_trip:
                    trip_reason = f"Overtemperature: {max(temps)}C >= {temp_trip:.0f}C"

                # current stall (RUN intent only)
                if not trip_reason and intent == "run" and amps is not None and amps >= trip_amps:
                    if over_since is None:
                        over_since = now
                    elif (now - over_since) * 1000.0 >= trip_ms:
                        trip_reason = (f"Overcurrent/stall: {amps:.1f} A >= {trip_amps:.1f} A "
                                       f"for {trip_ms} ms")
                elif amps is None or amps < trip_amps:
                    over_since = None

                if trip_reason and not tripped:
                    with self.state.lock:
                        self.state.tripped = True
                        self.state.trip_reason = trip_reason
                        self.state.armed = False
                    tripped, armed = True, False
                    self.state.push_event("TRIP: " + trip_reason)

                # --- command gate + slew ----------------------------------- #
                if run_mode == "drift":                  # auto slow sweep around a center
                    osc_phase += 2 * math.pi * CMD_PERIOD / max(osc_period, 0.5)
                    src = osc_center + osc_amp * wave(osc_wave, osc_phase)
                else:
                    src = target
                # CREEP anti-stiction kick: brief breakaway boost when starting from a stop
                if run_mode == "creep" and armed and not (estop or tripped) and abs(src) > 0:
                    if kick_start is None and abs(applied) < 1:
                        kick_start = now
                    if kick_start is not None and (now - kick_start) * 1000.0 < creep_kick_ms:
                        src = math.copysign(max(abs(src), creep_kick), src)
                else:
                    kick_start = None

                # --- characterization sweep state machine ------------------ #
                # When active, the sweep produces `src` INSTEAD of the normal
                # target/oscillator, but still flows through the SAME gate + slew
                # below. `armed` is the safety anchor: lose it (disarm/estop/trip)
                # and we abort immediately; command then returns to 0 via the gate.
                if sweep_active and (not armed or estop or tripped):
                    sweep_active = sweep_running = False
                    with self.state.lock:
                        self.state.sweep_active = False
                        self.state.sweep_status = "aborted"
                if sweep_active:
                    if not sweep_running:                    # rising edge -> initialise
                        sweep_levels = build_levels(sweep_step, sweep_max, sweep_dir, cap)
                        sweep_idx, sweep_phase = 0, "ramp"
                        sweep_sum, sweep_n, sweep_t0 = 0.0, 0, now
                        sweep_results = []
                        sweep_running = True
                        kick_start = None
                        with self.state.lock:
                            self.state.logging = True        # capture the raw CSV
                    if sweep_idx >= len(sweep_levels):       # all levels done -> ramp to 0
                        src = 0.0
                        if abs(applied) < 1:
                            breakaway, kick = compute_breakaway(sweep_results, sweep_step)
                            with self.state.lock:
                                self.state.sweep_results = list(sweep_results)
                                self.state.sweep_breakaway = breakaway
                                self.state.sweep_kick = kick
                                self.state.sweep_status = "done"
                                self.state.sweep_active = False
                                self.state.sweep_progress = 1.0
                                self.state.sweep_level = 0
                            self.state.push_event("SWEEP done: breakaway %s, suggested kick %s"
                                                  % (breakaway, kick))
                            sweep_active = sweep_running = False
                    else:
                        level = sweep_levels[sweep_idx]
                        src = float(level)
                        if sweep_phase == "ramp":            # wait for slew to reach the level
                            if abs(applied - level) < 1.0:
                                sweep_phase, sweep_t0 = "dwell", now
                                sweep_sum, sweep_n = 0.0, 0
                        elif sweep_phase == "dwell":
                            elapsed = now - sweep_t0
                            if elapsed >= 0.4 * sweep_dwell and amps is not None:
                                sweep_sum += amps            # average over the settled tail
                                sweep_n += 1
                            if elapsed >= sweep_dwell:
                                avg = (sweep_sum / sweep_n) if sweep_n else (amps if amps is not None else 0.0)
                                sweep_results.append({"cmd": int(level), "amps": round(avg, 2)})
                                self.state.push_event("SWEEP point: cmd %d -> %.2f A" % (level, avg))
                                sweep_idx += 1
                                sweep_phase = "ramp"
                        with self.state.lock:
                            self.state.sweep_progress = sweep_idx / len(sweep_levels) if sweep_levels else 1.0
                            self.state.sweep_level = int(level)
                            self.state.sweep_status = ("running · %d/%d cmd %d · %s"
                                                       % (sweep_idx + 1, len(sweep_levels), level, sweep_phase))
                elif sweep_running:                          # externally aborted (on=0)
                    sweep_running = False

                # --- guided LIFT TEST state machine ------------------------ #
                # Holds a slow command and steps ALIM up rung by rung. Detects
                # "lifted" when measured amps fall below the limit (no longer
                # current-clamped = the motor broke free and is turning). Aborts
                # on disarm/estop/trip and RESTORES the safe start limit.
                lift_end = None
                if lift_active and (not armed or estop or tripped):
                    lift_end = ("aborted (disarm/estop/trip)", False, None)
                elif lift_running and not lift_active:        # external abort (on=0)
                    lift_end = ("aborted", False, None)
                elif lift_active:
                    if not lift_running:
                        lift_alim, lift_phase, lift_results = lift_alim_start, "set", []
                        lift_pinned = False
                        lift_running = True
                        with self.state.lock:
                            self.state.logging = True
                    src = clamp(float(lift_cmd), -cap, cap)   # hold the slow lift command
                    if lift_phase == "set":
                        self._write_config("ALIM", "1", str(int(lift_alim)))
                        lift_phase, lift_t0, lift_sum, lift_n = "settle", now, 0.0, 0
                        with self.state.lock:
                            self.state.expected["ALIM 1"] = str(int(lift_alim))   # keep drift monitor in step
                            self.state.mon["ALIM 1"] = str(int(lift_alim))
                            self.state.lift_alim_cur = round(lift_alim / 10.0, 1)
                            self.state.lift_status = "testing ALIM %.1f A" % (lift_alim / 10.0)
                        self.state.push_event("LIFT: set ALIM %.1f A" % (lift_alim / 10.0))
                    elif lift_phase == "settle":
                        if (now - lift_t0) >= 0.4 * lift_dwell:
                            lift_phase, lift_t0, lift_sum, lift_n = "dwell", now, 0.0, 0
                    elif lift_phase == "dwell":
                        if amps is not None:
                            lift_sum += amps
                            lift_n += 1
                        if (now - lift_t0) >= 0.6 * lift_dwell:
                            avg = (lift_sum / lift_n) if lift_n else (amps if amps is not None else 0.0)
                            tmax = max(temps) if temps else None
                            alim_a = lift_alim / 10.0
                            if avg >= 0.9 * alim_a:            # it actually pinned at the limit (stalled)
                                lift_pinned = True
                            # only trust "amps dropped below limit = turning" AFTER it has pinned;
                            # otherwise low amps just mean the command is too weak to reach the limit.
                            lifted = lift_pinned and avg < 0.85 * alim_a
                            lift_results.append({"alim": round(alim_a, 1), "amps": round(avg, 2),
                                                 "temp": tmax, "lifted": lifted, "pinned": lift_pinned})
                            with self.state.lock:
                                self.state.lift_results = list(lift_results)
                            self.state.push_event("LIFT rung: ALIM %.1f A -> %.1f A%s"
                                                  % (alim_a, avg, " PINNED" if lift_pinned else ""))
                            if lifted:
                                lift_end = ("LIFTED at %.1f A — load draws %.1f A" % (alim_a, avg), True, avg)
                            elif tmax is not None and tmax >= lift_temp_limit:
                                lift_end = ("stopped: %d C >= %.0f C limit" % (tmax, lift_temp_limit), False, None)
                            elif lift_alim + lift_alim_step > lift_alim_max:
                                if lift_pinned:
                                    lift_end = ("ceiling %.1f A reached, did not lift — load needs more torque"
                                                % (lift_alim_max / 10.0), False, None)
                                else:
                                    lift_end = ("never reached the current limit — raise the HOLD CMD so the "
                                                "motor pushes to the limit", False, None)
                            else:
                                lift_alim += lift_alim_step
                                lift_phase = "set"
                if lift_end is not None:
                    status, keep_alim, peak = lift_end
                    self.state.push_event("LIFT end: " + status)
                    if not keep_alim:                          # restore the safe start limit
                        try:
                            self._write_config("ALIM", "1", str(int(lift_alim_start)))
                        except Exception:
                            pass
                        with self.state.lock:
                            self.state.expected["ALIM 1"] = str(int(lift_alim_start))
                            self.state.mon["ALIM 1"] = str(int(lift_alim_start))
                    with self.state.lock:
                        self.state.lift_active = False
                        self.state.lift_status = status
                        self.state.lift_lifted = peak is not None
                        if peak is not None:
                            self.state.lift_peak_amps = round(peak, 2)
                        self.state.target = 0.0
                    lift_active = lift_running = False
                    src = 0.0

                if sweep_running or lift_running:            # routine drives itself; no deadman gate
                    momentary = False

                # --- OVERTORQUE BACKOFF ------------------------------------ #
                # When pinned at the current limit (amps high or AT-LIMIT flag),
                # gently ramp the command DOWN to relieve torque so the drivetrain
                # can't wind up and break free violently. Recovers slowly once
                # relieved. Suppressed during the deliberate sweep / lift test.
                if backoff_on and not sweep_running and not lift_running:
                    overt = (amps is not None and amps >= backoff_amps) or at_limit
                    if overt:
                        if backoff_since is None:
                            backoff_since = now
                        elif (now - backoff_since) * 1000.0 >= backoff_ms:
                            backoff_scale = max(0.0, backoff_scale - BACKOFF_DOWN)
                    else:
                        backoff_since = None
                        if backoff_scale < 1.0:
                            backoff_scale = min(1.0, backoff_scale + BACKOFF_UP)
                    src = src * backoff_scale
                else:
                    backoff_since = None
                    if backoff_scale < 1.0:                   # recover when not applicable
                        backoff_scale = min(1.0, backoff_scale + BACKOFF_UP)

                if estop or tripped or not armed:
                    desired = 0.0
                elif momentary and deadman:
                    desired = 0.0
                else:
                    desired = clamp(src, -cap, cap)
                if applied < desired:
                    applied = min(desired, applied + SLEW_PER_TICK)
                elif applied > desired:
                    applied = max(desired, applied - SLEW_PER_TICK)

                self._txrx(f"!G 1 {int(round(applied))}", None)   # feeds ^RWD

                # --- one aux op: config write (priority) or read ----------- #
                with self.state.lock:
                    pending = self.state.config_queue.pop(0) if self.state.config_queue else None
                cfg_result = None
                if pending is not None:
                    if pending.get("flash"):
                        self._txrx("%EESAV", None)
                        cfg_result = {"key": "%EESAV", "val": "-", "readback": "sent", "ok": True,
                                      "t": time.strftime("%H:%M:%S")}
                    else:
                        rb, ok = self._write_config(pending["key"], pending.get("idx"), pending["val"])
                        cfg_result = {"key": pending["key"] + (f" {pending['idx']}" if pending.get("idx") else ""),
                                      "val": str(pending["val"]), "readback": rb, "ok": ok,
                                      "t": time.strftime("%H:%M:%S")}
                    prof_key = prof_val = aux_query = aux_val = mon_label = mon_val = None
                else:
                    aux = AUX[self._qi % len(AUX)]
                    self._qi += 1
                    parts = aux.split()
                    tok = parts[0]
                    key = tok.lstrip("~?")
                    aidx = parts[1] if len(parts) > 1 else None
                    reply = self._txrx(aux, key + "=")
                    prof_key = prof_val = aux_query = aux_val = mon_label = mon_val = None
                    if reply and "=" in reply:
                        val = reply.split("=", 1)[1]
                        if aux[0] == "~":
                            prof_key, prof_val = key, val
                            mon_label, mon_val = key + (" " + aidx if aidx else ""), val
                        else:
                            aux_query, aux_val = tok, val

                # --- commit shared state ----------------------------------- #
                with self.state.lock:
                    self.state.applied = applied
                    self.state.deadman = deadman
                    self.state.heat_now = heat_now
                    self.state.mode = "momentary" if momentary else "latched"
                    self.state.intent = intent
                    self.state.backoff_scale = backoff_scale
                    self.state.backoff_active = backoff_scale < 0.999
                    if amps_raw is not None:
                        decode("?A", amps_raw, self.state.tele)
                    if aux_query is not None:
                        decode(aux_query, aux_val, self.state.tele)
                    if prof_key is not None:
                        self.state.profile[prof_key] = prof_val
                    if mon_label is not None and mon_label in self.state.expected:
                        self.state.mon[mon_label] = mon_val
                    if cfg_result is not None:
                        self.state.config_log.insert(0, cfg_result)
                        del self.state.config_log[20:]
                        self.state.push_event("CONFIG %s = %s (%s)" % (
                            cfg_result["key"], cfg_result["val"],
                            "ok" if cfg_result.get("ok") else "FAIL"))
                        if cfg_result.get("ok") and not pending.get("flash") and cfg_result["readback"] is not None:
                            self.state.profile[pending["key"]] = cfg_result["readback"]
                            wlabel = pending["key"] + (" " + pending["idx"] if pending.get("idx") else "")
                            if wlabel in self.state.expected:            # writing sets the new baseline
                                self.state.expected[wlabel] = cfg_result["readback"]
                                self.state.mon[wlabel] = cfg_result["readback"]

                # --- characterization logging (~5 Hz telemetry + events) --- #
                if do_log and logf is None:
                    logf, log_t0, log_tick = self._open_log(), now, 0
                elif not do_log and logf is not None:
                    logf.close()
                    logf = None
                if logf is not None:
                    log_tick += 1
                    with self.state.lock:
                        v = self.state.tele.get("volts_batt")
                        tl = self.state.tele.get("temp") or []
                        reason = self.state.trip_reason
                        evs = self.state.events
                        self.state.events = []
                    base = [time.strftime("%H:%M:%S"), "%.2f" % (now - log_t0), run_mode,
                            int(round(target)), int(round(applied)),
                            ("%.1f" % amps) if amps is not None else "",
                            ("%.1f" % v) if v is not None else "",
                            (max(tl) if tl else ""), "%.0f" % heat_now,
                            1 if tripped else 0, reason.replace(",", ";")]
                    prefix = ",".join(str(c) for c in base)
                    n = 0
                    for e in evs:                        # event rows: telemetry context + the event
                        logf.write(prefix + "," + str(e).replace(",", ";") + "\n")
                        n += 1
                    if log_tick % 3 == 0:                # periodic telemetry row (~5 Hz)
                        logf.write(prefix + ",\n")
                        n += 1
                    if n:
                        logf.flush()
                        with self.state.lock:
                            self.state.log_rows += n
                elif self.state.events:                  # not logging -> discard
                    with self.state.lock:
                        self.state.events = []

                time.sleep(CMD_PERIOD)
            except Exception as exc:
                with self.state.lock:
                    self.state.connected = False
                    self.state.applied = 0.0
                applied = 0.0
                try:
                    if self._ser:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None
                time.sleep(0.5)

        if logf is not None:
            try:
                logf.close()
            except Exception:
                pass
        try:
            if self._ser:
                for _ in range(5):
                    self._txrx("!G 1 0", None)
                    time.sleep(0.02)
                self._ser.close()
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    state = None

    def log_message(self, *a):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _num(self, q, key, default):
        try:
            return float(q.get(key, [str(default)])[0])
        except (ValueError, TypeError):
            return default

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        st = self.state
        with st.lock:
            st.last_contact = time.monotonic()

        if u.path == "/":
            try:
                body = UI_FILE.read_bytes()
            except OSError:
                body = b"<h1>ui.html not found next to roto_bench.py</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/state":
            self._json(st.snapshot())
        elif u.path == "/api/set":
            with st.lock:
                st.target = clamp(self._num(q, "g", 0), -1000, 1000)
            self._json({"ok": True})
        elif u.path == "/api/arm":
            on = q.get("on", ["0"])[0] == "1"
            with st.lock:
                st.armed = on and not st.estop and not st.tripped
            self._json({"ok": True})
        elif u.path == "/api/runmode":
            m = q.get("m", ["jog"])[0]
            with st.lock:
                st.run_mode = m if m in ("jog", "cruise", "drift", "hold", "creep") else "jog"
            self._json({"ok": True})
        elif u.path == "/api/creep":
            with st.lock:
                st.creep_kick = clamp(self._num(q, "kick", st.creep_kick), 0, 1000)
                st.creep_kick_ms = int(clamp(self._num(q, "ms", st.creep_kick_ms), 0, 3000))
            self._json({"ok": True})
        elif u.path == "/api/log":
            with st.lock:
                st.logging = q.get("on", ["0"])[0] == "1"
            self._json({"ok": True})
        elif u.path == "/api/osc":
            with st.lock:
                st.osc_amp = clamp(self._num(q, "amp", st.osc_amp), 0, 1000)
                st.osc_period = clamp(self._num(q, "period", st.osc_period), 0.5, 600)
                st.osc_center = clamp(self._num(q, "center", st.osc_center), -1000, 1000)
                w = q.get("wave", [st.osc_wave])[0]
                st.osc_wave = w if w in ("sine", "triangle", "saw") else st.osc_wave
            self._json({"ok": True})
        elif u.path == "/api/reapply":
            with st.lock:
                for label, val in st.expected.items():
                    p = label.split()
                    st.config_queue.append({"key": p[0], "idx": p[1] if len(p) > 1 else None, "val": val})
            self._json({"ok": True})
        elif u.path == "/api/estop":
            with st.lock:
                st.estop = True
                st.armed = False
                st.target = 0.0
            st.push_event("E-STOP pressed")
            self._json({"ok": True})
        elif u.path == "/api/clear":
            with st.lock:
                st.estop = False
            self._json({"ok": True})
        elif u.path == "/api/resettrip":
            with st.lock:
                st.tripped = False
                st.trip_reason = ""
                st.heat_now = 0.0
            self._json({"ok": True})
        elif u.path == "/api/trip":
            with st.lock:
                st.trip_amps = clamp(self._num(q, "amps", st.trip_amps), 0.1, AMP_LIMIT * 3)
                st.trip_ms = int(clamp(self._num(q, "ms", st.trip_ms), 50, 10000))
            self._json({"ok": True})
        elif u.path == "/api/protect":
            with st.lock:
                st.temp_trip = clamp(self._num(q, "temp", st.temp_trip), 0, 150)
                st.heat_budget = clamp(self._num(q, "heat", st.heat_budget), 0, 100000)
            self._json({"ok": True})
        elif u.path == "/api/backoff":
            with st.lock:
                st.backoff_on = q.get("on", ["1" if st.backoff_on else "0"])[0] == "1"
                st.backoff_amps = clamp(self._num(q, "amps", st.backoff_amps), 0.1, 200)
                st.backoff_ms = int(clamp(self._num(q, "ms", st.backoff_ms), 50, 10000))
            self._json({"ok": True})
        elif u.path == "/api/cap":
            with st.lock:
                st.cap = int(clamp(self._num(q, "v", DEFAULT_CAP), 0, MAX_CAP))
            self._json({"ok": True})
        elif u.path == "/api/config":
            key = q.get("key", [""])[0].upper()
            if key not in CONFIG_WHITELIST:
                self._json({"ok": False, "err": "key not allowed"})
                return
            idx = q.get("idx", [None])[0]
            val = q.get("val", [""])[0]
            try:
                val = str(int(float(val)))
            except (ValueError, TypeError):
                self._json({"ok": False, "err": "bad value"})
                return
            with st.lock:
                st.config_queue.append({"key": key, "idx": idx, "val": val})
            self._json({"ok": True, "queued": True})
        elif u.path == "/api/config_flash":
            with st.lock:
                st.config_queue.append({"flash": True})
            self._json({"ok": True})
        elif u.path == "/api/sweep":
            on = q.get("on", ["0"])[0] == "1"
            with st.lock:
                if on:
                    st.sweep_step = int(clamp(self._num(q, "step", st.sweep_step), 1, 1000))
                    st.sweep_dwell = clamp(self._num(q, "dwell", st.sweep_dwell), 0.2, 30)
                    st.sweep_max = int(clamp(self._num(q, "max", st.sweep_max), 0, st.cap))
                    d = q.get("dir", [st.sweep_dir])[0]
                    st.sweep_dir = d if d in ("fwd", "rev", "both") else st.sweep_dir
                    st.lift_active = False               # mutually exclusive with lift test
                    st.sweep_active = True
                    st.sweep_status = "starting"
                    st.sweep_results = []
                    st.sweep_breakaway = st.sweep_kick = None
                    st.sweep_progress = 0.0
                    st.push_event("SWEEP START: step %d, max %d, dir %s"
                                  % (st.sweep_step, st.sweep_max, st.sweep_dir))
                else:
                    st.sweep_active = False
                    st.sweep_status = "aborted"
            self._json({"ok": True})
        elif u.path == "/api/lift":
            on = q.get("on", ["0"])[0] == "1"
            with st.lock:
                if on:
                    st.lift_alim_start = int(clamp(self._num(q, "start", st.lift_alim_start), 10, 600))
                    st.lift_alim_step = int(clamp(self._num(q, "step", st.lift_alim_step), 5, 200))
                    st.lift_alim_max = int(clamp(self._num(q, "max", st.lift_alim_max), st.lift_alim_start, 600))
                    st.lift_dwell = clamp(self._num(q, "dwell", st.lift_dwell), 0.5, 15)
                    st.lift_cmd = int(clamp(self._num(q, "cmd", st.lift_cmd), -1000, 1000))
                    st.lift_temp_limit = clamp(self._num(q, "temp", st.lift_temp_limit), 0, 120)
                    st.sweep_active = False              # mutually exclusive with sweep
                    st.lift_active = True
                    st.lift_status = "starting"
                    st.lift_results = []
                    st.lift_peak_amps = None
                    st.lift_lifted = False
                    st.push_event("LIFT START: %.1f-%.1f A step %.1f, hold %d, dwell %.1fs"
                                  % (st.lift_alim_start / 10.0, st.lift_alim_max / 10.0,
                                     st.lift_alim_step / 10.0, st.lift_cmd, st.lift_dwell))
                else:
                    st.lift_active = False
                    st.lift_status = "aborted"
                    st.push_event("LIFT aborted by operator")
            self._json({"ok": True})
        elif u.path == "/api/preset_save":
            name = q.get("name", [""])[0].strip()
            safe = safe_preset_name(name)
            with st.lock:
                results = list(st.sweep_results)
                obj = {"name": name, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "params": {"step": st.sweep_step, "dwell": st.sweep_dwell,
                                  "max": st.sweep_max, "dir": st.sweep_dir},
                       "results": results, "breakaway": st.sweep_breakaway,
                       "suggested_kick": st.sweep_kick}
            if not safe or not results:
                self._json({"ok": False, "err": "need a name and a completed sweep"})
                return
            PRESET_DIR.mkdir(exist_ok=True)
            (PRESET_DIR / (safe + ".json")).write_text(json.dumps(obj, indent=2))
            self._json({"ok": True, "name": safe})
        elif u.path == "/api/preset_list":
            self._json({"ok": True, "presets": preset_names()})
        elif u.path == "/api/preset_load":
            safe = safe_preset_name(q.get("name", [""])[0])
            f = PRESET_DIR / (safe + ".json")
            if not safe or not f.exists():
                self._json({"ok": False, "err": "not found"})
                return
            try:
                obj = json.loads(f.read_text())
            except (OSError, ValueError):
                self._json({"ok": False, "err": "bad preset file"})
                return
            with st.lock:
                st.baseline = obj
            self._json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()


def discover_port(explicit):
    if explicit:
        return explicit
    for pat in PORT_GLOBS:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    sys.exit("No serial port found. Plug in the HDC2450 or pass --port.")


def main():
    ap = argparse.ArgumentParser(description="HDC2450 bench/run control console.")
    ap.add_argument("--port", help="serial port (auto-detect if omitted)")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP, help="initial command cap /1000")
    args = ap.parse_args()
    if serial is None:
        sys.exit("pyserial not installed:  pip install pyserial")

    port = discover_port(args.port)
    state = State(clamp(args.cap, 0, MAX_CAP))
    # Load the most-recent characterization preset for DISPLAY only (reference
    # baseline in the UI). This never moves the motor and never starts a sweep.
    mr = most_recent_preset()
    if mr is not None:
        try:
            state.baseline = json.loads(mr.read_text())
        except (OSError, ValueError):
            pass
    worker = Worker(state, port)
    worker.start()

    Handler.state = state
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 60)
    print("  RA Roto — control console")
    print(f"  serial : {port} @ {BAUD}")
    print(f"  web UI : http://{HOST}:{PORT}")
    print(f"  trips  : stall {TRIP_AMPS_DEFAULT}A/{TRIP_MS_DEFAULT}ms (RUN) · "
          f"temp {TEMP_TRIP_DEFAULT:.0f}C · I2t {HEAT_BUDGET_DEFAULT:.0f}")
    print("  safety : DISARMED at start · power the motor from a current-limited supply")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping motor and shutting down...")
    finally:
        worker.stop()
        worker.join(timeout=2)
        httpd.server_close()


if __name__ == "__main__":
    main()
