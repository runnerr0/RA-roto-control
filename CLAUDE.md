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

Host control console (Python, no ESP32 needed — `pip install pyserial`):

```bash
python3 tools/roto-bench/roto_bench.py               # web console at http://127.0.0.1:8791
python3 tools/roto-bench/roto_bench.py --sim         # preview the whole UI with no hardware
python3 tools/roto-bench/roto_bench.py --lan         # bind 0.0.0.0 for the /remote phone view
python3 tools/roto-bench/roto_bench.py --encoder PORT --gear 1.0   # optional AS5600 closed-loop RPM
```

## Project Status

**Serial control + safety proven on hardware — via the host console; ESP32 firmware still scaffold.**
Decisions locked. The Python **control console** (`tools/roto-bench/`) has matured into a full-featured
run-time control surface and drives Motor 1 over `!G` on the real HDC2450 with a **current governor**
(feathers command under the limit instead of tripping), a **soft-stop** (halts every mode incl. DRIFT),
an **enforced + displayed speed cap**, layered auto-trip (overcurrent/stall, temperature, I²t),
control-drift detection, percentage UI, HOLD/CREEP effort control, pop-out dashboards (`/graphs`,
`/stats`), a phone view (`/remote` + `--lan`), config backup/restore, spacebar E-STOP, and a `--sim`
no-hardware preview. **Optional AS5600 encoder** (`tools/as5600-reader/`) adds closed-loop fixture RPM
(shaft RPM ÷ gear ratio) and a **TRUE STALL** trip. Telemetry, `ALIM`/`ATGA` config, and the `^RWD`
watchdog are validated. The **ESP32-POE-ISO firmware** (the product — adds Ethernet/PoE + DMX/Art-Net/sACN)
compiles clean but has not run on hardware; next is porting the proven console logic into
`SerialController`/`SafetyStage`. See `docs/ARCHITECTURE.md` → Roadmap.
