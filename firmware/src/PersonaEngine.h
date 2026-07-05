// PersonaEngine.h — static mapping from normalized DMX input to a target voltage.
// Handles persona window, multiplier, deadband, and invert. Temporal shaping
// (slew) and fail-safe live in SafetyStage.
#pragma once
#include "ControlTypes.h"

namespace PersonaEngine {
  // DMX channel footprint for a persona (1 = 8-bit, 2 = 16-bit coarse+fine).
  uint8_t channelCount(Persona p);
  bool    isBidirectional(Persona p);

  // d = normalized DMX value in [0,1]. Returns commanded voltage in [0,5].
  float toVoltage(const Settings& s, float d);
}
