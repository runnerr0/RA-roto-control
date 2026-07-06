// SafetyStage.h — temporal safety shaping between persona output and the controller.
//   * substitutes STOP (0) when no live source / fault / e-stop
//   * slew-rate limits every change (incl. the move to stop)
//   * clamps to [-1,1]
// Works in normalized command units (0 = stop). This is the SECONDARY fail-safe;
// the HDC2450's own ^RWD serial watchdog is the primary.
#pragma once

class SafetyStage {
 public:
  void  begin(float startCmd, float slew);
  void  setSlew(float s)       { slew_ = s; }
  void  forceFailSafe(bool on) { forced_ = on; }   // e-stop / manual latch

  // desiredCmd: persona output [-1,1]. sourceLive: is a command source fresh?
  // Returns the command to send this tick.
  float update(float desiredCmd, float dtSec, bool sourceLive);

  float current()    const { return current_; }
  bool  inFailSafe() const { return lastFailSafe_; }

 private:
  float current_      = 0.0f;
  float slew_         = 2.0f;    // command units/sec
  bool  forced_       = false;
  bool  lastFailSafe_ = true;
};
