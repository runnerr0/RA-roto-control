# RA Roto Control — Project Guide (CLAUDE.md)

Networked motor-speed controller for **Radiant Atmospheres**. Bridges show-control protocols
(physical DMX512, Art-Net, sACN/E1.31) to **RS232 serial commands** driving a **Roboteq HDC2450**
brushed-DC motor controller, with a web interface for setup, DMX persona selection, network config,
live troubleshooting (real motor telemetry), and manual override.

Spiritual sibling of **raDMX** (`~/temp/raDMX`) — reuse its patterns: ESPAsyncWebServer dashboard,
DMX persona system, WebSocket telemetry, PlatformIO build targets, OTA.

---

## Locked Decisions (do not re-litigate without cause)

| Decision | Choice | Why |
|----------|--------|-----|
| **Compute host** | Olimex **ESP32-POE-ISO** | Wired Ethernet + PoE + galvanic isolation on one cable; instant boot; watchdog recovery; robust flash (no SD); reuses raDMX. |
| **Motor controller** | Roboteq **HDC2450** (2×150A) | Existing hardware. We use **1 channel** (Motor 1). |
| **Control interface** | **RS232 serial** — `!G 1 <-1000..+1000>` | One signed command = speed **and** direction (0 = stop). No DAC/op-amp/calibration. Full resolution. Gives telemetry back. |
| **Level shift** | **MAX3232** between ESP32 UART and DB25 pins 2/3 | HDC2450 serial is true RS232 (±V), not 3.3V TTL. USB isn't usable (classic ESP32 can't host it). |
| **Direction model** | **Bidirectional** default (persona P5): -1000 rev / **0 stop** / +1000 fwd | Confirmed real behavior: center = stop. Serial makes this trivial (signed command). |
| **Motor fail-safe** | HDC2450 **`^RWD` command-loss watchdog** (primary) + firmware STOP (secondary) | Serial watchdog actually works (analog mode doesn't) — controller self-stops if we go silent. |
| **Telemetry** | Query `?A ?V ?T ?FF` over serial | Real motor amps / battery V / temp / fault flags in the troubleshooting UI. |
| **Command scaling** | Firmware **personas** (command-range compression) + live **web multiplier** | Full / half / quarter ultra-slow ranges. See `docs/PERSONAS.md`. |
| **Remote enable** | **KF0602D** DC-DC SSR, input buffered by **S8050** off 5V, in series with manual SW1 | Isolated PwrCtrl switching; ESP-dead → power-down. See `docs/HARDWARE.md` §5. |

**Rejected:** Analog 0–5V path (DAC + op-amp) — **superseded by serial**: serial has a working command-loss
watchdog, gives telemetry, and needs no calibration or analog BOM. Raspberry Pi host (SD/boot/isolation
risks). 0–10V stage (moot — serial). Native ESP32 DAC (moot — serial).

> The MCP4725 + MCP6002 are no longer on the control path. Keep them for another project.

---

## Hardware Signal Chain

```
DMX512 (RS485) ─┐
Art-Net ────────┼─► ESP32-POE-ISO ─UART─► MAX3232 ─► DB25 pin3 (Rx) ─► HDC2450 ─► Motor 1
sACN/E1.31 ─────┘        ▲                          ◄─ DB25 pin2 (Tx) ◄─ (telemetry: ?A ?V ?T ?FF)
                         │                             GND = DB25 pin5
                    WebServer (config · override · live telemetry)
```

Full pinout, wiring diagram, BOM, and bring-up procedure: **`docs/HARDWARE.md`**.

---

## Firmware layout (`firmware/`)

`main.cpp` wires the modules; each is single-responsibility (see `docs/ARCHITECTURE.md`):
`InputMux` (source arbitration) → `PersonaEngine` (→ command [-1,1]) → `SafetyStage` (slew + stop) →
`SerialController` (`!G` + telemetry + `^RWD`). Network: `NetworkManager` (ETH), `ArtnetInput`,
`SacnInput`. `ConfigStore` (NVS), `WebInterface` (async HTTP + WS).

## Operational Rules

- **PlatformIO + Arduino-ESP32 2.0.x** (pinned via `platform = espressif32@^6.9`), C++. Never `npm`/`npx`.
  The classic `ETH.begin()` + `esp_task_wdt_init(timeout, panic)` signatures depend on this — update
  `NetworkManager`/`main.cpp` if you bump to core 3.x.
- **Verify GPIO assignments against your Olimex board revision** before soldering. Ethernet RMII owns
  GPIO 0,12,17,18,19,21,22,23,25,26,27 — never reuse. UART is on GPIO13(RX)/14(TX).
- **Hardware first**: confirm the RS232 link with a serial loopback / a manual `?FID` query before
  trusting motor commands. Meter/scope the MAX3232 lines. (Hard-won lesson: verify wiring before firmware.)
- **Motor safety is layered**: (1) HDC2450 `^RWD` watchdog self-stops on command loss; (2) firmware
  drives command to 0 on boot/link-loss/e-stop/fault; (3) `!G` is sent continuously to feed the watchdog.
  Never remove the continuous send or the `^RWD` config.
- **Never enable PwrCtrl before the firmware is commanding STOP.** Boot order: serial up → command 0 →
  power controller.
- Keep files under 500 lines. Docs in `docs/`, firmware in `firmware/`, no working files in root.

## Build & Test

```bash
cd firmware
pio run -e olimex_poe_iso            # build  (verified: RAM 13.6%, Flash 67.9%)
pio run -e olimex_poe_iso -t upload  # flash
pio device monitor                   # serial console
```

## Project Status

**Phase 0 — Planning + firmware scaffold (current).** Decisions locked; firmware compiles clean for the
ESP32-POE-ISO with the full serial control core, Art-Net/sACN parsers, safety/fail-safe, and a minimal
web dashboard. Nothing has run on hardware yet. Next: bench bring-up — MAX3232 wiring, RS232 loopback,
then live `!G` + telemetry against the HDC2450. See `docs/ARCHITECTURE.md` → Roadmap.
