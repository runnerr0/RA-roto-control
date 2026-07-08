---
name: serial-bench
description: Use for quick, safe interaction with a serial device on the bench — especially the Roboteq HDC2450 motor controller — via the mcp__serial tools (list ports, open, write commands, read replies) without launching the full roto console.
---

# Serial Bench

## Purpose

Talk to a serial device directly for identification, telemetry reads, and
config, using the `mcp__serial` MCP tools. Primary target: the **Roboteq
HDC2450**.

## Tools & workflow (mcp__serial)

- `mcp__serial__list_ports` — discover ports.
- `mcp__serial__open` — open the port. HDC2450 is **115200 baud, 8 data bits, no
  parity, 1 stop bit**.
- `mcp__serial__write` — send a command. Roboteq commands are terminated with a
  carriage return `\r`.
- `mcp__serial__read` — read the reply.
- `mcp__serial__close` — close when done.

## Safe HDC2450 commands (queries — do NOT move the motor)

- `?FID` — firmware identify (good first handshake / loopback confirm).
- `?A` — motor amps (×10).
- `?V` — volts.
- `?T` — temp.
- `?FF` — fault flags.
- `?FS` — status flags.
- `~ALIM 1` — read the current limit config (and `~MXPF 1`, `~RWD`, etc. for
  other params).

## Config writes (careful — RAM until saved)

`^KEY [idx] value` writes config to RAM; `%EESAV` saves to flash.

Example: `^ALIM 1 50` sets the motor-1 current limit to **5.0 A** (units are
0.1 A).

## CRITICAL SAFETY

- **Never send `!G ...` (a motor command) casually — it moves the motor.** Use
  serial-bench for identification, telemetry, and config reads/writes by default.
  Only issue `!G` if you intend motion AND the motor is mechanically safe to move
  and current-limited.
- Confirm the link with `?FID` before trusting anything.
- The HDC2450 uses **true RS232 (±V) via a MAX3232 level shifter** — not 3.3V
  TTL.
