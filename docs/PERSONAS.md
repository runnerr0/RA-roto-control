# DMX Personas & Speed Scaling

How incoming DMX/Art-Net/sACN values map to the 0–5V analog command. Personas select a **voltage
span** (coarse behaviour + ultra-slow modes); a live **web multiplier** trims within that span.

---

## Concept

The HDC2450 speed is proportional to command voltage. Two levers:

1. **Persona** — picks the voltage window the full DMX range maps onto. A *narrower* window = lower top
   speed but the **same DMX resolution spread over a smaller speed band** → finer, slower control.
   This is the "ultra-slow mode."
2. **Multiplier** (web UI, 0.00–1.00, live) — scales the mapped output within the persona window,
   for on-the-fly trimming without changing personas.

Because the DAC is **12-bit (4096 steps)**, even a narrow window keeps plenty of resolution:

| Persona window | Voltage span | DAC codes across span | Feel |
|----------------|-------------|-----------------------|------|
| Full | 2.5→5.0V (uni) or 0→5.0V (bi) | 2048 / 4096 | Full speed |
| Half (slow) | 2.5→3.75V | 1024 | Half top speed, fine |
| Quarter (ultra-slow) | 2.5→3.125V | 512 | Crawl, very fine |

(For comparison, native 8-bit DAC would give only 64 codes on the quarter window — the reason we went MCP4725.)

---

## Direction models

The HDC2450 analog input is **center-point at 2.5V** by default:

- **Bidirectional** (default): `0V = full reverse · 2.5V = stop · 5V = full forward`.
- **Unidirectional** (roto spins one way): configure Roborun+ so `0V…5V = 0%…100% forward`, OR keep the
  center default and only use the `2.5V→5.0V` half. Firmware persona flag `direction: uni|bi` picks the math.

---

## Persona definitions (v1)

Each persona defines: DMX footprint (channels), resolution (8/16-bit), direction model, and output window.
`Vout` is the voltage delivered to AnaCmd1 (post op-amp). `m` = web multiplier (0–1). `d` = DMX value
normalized to 0.0–1.0 (8-bit: `dmx/255`; 16-bit: `(coarse*256+fine)/65535`).

### P1 — Full Range · Unidirectional (1 ch, 8-bit)
```
Vout = 2.5 + d * m * 2.5        # 2.5V(stop) → 5.0V(full fwd)
```
Default persona. One DMX channel. Stop at DMX 0.

### P2 — Full Range · Unidirectional · 16-bit (2 ch)
```
Vout = 2.5 + d16 * m * 2.5      # coarse+fine channels for buttery ramps
```
Use when smooth slow acceleration matters. Channel N = coarse, N+1 = fine.

### P3 — Ultra-Slow ½ · Unidirectional (1 ch, 8-bit)
```
Vout = 2.5 + d * m * 1.25       # 2.5V → 3.75V, half top speed, full DMX spread
```

### P4 — Ultra-Slow ¼ · Unidirectional (1 ch, 8-bit)
```
Vout = 2.5 + d * m * 0.625      # 2.5V → 3.125V, crawl
```

### P5 — Full Range · Bidirectional (1 ch, 8-bit)
```
c  = (d - 0.5) * 2              # -1..+1, center at DMX 128
Vout = 2.5 + c * m * 2.5        # 0V(full rev) .. 2.5V(stop) .. 5.0V(full fwd)
```
Deadband around DMX 128 handled in firmware (configurable ± counts) to guarantee a true stop.

### P6 — Ultra-Slow Bidirectional (1 ch, 8-bit)
```
c  = (d - 0.5) * 2
Vout = 2.5 + c * m * 0.625      # ±25% speed either direction, fine
```

### P7 — 16-bit Bidirectional (2 ch)
16-bit version of P5 for smooth reversible slow motion.

> All personas clamp `Vout` to `[0, 5]` and are calibrated against `DAC_STOP_CODE` / `DAC_MAX_CODE` from
> the HARDWARE.md validation step (measured, not assumed).

---

## Global parameters (web UI, persisted)

| Param | Range | Effect |
|-------|-------|--------|
| `persona` | P1–P7 | Active mapping |
| `dmxStart` | 1–512 | Start address (footprint = 1 or 2 ch) |
| `multiplier` | 0.00–1.00 | Live output scale within persona window |
| `deadband` | 0–20 DMX counts | Stop zone around center (bidirectional) |
| `slewLimit` | 0–5 V/s | Max rate-of-change on Vout (protects mechanics) |
| `invert` | bool | Flip direction sense |
| `failSafeV` | 0/2.5V | Voltage on link-loss / boot / fault (default = stop) |

**Slew limiting** is a first-class safety/quality feature: it caps how fast the commanded voltage can
change, preventing a snapped DMX jump from slamming the motor. Applied after persona math, before the DAC.

---

## Manual override (web UI)

A big **OVERRIDE** toggle takes control away from DMX/Art-Net/sACN and exposes a direct slider
(-100%…+100% or 0…100% per direction model). While engaged:
- Incoming network/DMX values are ignored (but still displayed for reference).
- The same `slewLimit` and clamps apply.
- A visible banner + timeout option prevents leaving it engaged accidentally.
