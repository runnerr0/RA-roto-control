// ControlTypes.h — shared enums, persisted Settings, live ControlState, Telemetry.
#pragma once
#include <stdint.h>

// DMX personas (see docs/PERSONAS.md). Each encodes direction model, resolution, and range.
enum class Persona : uint8_t {
  FullUni      = 1,  // P1: 1ch 8-bit, 0..+100% forward
  FullUni16    = 2,  // P2: 2ch 16-bit, 0..+100% forward
  SlowHalfUni  = 3,  // P3: 1ch 8-bit, 0..+50%
  SlowQuartUni = 4,  // P4: 1ch 8-bit, 0..+25%
  FullBi       = 5,  // P5: 1ch 8-bit, -100%..stop..+100%
  SlowBi       = 6,  // P6: 1ch 8-bit, +/-25%
  FullBi16     = 7,  // P7: 2ch 16-bit bidirectional
};

enum class CommandSource : uint8_t {
  None = 0, FailSafe, Override, Dmx512, Sacn, Artnet
};

const char* toString(Persona p);
const char* toString(CommandSource s);

// Persisted configuration (stored as a versioned blob in NVS via ConfigStore).
struct Settings {
  uint8_t  version       = 2;      // bump invalidates older/incompatible blobs

  // Control (default = bidirectional: -100% rev / stop / +100% fwd)
  Persona  persona       = Persona::FullBi;
  uint16_t dmxStart      = 1;      // 1..512 (footprint 1 or 2 ch by persona)
  float    multiplier    = 1.0f;   // 0..1 live output scale within persona range
  uint8_t  deadband      = 4;      // DMX counts around center (bidirectional)
  float    slewLimit     = 2.0f;   // command units/sec (full range in 0.5s); 0 = off
  bool     invert        = false;
  // Fail-safe command is always cmd::STOP (0) — the HDC2450 also self-stops via ^RWD.

  // Network
  bool     useStaticIp   = false;
  uint32_t staticIp      = 0;
  uint32_t staticGw      = 0;
  uint32_t staticMask    = 0;
  bool     artnetEnabled = true;
  bool     sacnEnabled   = true;
  bool     dmx512Enabled = false;
  uint16_t artnetUniverse= 0;      // 15-bit port-address (Net<<8 | SubUni)
  uint16_t sacnUniverse  = 1;      // 1..63999
  uint8_t  sacnPriority  = 100;
};

// Telemetry queried back from the HDC2450 over serial.
struct Telemetry {
  bool     valid      = false;
  float    motorAmps  = 0.0f;   // ?A  (channel 1)
  float    batteryV   = 0.0f;   // ?V  (main battery)
  int      tempC      = 0;      // ?T
  uint32_t faultFlags = 0;      // ?FF (bitfield: overheat, overvolt, short, estop, ...)
};

// Live state snapshot for telemetry / web UI.
struct ControlState {
  CommandSource activeSource = CommandSource::FailSafe;
  float    normalizedD    = 0.0f;   // 0..1 input after mux
  float    targetCmd      = 0.0f;   // -1..1 persona output, pre-safety
  float    outputCmd      = 0.0f;   // -1..1 commanded, post-safety (0 = stop)
  Telemetry tele;
  bool     ethLinkUp      = false;
  bool     failSafe       = true;
  bool     overrideOn     = false;
  bool     controllerOnline = false; // HDC2450 answering on serial
  bool     estopActive    = false;
  uint32_t uptimeS        = 0;
  char     ip[16]         = "0.0.0.0";
};
