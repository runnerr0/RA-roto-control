#include "SafetyStage.h"
#include "Config.h"

void SafetyStage::begin(float startCmd, float slew) {
  current_      = startCmd;
  slew_         = slew;
  forced_       = false;
  lastFailSafe_ = true;
}

float SafetyStage::update(float desiredCmd, float dtSec, bool sourceLive) {
  const bool failSafe = forced_ || !sourceLive;
  lastFailSafe_ = failSafe;

  float target = failSafe ? cmd::STOP : desiredCmd;
  if (target < cmd::REV) target = cmd::REV;
  if (target > cmd::FWD) target = cmd::FWD;

  if (slew_ <= 0.0f || dtSec <= 0.0f) {
    current_ = target;                       // slew disabled -> jump
  } else {
    const float step = slew_ * dtSec;        // max change this tick
    const float delta = target - current_;
    if (delta >  step) current_ += step;
    else if (delta < -step) current_ -= step;
    else current_ = target;
  }
  return current_;
}
