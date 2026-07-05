#include "InputMux.h"
#include "PersonaEngine.h"
#include "Config.h"

float InputMux::normalize(const uint8_t* slots, uint16_t count) const {
  if (!s_ || !slots) return 0.0f;
  const uint16_t start = s_->dmxStart;                 // 1-based
  if (start < 1) return 0.0f;
  const uint16_t idx = start - 1;                      // 0-based
  const uint8_t ch = PersonaEngine::channelCount(s_->persona);

  if (ch == 2) {
    if (idx + 1 >= count) return 0.0f;                 // footprint out of frame
    const uint16_t v = (uint16_t(slots[idx]) << 8) | slots[idx + 1];
    return float(v) / 65535.0f;
  }
  if (idx >= count) return 0.0f;
  return float(slots[idx]) / 255.0f;
}

void InputMux::onDmxFrame(CommandSource src, const uint8_t* slots,
                          uint16_t count, uint32_t nowMs) {
  const float d = normalize(slots, count);
  Src* t = nullptr;
  switch (src) {
    case CommandSource::Artnet: t = &artnet_; break;
    case CommandSource::Sacn:   t = &sacn_;   break;
    case CommandSource::Dmx512: t = &dmx_;    break;
    default: return;
  }
  t->d = d;
  t->ms = nowMs;
  t->everSeen = true;
}

void InputMux::setOverride(bool on, float d) {
  override_.active = on;
  if (d < 0.0f) d = 0.0f;
  if (d > 1.0f) d = 1.0f;
  override_.d = d;
}

InputMux::Selected InputMux::select(uint32_t nowMs) const {
  if (override_.active) {
    return { CommandSource::Override, override_.d, true };
  }
  const uint32_t to = timing::SOURCE_TIMEOUT_MS;
  auto live = [&](const Src& s) { return s.everSeen && (nowMs - s.ms) <= to; };

  if (live(dmx_))    return { CommandSource::Dmx512, dmx_.d,    true };
  if (live(sacn_))   return { CommandSource::Sacn,   sacn_.d,   true };
  if (live(artnet_)) return { CommandSource::Artnet, artnet_.d, true };

  return { CommandSource::FailSafe, 0.0f, false };
}
