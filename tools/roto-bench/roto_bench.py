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
from __future__ import annotations

import argparse
import glob
import json
import sys
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

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
HOST, PORT = "127.0.0.1", 8791
UI_FILE = Path(__file__).parent / "ui.html"
PORT_GLOBS = ["/dev/cu.usbmodemRTQ*", "/dev/cu.usbmodem*", "/dev/cu.usbserial*",
              "/dev/ttyACM*", "/dev/ttyUSB*"]
# aux ops round-robined one-per-tick: telemetry (?) + profile reads (~)
AUX = ["?V", "?T", "?FF", "?AI", "?PI", "?AIC",
       "~ALIM 1", "~MXPF 1", "~MXPR 1", "~RWD", "~ATRIG 1", "~ATGA 1", "~ATGD 1"]
CONFIG_WHITELIST = {"ALIM", "MXPF", "MXPR", "RWD", "ATRIG", "ATGA", "ATGD", "MAC", "MDEC", "AINA"}
FAULT_BITS = [(0x01, "OVERHEAT"), (0x02, "OVERVOLT"), (0x04, "UNDERVOLT"),
              (0x08, "SHORT"), (0x10, "ESTOP"), (0x20, "SEPEX-FAULT"),
              (0x40, "MOSFET-FAIL"), (0x80, "STARTUP-CFG")]


class State:
    def __init__(self, cap):
        self.lock = threading.Lock()
        self.target = 0.0
        self.applied = 0.0
        self.cap = cap
        self.armed = False
        self.estop = False
        self.mode = "momentary"          # momentary | latched
        self.intent = "run"              # run | hold
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

    def snapshot(self):
        with self.lock:
            return {
                "target": self.target, "applied": round(self.applied), "cap": self.cap,
                "armed": self.armed, "estop": self.estop, "mode": self.mode, "intent": self.intent,
                "tripped": self.tripped, "trip_reason": self.trip_reason,
                "trip_amps": self.trip_amps, "trip_ms": self.trip_ms,
                "temp_trip": self.temp_trip, "heat_budget": self.heat_budget,
                "heat_now": round(self.heat_now, 1), "amp_limit": AMP_LIMIT,
                "connected": self.connected, "deadman": self.deadman,
                "tele": dict(self.tele), "profile": dict(self.profile),
                "config_log": list(self.config_log[:8]),
            }


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


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
        over_since = None
        while not self._halt.is_set():
            try:
                if self._ser is None:
                    self._open()
                    with self.state.lock:
                        self.state.connected = True

                now = time.monotonic()
                with self.state.lock:
                    target, cap, mode, intent = self.state.target, self.state.cap, self.state.mode, self.state.intent
                    armed, estop, tripped = self.state.armed, self.state.estop, self.state.tripped
                    trip_amps, trip_ms = self.state.trip_amps, self.state.trip_ms
                    temp_trip, heat_budget, heat_now = self.state.temp_trip, self.state.heat_budget, self.state.heat_now
                    deadman = (now - self.state.last_contact) > DEADMAN_S
                    temps = self.state.tele.get("temp") or []

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

                # --- command gate + slew ----------------------------------- #
                if estop or tripped or not armed:
                    desired = 0.0
                elif mode == "momentary" and deadman:
                    desired = 0.0
                else:
                    desired = clamp(target, -cap, cap)
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
                    prof_key = prof_val = None
                    aux_query = aux_val = None
                else:
                    aux = AUX[self._qi % len(AUX)]
                    self._qi += 1
                    tok = aux.split()[0]
                    key = tok.lstrip("~?")
                    reply = self._txrx(aux, key + "=")
                    prof_key = prof_val = aux_query = aux_val = None
                    if reply and "=" in reply:
                        val = reply.split("=", 1)[1]
                        if aux[0] == "~":
                            prof_key, prof_val = key, val
                        else:
                            aux_query, aux_val = tok, val

                # --- commit shared state ----------------------------------- #
                with self.state.lock:
                    self.state.applied = applied
                    self.state.deadman = deadman
                    self.state.heat_now = heat_now
                    if amps_raw is not None:
                        decode("?A", amps_raw, self.state.tele)
                    if aux_query is not None:
                        decode(aux_query, aux_val, self.state.tele)
                    if prof_key is not None:
                        self.state.profile[prof_key] = prof_val
                    if cfg_result is not None:
                        self.state.config_log.insert(0, cfg_result)
                        del self.state.config_log[20:]
                        if cfg_result.get("ok") and not pending.get("flash") and cfg_result["readback"] is not None:
                            self.state.profile[pending["key"]] = cfg_result["readback"]

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
        elif u.path == "/api/mode":
            with st.lock:
                st.mode = "latched" if q.get("m", [""])[0] == "latched" else "momentary"
            self._json({"ok": True})
        elif u.path == "/api/intent":
            with st.lock:
                st.intent = "hold" if q.get("i", [""])[0] == "hold" else "run"
            self._json({"ok": True})
        elif u.path == "/api/estop":
            with st.lock:
                st.estop = True
                st.armed = False
                st.target = 0.0
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
