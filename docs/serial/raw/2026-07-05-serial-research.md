# raw — serial research log — 2026-07-05

Running notes; unpolished on purpose. Compiled version → `../SERIAL-CONFIG.md`.

## Trigger
Wanted RoboRun+ on macOS to set up the HDC2450. RoboRun+ is Windows-only
(`RoborunPlus.exe`), talks to controller over a virtual COM port (USB/RS232/TCP).
Realized the GUI is the easy part — the hard part is getting the controller's
serial port to whatever runs it. And then: maybe we don't need the GUI at all.

## HDC2450 USB identity (important)
- Enumerates as **USB CDC-ACM**, NOT FTDI. Linux `dmesg`: `cdc_acm ... ttyACM0`.
  → macOS = `/dev/tty.usbmodem*`, **no driver needed**.
- Serial params: **115200 8N1 no flow**. 3 wires for RS232 (Rx/Tx/GND).
- Forum lore: USB link is **EMI-sensitive** — "firing off a relay pulls the USB
  offline"; USB described as "not robust." RS232 more reliable under load.
- Can't use CAN + USB simultaneously; CAN + RS232 is OK.
- src: roboteq forum threads (hdc2450 on linux with usb; hdc2450 serial
  communication; unable to establish connection with USB in HDC2450).

## Protocol verbs (ADMC family — HDC2450 is one)
- `^` SetConfig (RAM), `~` GetConfig, `!` runtime cmd, `?` runtime query,
  `%` maintenance. `%EESAV` = save RAM→flash. `?FID` = firmware id.
- Echo ON by default; `^ECHOF 1` disables. Replies `+`/`-`.
- Watchdog (`RWD`) guards SERIAL only. Analog holds last voltage → our firmware
  must own the fail-safe. (Already in ARCHITECTURE.md safety model.)

## Running RoboRun+ on mac — options considered
1. **VM + USB passthrough** (UTM free / Parallels smooth / VMware Fusion free).
   Most reliable: raw USB device → Windows loads CDC driver → COM port → RoboRun+
   auto-scans. Win11 ARM emulates the x86 exe fine.
2. **Wine/Whisky/CrossOver** — launches GUI but CDC→COM bridging is fiddly &
   unreliable. Skip for writing config to hardware.
3. **Skip Windows entirely** — controller is already `/dev/tty.usbmodem*`, speaks
   ASCII. Send `^`/`~` from pyserial. ← chose this. Became `tools/roto-setup/`.
   RoboRun+ only truly needed for firmware update / config-tree GUI / live charts
   / MicroBasic. None of which our analog bridge needs.

## Library survey (see compiled doc for links)
- PyRoboteq (pip) — pyserial wrapper, tested SDC2130/SBL2360T. Good framing base.
- brettpac/Roboteq-Linux-API — vendor RoboteqDevice port, SetConfig/GetConfig +
  sample.cpp = authoritative config semantics.
- rbonghi/roboteq_control (ROS) — controls ALL params incl analog ports; HDC24xx.
- g/roboteq roboteq_driver (ROS) — HDC24xx, ttyACM0@115200 (matches us).
- niclaslind/arduino-roboteq — PlatformIO lib_deps; has readConvertedAnalogCommand
  (read back the analog cmd the controller sees — nice chain integrity check).
- kippandrew/Arduino-RobotEQ, Azrrael-exe/Ard-Roboteq (AX2550) — simpler arduino.
- Caveat across all: command SET is shared, but config item indices/defaults vary
  by controller+firmware. Borrow framing, verify the numbers.

## Tool decisions (roto_setup.py)
- Config-only, never `!`. Dry-run default. Verify every write via read-back.
- RAM until `--save` (%EESAV). `--audit` read-only. Placeholder (null/TODO) values
  SKIPPED so we can't flash a stub. Manifest-driven (JSON), values are DATA.
- Echo-tolerant line parser (works echo on/off), FID as connection check.
- Smoke-tested framing/diff/verify with a fake controller. Real-hardware TODO.

## ESP32-over-serial — thinking (→ compiled §6)
Idea: ESP32 also speaks serial to HDC2450. Closes 2 named gaps: no controller
telemetry, no analog command-loss watchdog.
- HW cost: DB25 is RS232 not TTL → need **MAX3232**. 2 GPIOs. Reuse pin-5 GND.
- Pins: RMII owns 0/12/18/19/21/22/23/25/26/27. Taken: 35,36,39,32,13,16.
  Candidate TX=33 RX=34(input-only ok). VERIFY on POE-ISO Rev M schematic.
- **A (recommended):** analog command stays; serial = read-only telemetry +
  optional boot config-assert. Additive, off the motion-critical path, fills the
  telemetry gap already in the roadmap.
- **B:** serial command replaces analog. Simpler BOM, digital precision, gets the
  RS232 watchdog — BUT re-opens locked decision + reliability risk + streaming
  requirement. Only via a deliberate logged decision.
- **C:** serial config-only from ESP32. Low value vs the host tool (which needs no
  extra HW). Only if there's a field re-config need.
- Firmware: `RoboteqLink` module → feeds existing `Telemetry`. Poll 5–10Hz.
  Cross-check readConvertedAnalogCommand vs SenseADC = analog-chain integrity test.

## Next actions
- Verify mnemonics/values vs HDC2450 reference; fill ALIM/OVL/UVL; AINA bitmask.
- Confirm %EESAV arg-less on this rev.
- Decide A/B/C (leaning A). If A: pick MAX3232 breakout, add serial to DB25 hood
  pinout in HARDWARE.md, add RoboteqLink to ARCHITECTURE.md module map.
- Run roto_setup.py --audit against the real controller (motor power OFF).
