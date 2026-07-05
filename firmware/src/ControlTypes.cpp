#include "ControlTypes.h"

const char* toString(Persona p) {
  switch (p) {
    case Persona::FullUni:      return "Full / Uni";
    case Persona::FullUni16:    return "Full / Uni 16-bit";
    case Persona::SlowHalfUni:  return "Slow 1/2 / Uni";
    case Persona::SlowQuartUni: return "Slow 1/4 / Uni";
    case Persona::FullBi:       return "Full / Bidirectional";
    case Persona::SlowBi:       return "Slow / Bidirectional";
    case Persona::FullBi16:     return "Full / Bi 16-bit";
  }
  return "Unknown";
}

const char* toString(CommandSource s) {
  switch (s) {
    case CommandSource::None:     return "none";
    case CommandSource::FailSafe: return "fail-safe";
    case CommandSource::Override: return "override";
    case CommandSource::Dmx512:   return "DMX512";
    case CommandSource::Sacn:     return "sACN";
    case CommandSource::Artnet:   return "Art-Net";
  }
  return "unknown";
}
