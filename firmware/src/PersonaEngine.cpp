#include "PersonaEngine.h"
#include <math.h>

namespace {
  // Forward (unidirectional) command fraction for each persona (0..1).
  float uniSpan(Persona p) {
    switch (p) {
      case Persona::FullUni:
      case Persona::FullUni16:    return 1.0f;
      case Persona::SlowHalfUni:  return 0.5f;
      case Persona::SlowQuartUni: return 0.25f;
      default:                    return 1.0f;
    }
  }
  // Bidirectional command fraction each side of stop (0..1).
  float biSpan(Persona p) {
    switch (p) {
      case Persona::SlowBi: return 0.25f;
      default:              return 1.0f;   // FullBi, FullBi16
    }
  }
  float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
  }
}

uint8_t PersonaEngine::channelCount(Persona p) {
  return (p == Persona::FullUni16 || p == Persona::FullBi16) ? 2 : 1;
}

bool PersonaEngine::isBidirectional(Persona p) {
  return p == Persona::FullBi || p == Persona::SlowBi || p == Persona::FullBi16;
}

float PersonaEngine::toCommand(const Settings& s, float d) {
  d = clampf(d, 0.0f, 1.0f);
  const float m = clampf(s.multiplier, 0.0f, 1.0f);

  if (isBidirectional(s.persona)) {
    // Center at DMX mid; continuous deadband, then scale to [-1,1].
    const float dev = d - 0.5f;                        // -0.5..0.5
    const float dz  = float(s.deadband) / 255.0f;      // deadband as fraction
    float c;
    if (fabsf(dev) <= dz || dz >= 0.5f) {
      c = 0.0f;
    } else {
      const float sign = dev < 0 ? -1.0f : 1.0f;
      c = sign * (fabsf(dev) - dz) / (0.5f - dz);      // -1..1
    }
    if (s.invert) c = -c;
    return clampf(c * m * biSpan(s.persona), -1.0f, 1.0f);
  }

  // Unidirectional: forward only (0..+1).
  const float du = s.invert ? (1.0f - d) : d;
  return clampf(du * m * uniSpan(s.persona), 0.0f, 1.0f);
}
