// InputMux.h — arbitrates the active command source and normalizes it to [0,1].
// Priority: Override > DMX512 > sACN > Art-Net. A source is "live" only while
// fresh (timing::SOURCE_TIMEOUT_MS); otherwise it drops out and SafetyStage
// substitutes the fail-safe voltage.
#pragma once
#include "ControlTypes.h"

class InputMux {
 public:
  void begin(const Settings* s) { s_ = s; }

  // Protocol inputs push frames here. slots[0] == DMX channel 1.
  void onDmxFrame(CommandSource src, const uint8_t* slots, uint16_t count, uint32_t nowMs);

  // Manual override from the web UI. d in [0,1].
  void setOverride(bool on, float d);
  bool overrideActive() const { return override_.active; }

  struct Selected { CommandSource src; float d; bool live; };
  Selected select(uint32_t nowMs) const;

 private:
  float normalize(const uint8_t* slots, uint16_t count) const;

  const Settings* s_ = nullptr;
  struct Src { float d = 0.0f; uint32_t ms = 0; bool everSeen = false; };
  Src artnet_, sacn_, dmx_;
  struct Ovr { bool active = false; float d = 0.0f; } override_;
};
