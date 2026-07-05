#include "PersonaEngine.h"
#include "Config.h"
#include <math.h>

namespace {
  // Forward (unidirectional) window span above 2.5V for each persona.
  float uniSpan(Persona p) {
    switch (p) {
      case Persona::FullUni:
      case Persona::FullUni16:    return 2.5f;
      case Persona::SlowHalfUni:  return 1.25f;
      case Persona::SlowQuartUni: return 0.625f;
      default:                    return 2.5f;
    }
  }
  // Bidirectional half-span each side of 2.5V.
  float biHalfSpan(Persona p) {
    switch (p) {
      case Persona::SlowBi: return 0.625f;
      default:              return 2.5f;   // FullBi, FullBi16
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

float PersonaEngine::toVoltage(const Settings& s, float d) {
  d = clampf(d, 0.0f, 1.0f);
  const float m = clampf(s.multiplier, 0.0f, 1.0f);

  if (isBidirectional(s.persona)) {
    // Center at DMX mid; apply a continuous deadband, then scale to [-1,1].
    const float dev  = d - 0.5f;                       // -0.5..0.5
    const float dz   = float(s.deadband) / 255.0f;     // deadband as fraction
    float c;
    if (fabsf(dev) <= dz || dz >= 0.5f) {
      c = 0.0f;
    } else {
      const float sign = dev < 0 ? -1.0f : 1.0f;
      c = sign * (fabsf(dev) - dz) / (0.5f - dz);      // -1..1
    }
    if (s.invert) c = -c;
    const float v = cmd::VOLT_STOP + c * m * biHalfSpan(s.persona);
    return clampf(v, cmd::VOLT_MIN, cmd::VOLT_MAX);
  }

  // Unidirectional: window sits above the 2.5V stop point.
  float du = s.invert ? (1.0f - d) : d;
  const float v = cmd::VOLT_STOP + du * m * uniSpan(s.persona);
  return clampf(v, cmd::VOLT_STOP, cmd::VOLT_MAX);
}
