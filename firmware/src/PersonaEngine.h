// PersonaEngine.h — static mapping from normalized DMX input to a normalized motor
// command in [-1,1] (0 = stop, +1 = full forward, -1 = full reverse). Handles persona
// range, multiplier, deadband, and invert. Temporal shaping (slew) + fail-safe live in
// SafetyStage. SerialController scales [-1,1] to the HDC2450's !G range (+/-1000).
#pragma once
#include "ControlTypes.h"

namespace PersonaEngine {
  // DMX channel footprint for a persona (1 = 8-bit, 2 = 16-bit coarse+fine).
  uint8_t channelCount(Persona p);
  bool    isBidirectional(Persona p);

  // d = normalized DMX value in [0,1]. Returns command in [-1,1].
  float toCommand(const Settings& s, float d);
}
