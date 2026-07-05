// ControlTypes.h — shared enums, persisted Settings, and live ControlState.
#pragma once
#include <stdint.h>

// DMX personas (see docs/PERSONAS.md). Each encodes direction model, resolution, and window.
enum class Persona : uint8_t {
  FullUni      = 1,  // P1: 1ch 8-bit, 2.5->5.0V forward
  FullUni16    = 2,  // P2: 2ch 16-bit, 2.5->5.0V forward
  SlowHalfUni  = 3,  // P3: 1ch 8-bit, 2.5->3.75V
  SlowQuartUni = 4,  // P4: 1ch 8-bit, 2.5->3.125V
  FullBi       = 5,  // P5: 1ch 8-bit, 0<-2.5->5V
  SlowBi       = 6,  // P6: 1ch 8-bit, +/-25% around 2.5V
  FullBi16     = 7,  // P7: 2ch 16-bit bidirectional
};

enum class CommandSource : uint8_t {
  None = 0, FailSafe, Override, Dmx512, Sacn, Artnet
};

const char* toString(Persona p);
const char* toString(CommandSource s);

// Persisted configuration (stored as a versioned blob in NVS via ConfigStore).
struct Settings {
  uint8_t  version       = 1;

  // Control
  Persona  persona       = Persona::FullUni;
  uint16_t dmxStart      = 1;      // 1..512 (footprint 1 or 2 ch by persona)
  float    multiplier    = 1.0f;   // 0..1 live output scale within persona window
  uint8_t  deadband      = 4;      // DMX counts around center (bidirectional)
  float    slewLimitVps  = 2.0f;   // V/s max rate-of-change; 0 = disabled
  bool     invert        = false;
  float    failSafeV     = cmdStopDefault(); // voltage on link-loss/boot/fault

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
  uint8_t  sacnPriority  = 100;    // informational; lowest priority accepted

  // Calibration (from Phase 1 bench validation)
  uint16_t dacCode0V     = 0;      // MCP4725 code producing 0.000V at AnaCmd1
  uint16_t dacCode5V     = 4030;   // MCP4725 code producing 5.000V at AnaCmd1

  static constexpr float cmdStopDefault() { return 2.5f; }
};

// Live state snapshot for telemetry / web UI.
struct ControlState {
  CommandSource activeSource = CommandSource::FailSafe;
  float    normalizedD  = 0.0f;   // 0..1 input after mux
  float    targetV      = 2.5f;   // persona output, pre-safety
  float    outputV      = 2.5f;   // commanded voltage, post-safety
  float    measuredV    = 0.0f;   // sense ADC reading
  bool     ethLinkUp    = false;
  bool     failSafe     = true;
  bool     overrideOn   = false;
  bool     dacHealthy   = false;
  bool     estopActive  = false;
  uint32_t uptimeS      = 0;
  char     ip[16]       = "0.0.0.0";
};
