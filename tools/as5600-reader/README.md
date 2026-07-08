# AS5600 Encoder Add-on (`as5600-reader`)

An **optional** magnetic-encoder add-on that gives the RA Roto control console real closed-loop
motion feedback — **actual RPM** of the fixture, and a **TRUE STALL** trip. Everything here is off by
default; you **enable and debug it entirely from the console UI** (⚙ Settings → Encoder card).

## Why

The console drives the HDC2450 **open-loop**: `!G` command ≈ voltage, no idea what the shaft is doing.
Current alone can't tell a **jam** from a **loaded hold** — both draw amps at near-zero motion. An
AS5600 on the shaft closes that gap: it reports whether the thing is *actually turning*, so the console
can show true RPM and stop the motor when it's commanded to move but isn't.

## Architecture — the simplest path

The AS5600 is **I2C**, and a laptop has no I2C. So a small MCU bridges it: a cheap Arduino / ESP32 /
Pico reads the AS5600 over I2C and streams angle + RPM over **USB serial** — a second serial port the
console reads alongside the HDC2450 port. (More robust than a USB-I2C dongle, and you probably have a
spare board.)

```
AS5600 ──I2C──► MCU (bridge) ──USB serial──► laptop ──► roto console
                as5600_reader.ino            (EncoderReader thread)
```

---

## Firmware — `as5600_reader.ino`

Reads the AS5600 (I2C addr **0x36**, `RAW_ANGLE` reg **0x0C**, 12-bit → **4096 counts/rev**),
**unwraps** each reading across the 4095↔0 seam into a cumulative position, computes **SIGNED RPM**
(direction-aware — the absolute-angle sensor gives sign for free), and reads the **MD** (magnet-detect)
bit from the status register (0x0B).

- **Stream:** ~10 Hz, **115200 baud**, one line per report:

  ```
  ANG=<0-4095> POS=<cumulative_counts> RPM=<signed float> MAG=<0|1> STALL=<0|1>
  ```

  (`STALL` here is just the firmware's own `|rpm| < 0.5` flag; the console does the real
  commanded-vs-moving trip logic.)

- **Wiring** (from the sketch header; check your board's I2C pins):

  | AS5600 | MCU |
  |--------|-----|
  | VCC | **3.3 V** |
  | GND | GND |
  | SDA | board SDA (Uno/Nano A4, ESP32 GPIO21, Pico GP4) |
  | SCL | board SCL (Uno/Nano A5, ESP32 GPIO22, Pico GP5) |

  The AS5600 is a **3.3 V** part — on a 5 V board (Uno/Nano) **level-shift SDA/SCL** or use a
  3.3 V-logic board / ESP32 / Pico. The **diametrically-magnetised** magnet mounts on the shaft's
  **END face**, centred on the die, **~1–2 mm** gap.

---

## Console integration

Everything is driven from the console — no config files.

- **⚙ Settings → Encoder card:** an **enable** toggle, a **port** dropdown (populated from
  `/api/serial_ports`), a **gear ratio** field, an **Apply** button, and a live **debug readout**:
  present/stale, magnet OK/not-detected, shaft RPM → fixture RPM, cumulative position, and the raw line.
- **Gear ratio.** The encoder rides a small cog driving the big wheel, so the shaft spins faster than
  the fixture: **fixture RPM = shaft RPM ÷ gear ratio**. Set the ratio to the encoder-shaft revs per one
  fixture revolution. The **Speed** telemetry row and the stats pop-out show real **fixture RPM** whenever
  the encoder is live (instead of the controller's `?S`).
- **TRUE STALL trip.** When commanding **≥10%** (`ENC_STALL_CMD = 100`) but the shaft reads **<1 RPM**
  (`ENC_STALL_RPM`) for **>1.2 s** (`ENC_STALL_MS`) — in a **RUN** intent, armed, not already stopped —
  the console stops the motor. This is the motion check open-loop current can't make. It's **suppressed
  in HOLD/CREEP**, which legitimately sit near 0 RPM under load. If the encoder line goes silent for
  >1.5 s (`ENC_TIMEOUT`) it's treated as absent and the trip disengages (fail-safe, not fail-active).

- **Endpoints:** `/api/encoder?on=&port=&ratio=` (enable / port / gear ratio) and `/api/serial_ports`
  (candidate ports for the dropdown).
- **Boot flags:** `--encoder <PORT>` (enable + pin the port at start) and `--gear <ratio>`.

---

## The 3D-printed mount — `as5600_mount.scad`

Parametric OpenSCAD. **NESTED, self-spacing** design: the two printed parts set the sensor-to-magnet
**air gap by nesting together** — the L-bracket does *not* set the gap.

- **Magnet carrier** — grips the shaft (M3 set screw). A **solid floor** (`bore_floor`) above the shaft
  bore ties a raised **pilot** into the body; the pilot holds the **5×2 diametric magnet** on-axis in a
  pocket at its top. The step where the pilot meets the wider body is the **shoulder**.
- **Sensor holder** — cups over the pilot: its bore is a **register** (`hub_fit`) that centres the
  AS5600 chip over the magnet, and its hub bottom **seats on the shoulder**. That seat *is* the spacer —
  it fixes the board exactly `air_gap` above the magnet, and the gap stays constant even if the shaft
  wobbles (the board rides the holder, the holder rides the carrier). The board mounts **chip-down**
  over an open central window so the die sees the magnet. The carrier **spins under** the holder; they
  rub at the seat (fine for a slow roto — a thrust washer/bearing can drop onto the pilot later).
- **Gap gauge** — a shim exactly `air_gap` thick to confirm the seated gap.
- **L-bracket** — any spare; it only pins the holder's **anti-rotation ear** (retention, not spacing).

**Board:** the 23×23 mm AS5600 module (mounting holes 16 mm c-c, 3.5 mm). **Fits** (tune to your
printer): `shaft_fit` **0.45** and `magnet_fit` **0.25** (printed-to-metal, ABS shrink room);
`hub_fit` **0.25** (printed-to-printed register — deliberately tight for concentricity, ~0.5 mm total
slop so it spins yet stays centred). Print orientations are baked into the `part` selector
(`"carrier"` / `"holder"` / `"gauge"`); exported meshes are in **`stl/`** (`as5600_carrier.stl`,
`as5600_holder.stl`, `as5600_gauge.stl`).

---

## Bring-up

1. **Flash** `as5600_reader.ino` to the MCU.
2. **Wire** the AS5600 (3.3 V, level-shift on a 5 V board), magnet on the shaft end face ~1–2 mm.
3. **Plug** the MCU into the laptop.
4. In the console: **enable** the encoder, **pick the port**, **set the gear ratio**, Apply.
5. **Spin the shaft by hand** and confirm RPM / position move and **magnet = OK**.

For the mount, **print the carrier + gauge first** to check the shaft and magnet fits, then print the
holder.
