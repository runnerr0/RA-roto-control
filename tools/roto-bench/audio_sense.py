"""audio_sense.py — OPTIONAL mic-energy sensor for RA Roto (audio-reactive motion).

Captures the host microphone and produces a smoothed audio ENERGY envelope in 0..1.
Phase 1 use = a live meter only; NO motor coupling. Phase 2 maps `level` -> drift speed
INSIDE the existing safety envelope (cap/governor/slew) — never bypassing it.

Guarded: if numpy/sounddevice aren't installed, AudioSensor.available is False and the
console runs exactly as before. Install on the host with:  pip install sounddevice numpy

Control is read from the shared State (audio_enabled/device/gain/floor); results are written
back (audio_level/audio_rms/audio_present), mirroring the EncoderReader pattern.
"""

import threading
import time

try:
    import numpy as np
    import sounddevice as sd
    _AUDIO_OK = True
except Exception:
    _AUDIO_OK = False

SAMPLE_RATE = 44100
BLOCK       = 1024        # ~23 ms/frame -> ~43 updates/s
ATTACK      = 0.55        # envelope rise (fast, so beats show)
RELEASE     = 0.06        # envelope fall (slow, so it reads as energy not strobe)


class AudioSensor(threading.Thread):
    available = _AUDIO_OK

    def __init__(self, state):
        super().__init__(daemon=True)
        self.state = state
        self._stream = None
        self._cur_device = None
        self._level = 0.0
        self._ref = 1e-5          # slow-decaying recent-peak reference (auto-gain)

    @staticmethod
    def input_devices():
        if not _AUDIO_OK:
            return []
        out = []
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                out.append({"idx": i, "name": d["name"]})
        return out

    def _open(self, dev):
        self._close()
        try:
            self._stream = sd.InputStream(
                device=(dev if (dev is not None and dev >= 0) else None),
                channels=1, samplerate=SAMPLE_RATE, blocksize=BLOCK, dtype="float32")
            self._stream.start()
            self._cur_device = dev
        except Exception:
            self._stream = None

    def _close(self):
        if self._stream is not None:
            try:
                self._stream.stop(); self._stream.close()
            except Exception:
                pass
        self._stream = None
        self._cur_device = None

    def run(self):
        if not _AUDIO_OK:
            return
        st = self.state
        while True:
            with st.lock:
                enabled = st.audio_enabled
                dev     = st.audio_device
                gain    = st.audio_gain
                floor   = st.audio_floor
            if not enabled:
                if self._stream is not None:
                    self._close()
                self._level = 0.0
                with st.lock:
                    st.audio_present = False
                    st.audio_level = 0.0
                    st.audio_rms = 0.0
                time.sleep(0.2)
                continue
            if self._stream is None or dev != self._cur_device:
                self._open(dev)
                if self._stream is None:
                    with st.lock:
                        st.audio_present = False
                    time.sleep(0.3)
                    continue
            try:
                block, _ = self._stream.read(BLOCK)     # blocks ~23 ms -> paces the loop
            except Exception:
                self._close()
                time.sleep(0.2)
                continue
            x = block[:, 0]
            rms = float(np.sqrt(np.mean(x * x)) + 1e-9)
            # scale-independent auto-gain: normalise against a slow-decaying recent peak,
            # so it works on any device/venue without hand-calibrating absolute levels.
            if rms > self._ref:
                self._ref += (rms - self._ref) * 0.08      # rise to peaks (~0.3 s)
            else:
                self._ref += (rms - self._ref) * 0.001     # decay slowly (~20 s)
            self._ref = max(self._ref, 1e-5)
            norm = rms / self._ref                          # ~0..1, 1.0 at recent peaks
            v = min(1.0, max(0.0, (norm - floor) * gain))   # floor/gain act on the normalised signal
            a = ATTACK if v > self._level else RELEASE
            self._level += (v - self._level) * a
            with st.lock:
                st.audio_present = True
                st.audio_level = round(self._level, 3)
                st.audio_rms = round(rms, 4)


# --- standalone self-test: print the live level bar, no motor, no server ---
if __name__ == "__main__":
    if not _AUDIO_OK:
        raise SystemExit("audio libs missing — pip install sounddevice numpy")

    class _Mock:
        lock = threading.Lock()
        audio_enabled = True
        audio_device = None
        audio_gain = 1.5
        audio_floor = 0.08
        audio_level = 0.0
        audio_rms = 0.0
        audio_present = False

    m = _Mock()
    s = AudioSensor(m); s.start()
    print("listening on default mic for 8 s (make some noise)...")
    t0 = time.monotonic()
    while time.monotonic() - t0 < 8:
        with m.lock:
            lvl, rms, pres = m.audio_level, m.audio_rms, m.audio_present
        bar = "#" * int(lvl * 40)
        print("  level %4.2f  rms %6.4f  %-40s present=%s" % (lvl, rms, bar, pres))
        time.sleep(0.2)
