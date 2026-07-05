# Firmware & System Architecture

ESP32-POE-ISO firmware bridging show-control protocols → 0–5V analog → HDC2450. Built on
PlatformIO + Arduino-ESP32, following raDMX patterns.

---

## Module map

```
        ┌──────────────────────── Network (Ethernet, isolated PoE) ─────────────────────┐
        │                                                                                │
   Art-Net rx ──┐                                                                        │
   sACN/E1.31 ──┼─► InputMux ──► PersonaEngine ──► SafetyStage ──► DacDriver ──► MCP4725 ─┼─► op-amp ─► HDC2450
   DMX512 rx  ──┘        ▲            ▲                 ▲              │                   │
                         │            │                 │            SenseADC ◄───────────┤ (GPIO36)
                    OverrideCtl   PersonaCfg        Watchdog          │                   │
                         ▲            ▲             SlewLimit    Telemetry ────────────────┤
                         │            │             FailSafe          │                   │
                    WebServer (ESPAsyncWebServer) ◄──── WebSocket ────┘                   │
                         │                                                                │
                    Config store (Preferences/LittleFS) · OTA                            │
        └────────────────────────────────────────────────────────────────────────────────┘
```

### Modules
- **InputMux** — arbitrates the active command source (priority: **Override > DMX512 > sACN > Art-Net**,
  configurable). Tracks per-source liveness; drops to fail-safe if the selected source goes stale.
- **PersonaEngine** — applies the active persona math (`docs/PERSONAS.md`) → target voltage.
- **SafetyStage** — deadband, slew-rate limit, clamp `[0,5]`, invert, fail-safe substitution.
- **DacDriver** — voltage → calibrated DAC code (`DAC_STOP_CODE`, `DAC_MAX_CODE`) → MCP4725 over I2C.
- **SenseADC** — reads op-amp output via ÷2 divider (GPIO36) → *measured* command voltage for the UI.
- **Watchdog** — hardware task watchdog; on reset, DacDriver boots to fail-safe voltage.
- **WebServer / WebSocket** — config + live dashboard + override (below).
- **Telemetry** — pushes state (source, DMX value, target V, measured V, faults) over WebSocket.
  Phase 2: HDC2450 amps/volts/temp/faults via RS232.
- **Config store** — persisted settings (persona, network, calibration) in NVS/LittleFS. OTA updates.

---

## Protocols

| Protocol | Transport | Library (candidate) | Notes |
|----------|-----------|---------------------|-------|
| **DMX512** | RS485 (MAX485) on UART | `esp_dmx` | Physical XLR input, GPIO35 RX, receive-only. Optional. |
| **Art-Net** | UDP 6454 | `ArtnetWiFi`/custom | Universe/subnet configurable in UI. |
| **sACN / E1.31** | UDP 5568 (multicast) | `ESPAsyncE131` | Universe + priority; multicast join on the Ethernet iface. |

All three feed **InputMux**. Only the DMX slot(s) at `dmxStart` (1 or 2 channels per persona) are consumed.

---

## Web interface

Single-page dashboard served from LittleFS (raDMX-style), WebSocket for live data.

**Tabs / sections:**
1. **Live** — big readout: active source, raw DMX value, target voltage, **measured** voltage (sense ADC),
   direction, motor state; source-liveness indicators.
2. **Persona** — pick P1–P7, DMX start address, multiplier slider, deadband, slew limit, invert.
3. **Network** — hostname, DHCP/static IP, Art-Net universe/subnet, sACN universe/priority, DMX enable.
4. **Override** — master takeover toggle + direct speed/direction slider + timeout. Prominent banner when active.
5. **Diagnostics** — I2C/DAC health, calibration values, sense-vs-target delta, Ethernet link, uptime,
   fault log; (Phase 2) HDC2450 telemetry (battery V, amps, temp, controller fault flags).
6. **System** — calibration wizard (0/2.5/5V trim), OTA firmware upload, config export/import, reboot.

---

## Safety model

The HDC2450's serial command-loss watchdog does **not** protect analog mode — it holds the last voltage.
So safety lives in *our* firmware:

- **Fail-safe voltage** on boot, Ethernet link-loss, source-stale, or watchdog reset (default 2.5V = stop).
- **Source-liveness timeout** per input (e.g. 2s) → fail-safe.
- **Slew-rate limiting** so no command can snap the motor.
- **Task watchdog** → reset → boot fail-safe.
- **Optional hardware E-stop** input (GPIO39) → immediate fail-safe voltage + optional PwrCtrl relay off.
- **Optional PwrCtrl relay** (GPIO32) → remote power-down of the HDC2450 from the UI/E-stop.

---

## Roadmap

- **Phase 0 — Planning & validation (current).** Docs done; validate analog chain on paper.
- **Phase 1 — Bench analog chain.** Wire MCP4725 + op-amp on breadboard; run HARDWARE.md validation
  steps 1–5; record calibration. **No motor power.**
- **Phase 2 — Core firmware.** PlatformIO scaffold, Ethernet up, MCP4725 driver + calibration, PersonaEngine,
  SafetyStage, fail-safe. Meter-verify personas produce correct voltages.
- **Phase 3 — Protocols + web UI.** Art-Net + sACN + optional DMX512; dashboard; override; OTA.
- **Phase 4 — Motor-in-the-loop.** Connect motor power, verify direction/speed/slew on the real roto.
- **Phase 5 — Field hardening.** Enclosure, connectorization (DB25 hood), Phase-2 RS232 telemetry,
  E-stop + PwrCtrl relay, deployment test.

---

## Open items to confirm before Phase 2
- Verify GPIO13/16 (I2C) free on the exact Olimex ESP32-POE-ISO revision in hand.
- Decide unidirectional vs bidirectional roto (drives Roborun+ config + default persona).
- Confirm whether physical DMX512 input is needed for v1 or Art-Net/sACN only.
- Confirm PoE switch/injector availability (802.3af).
