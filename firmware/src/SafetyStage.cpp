#include "SafetyStage.h"
#include "Config.h"

void SafetyStage::begin(float startV, float failSafeV, float slewVps) {
  current_    = startV;
  failSafeV_  = failSafeV;
  slewVps_    = slewVps;
  forced_     = false;
  lastFailSafe_ = true;
}

float SafetyStage::update(float desiredV, float dtSec, bool sourceLive) {
  const bool failSafe = forced_ || !sourceLive;
  lastFailSafe_ = failSafe;

  float target = failSafe ? failSafeV_ : desiredV;
  if (target < cmd::VOLT_MIN) target = cmd::VOLT_MIN;
  if (target > cmd::VOLT_MAX) target = cmd::VOLT_MAX;

  if (slewVps_ <= 0.0f || dtSec <= 0.0f) {
    current_ = target;                       // slew disabled -> jump
  } else {
    const float step = slewVps_ * dtSec;     // max change this tick
    const float delta = target - current_;
    if (delta >  step) current_ += step;
    else if (delta < -step) current_ -= step;
    else current_ = target;
  }
  return current_;
}
