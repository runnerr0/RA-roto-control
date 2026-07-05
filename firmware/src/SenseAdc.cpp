#include "SenseAdc.h"
#include "Config.h"
#include <Arduino.h>

void SenseAdc::begin(uint8_t pin) {
  pin_ = pin;
  analogReadResolution(12);
  // GPIO36 is on ADC1; 11 dB attenuation covers the ~0..2.5V divider output.
  analogSetPinAttenuation(pin_, ADC_11db);
}

float SenseAdc::readVoltage() {
  // analogReadMilliVolts applies the factory eFuse ADC calibration.
  const float mv = float(analogReadMilliVolts(pin_));
  const float v  = (mv / 1000.0f) * cmd::SENSE_DIV;   // undo the /2 divider
  if (!primed_) { ema_ = v; primed_ = true; }
  else          { ema_ += 0.2f * (v - ema_); }        // light smoothing
  return ema_;
}
