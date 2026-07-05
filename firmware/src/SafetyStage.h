// SafetyStage.h — temporal safety shaping between persona output and the DAC.
//   * substitutes the fail-safe voltage when no live source / fault / e-stop
//   * slew-rate limits every change (incl. the move to fail-safe)
//   * clamps to [0,5]
// The HDC2450 holds its last analog voltage if we hang, so this stage is the
// only thing guaranteeing a safe stop. Treat it as safety-critical.
#pragma once

class SafetyStage {
 public:
  void  begin(float startV, float failSafeV, float slewVps);
  void  setFailSafe(float v)   { failSafeV_ = v; }
  void  setSlew(float vps)     { slewVps_ = vps; }
  void  forceFailSafe(bool on) { forced_ = on; }   // e-stop / manual latch

  // desiredV: persona output. sourceLive: is a command source fresh?
  // Returns the voltage to command this tick.
  float update(float desiredV, float dtSec, bool sourceLive);

  float current()      const { return current_; }
  bool  inFailSafe()   const { return lastFailSafe_; }

 private:
  float current_     = 2.5f;
  float failSafeV_   = 2.5f;
  float slewVps_     = 2.0f;
  bool  forced_      = false;
  bool  lastFailSafe_= true;
};
