# RA Roto Control

Networked analog motor-speed controller for **Radiant Atmospheres**. Bridges show-control protocols
(**DMX512, Art-Net, sACN/E1.31**) to a **0–5V analog command** driving a **Roboteq HDC2450** brushed-DC
motor controller — with a web interface for setup, DMX personas, network config, live troubleshooting,
and manual override. Sibling project to [raDMX](../raDMX).

## What it does

```
DMX512 / Art-Net / sACN ─► ESP32-POE-ISO ─► MCP4725 (12-bit DAC) ─► op-amp (0–5V) ─► HDC2450 ─► roto motor
                                │                                                        ▲
                                └──── web UI: config · personas · override · diagnostics ┘
```

- **One motor**, controlled by a single **0–5V** analog line (speed + direction via the HDC2450's
  center-point scheme — no separate direction/enable wire needed).
- **DMX personas** including **ultra-slow modes** (compressed voltage windows) + a live **multiplier**,
  for fine slow-rotation control. See [`docs/PERSONAS.md`](docs/PERSONAS.md).
- **Wired Ethernet + PoE + galvanic isolation** (Olimex ESP32-POE-ISO) for rugged festival deployment.
- **Fail-safe by design** — analog mode has no controller-side command-loss protection, so firmware
  enforces a stop voltage on boot/link-loss/fault plus slew limiting.

## Hardware

- **Host:** Olimex ESP32-POE-ISO
- **Motor controller:** Roboteq HDC2450 (Motor 1 channel)
- **DAC:** MCP4725 (12-bit I2C) → RRIO op-amp gain ×1.515, referenced to the HDC2450's own 5V

Full pinout, wiring diagram, BOM, and electrical validation: [`docs/HARDWARE.md`](docs/HARDWARE.md).

## Docs

| Doc | Contents |
|-----|----------|
| [`CLAUDE.md`](CLAUDE.md) | Project guide, locked decisions, operational rules |
| [`docs/HARDWARE.md`](docs/HARDWARE.md) | Pinout, wiring diagram, DAC/op-amp math, BOM, validation checklist |
| [`docs/PERSONAS.md`](docs/PERSONAS.md) | DMX persona definitions + speed-scaling math |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Firmware module map, protocols, web UI, safety, roadmap |

## Status

**Phase 0 — Planning & validation.** Decisions locked, docs written, wiring validated on paper.
Next: bench-prototype the analog chain and meter-verify 0 / 2.5 / 5V before any firmware motor command.
