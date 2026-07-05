// SenseAdc.h — reads the commanded voltage back via the /2 divider on GPIO36.
// Lets the UI show the *measured* command voltage, not just the intended value.
#pragma once
#include <stdint.h>

class SenseAdc {
 public:
  void  begin(uint8_t pin);
  float readVoltage();          // returns op-amp output volts (divider compensated)
 private:
  uint8_t pin_ = 36;
  float   ema_ = 0.0f;          // light smoothing
  bool    primed_ = false;
};
