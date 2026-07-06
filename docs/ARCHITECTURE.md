# Firmware & System Architecture

ESP32-POE-ISO firmware bridging show-control protocols → **RS232 serial** → HDC2450. Built on
PlatformIO + Arduino-ESP32, following raDMX patterns.

---

## Module map

```
        ┌──────────────────────── Network (Ethernet, isolated PoE) ─────────────────────┐
        │                                                                                │
   Art-Net rx ──┐                                                                        │
   sACN/E1.31 ──┼─► InputMux ──► PersonaEngine ──► SafetyStage ──► SerialController ─UART─┼─► MAX3232 ─► HDC2450
   DMX512 rx  ──┘        ▲          (→ [-1,1])      (slew + STOP)   (!G / ?A?V?T?FF / ^RWD)│      ▲
                         │                                                │                │      │
                    OverrideCtl                                     Telemetry ◄────────────┼──────┘
                         ▲                                                │                │
                    WebServer (ESPAsyncWebServer + WebSocket) ◄───────────┘                │
                         │                                                                 │
                    ConfigStore (NVS) · OTA                                                │
        └───────────────────────────────────────────────────────────────────────────────┘
```

### Modules
- **InputMux** — arbitrates the command source (priority **Override > DMX512 > sACN > Art-Net**),
  tracks per-source liveness, normalizes the active DMX slot(s) to `d ∈ [0,1]`.
- **PersonaEngine** — persona math (`docs/PERSONAS.md`) → command in **[-1,1]** (0 = stop).
- **SafetyStage** — deadband is in PersonaEngine; here: slew-rate limit, clamp, and STOP substitution
  when no live source / e-stop. Secondary fail-safe.
- **SerialController** — `!G 1 <-1000..1000>` (sent continuously at 20 Hz → also feeds the watchdog),
  round-robin telemetry queries, `^RWD`/`^ECHOF` config, online detection.
- **Telemetry** — motor amps / battery V / temp / fault flags parsed from `?A ?V ?T ?FF`.
- **NetworkManager** — Olimex ETH bring-up + link/IP events.
- **ArtnetInput / SacnInput** — ArtDMX + E1.31 parsers over AsyncUDP.
- **ConfigStore** — versioned Settings blob in NVS.
- **WebServer / WebSocket** — config, override, live telemetry dashboard.

---

## Protocols

| Protocol | Transport | Library | Notes |
|----------|-----------|---------|-------|
| **HDC2450 control** | RS232 (MAX3232) on UART1 | native | `!G` commands + `?…` telemetry, 115200 8N1 |
| **DMX512** | RS485 (MAX485) | `esp_dmx` (TODO) | Physical XLR input, GPIO35, optional |
| **Art-Net** | UDP 6454 | AsyncUDP (built-in) | Universe configurable |
| **sACN / E1.31** | UDP 5568 multicast | AsyncUDP (built-in) | Universe + multicast join |

---

## Safety model (layered)

The serial pivot upgraded this materially — the HDC2450's command-loss watchdog only works on serial:

1. **HDC2450 `^RWD` watchdog (primary):** controller self-stops if it doesn't receive a command within
   500 ms — independent of our firmware. This is why serial beats analog for a motor.
2. **Continuous send:** `SerialController` emits `!G` at 20 Hz, so a hung/crashed ESP simply stops
   feeding the watchdog → controller stops.
3. **Firmware STOP (secondary):** `SafetyStage` drives command → 0 on boot, Ethernet link-loss,
   source-stale, or e-stop; slew-rate limits every change.
4. **ESP task watchdog:** hang → reset → boot re-commands STOP before powering the controller.
5. **Optional hardware E-stop** (GPIO39) → STOP + drops the PwrCtrl SSR.
6. **Optional PwrCtrl SSR** (GPIO32) → remote/auto power-down of the controller.

Boot order is safety-ordered: serial up → command STOP → *then* enable PwrCtrl.

---

## Web interface

Single-page dashboard (embedded now; full LittleFS SPA in Phase 3). WebSocket live data.
Sections: **Command** (source, input %, target/output %, fail-safe state), **Controller** (serial
online, motor amps, battery V, temp, fault flags), **System** (Ethernet, uptime), **Override**
(takeover toggle + slider: 0 = rev, 50 = stop, 100 = fwd). Phase 3 adds persona editor, network
config, calibration-free diagnostics, OTA.

---

## Roadmap

- **Phase 0 — Planning + firmware scaffold (current).** Docs + serial control core, compiles clean.
- **Phase 1 — Serial bench bring-up.** MAX3232 wiring, `?FID` link check, `^RWD` + telemetry, no motor.
- **Phase 2 — Motor-in-the-loop.** Live `!G`, verify direction/speed/slew/e-stop on the real roto.
- **Phase 3 — Protocols + web UI.** Art-Net + sACN + optional DMX512; full dashboard; override; OTA.
- **Phase 4 — Telemetry hardening.** Verify Roboteq value scaling, fault-flag decoding, reconnect logic.
- **Phase 5 — Field hardening.** Enclosure, DB25 hood, E-stop + PwrCtrl SSR, deployment test.

---

## Open items to confirm before hardware bring-up
- Verify GPIO13/14 (UART) free on the exact Olimex ESP32-POE-ISO revision.
- Confirm HDC2450 serial baud (Roborun+) matches `hdc::BAUD` (115200).
- Confirm `?A`/`?V` value scaling on your controller and fix `SerialController::poll()` if needed.
- Confirm whether physical DMX512 input is needed for v1 or Art-Net/sACN only.
