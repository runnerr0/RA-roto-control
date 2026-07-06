# DMX Personas & Speed Scaling

How incoming DMX/Art-Net/sACN values map to the HDC2450 motor command. Personas select a **command
range** (coarse behaviour + ultra-slow modes); a live **web multiplier** trims within that range.

The firmware works in a **normalized command `c ∈ [-1, 1]`** (0 = stop, +1 = full forward, −1 = full
reverse). `SerialController` scales that to the HDC2450's `!G` range: `g = round(c × 1000)`.

---

## Concept

The HDC2450 speed is proportional to the command value. Two levers:

1. **Persona** — picks the command window the full DMX range maps onto. A *narrower* window = lower top
   speed but the **same DMX resolution spread over a smaller speed band** → finer, slower control
   ("ultra-slow mode").
2. **Multiplier** (web UI, 0.00–1.00, live) — scales the mapped output within the persona window.

Serial gives effectively continuous resolution — `!G` spans −1000..+1000 (2000 steps) and the
controller's internal loop is finer still — so even a narrow ultra-slow window stays smooth (no DAC
quantization to worry about; this is a win over the retired analog path).

| Persona window | Command range | Feel |
|----------------|--------------|------|
| Full | 0 → ±1000 | Full speed |
| Half (slow) | 0 → ±500 | Half top speed, fine |
| Quarter (ultra-slow) | 0 → ±250 | Crawl, very fine |

---

## Direction models

- **Bidirectional** (default): DMX center = stop; below center = one direction, above = the other;
  speed grows toward the extremes. `c ∈ [-1, 1]`.
- **Unidirectional**: forward only, `c ∈ [0, 1]` (DMX 0 = stop).

Firmware persona flag picks the math; no Roborun+ reconfig needed.

---

## Persona definitions (v1)

`c` = normalized command in [-1,1]. `m` = web multiplier (0–1). `d` = DMX normalized to 0.0–1.0
(8-bit: `dmx/255`; 16-bit: `(coarse*256+fine)/65535`).

### P1 — Full · Unidirectional (1 ch, 8-bit)
```
c = d * m               # 0 (stop) → +1 (full fwd)
```
One DMX channel. Stop at DMX 0. (Use when the roto only ever spins one way.)

### P2 — Full · Unidirectional · 16-bit (2 ch)
```
c = d16 * m             # coarse+fine channels for buttery ramps
```

### P3 — Ultra-Slow ½ · Unidirectional (1 ch, 8-bit)
```
c = d * m * 0.5         # 0 → +0.5
```

### P4 — Ultra-Slow ¼ · Unidirectional (1 ch, 8-bit)
```
c = d * m * 0.25        # 0 → +0.25
```

### P5 — Full · Bidirectional (1 ch, 8-bit) — **default persona**
```
b = deadband((d - 0.5) * 2)   # -1..+1, center at DMX 128
c = b * m                     # -1 (full rev) .. 0 (stop) .. +1 (full fwd)
```
Continuous deadband around DMX 128 (configurable ± counts) guarantees a true stop at center.

### P6 — Ultra-Slow · Bidirectional (1 ch, 8-bit)
```
c = deadband((d - 0.5) * 2) * m * 0.25    # +/-25% either direction, fine
```

### P7 — Full · Bidirectional · 16-bit (2 ch)
16-bit version of P5 for smooth reversible slow motion.

> All personas clamp `c` to the valid range. `SerialController` maps `c → !G g` (±1000).

---

## Global parameters (web UI, persisted)

| Param | Range | Effect |
|-------|-------|--------|
| `persona` | P1–P7 | Active mapping (default P5) |
| `dmxStart` | 1–512 | Start address (footprint = 1 or 2 ch) |
| `multiplier` | 0.00–1.00 | Live output scale within persona window |
| `deadband` | 0–40 DMX counts | Stop zone around center (bidirectional) |
| `slewLimit` | command units/s | Max rate-of-change on `c` (protects mechanics); 0 = off |
| `invert` | bool | Flip direction sense |

The **fail-safe command is always 0 (stop)** — no separate parameter. On boot, link-loss, source-stale,
or e-stop, `SafetyStage` slews the command to 0, and the HDC2450's `^RWD` watchdog independently stops
the motor if our command stream dies.

**Slew limiting** is applied after persona math, before the command is sent — a snapped DMX jump can't
slam the motor.

---

## Manual override (web UI)

A master **OVERRIDE** toggle takes control away from DMX/Art-Net/sACN and exposes a direct slider
(0 = full reverse, 50 = stop, 100 = full forward, fed through the active persona). While engaged:
- Incoming network/DMX values are ignored (still displayed for reference).
- The same `slewLimit` and clamps apply.
- A visible banner marks the override state.
