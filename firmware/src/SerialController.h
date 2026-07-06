// SerialController.h — commands the Roboteq HDC2450 over RS232 (via MAX3232).
//   * setCommand(): normalized [-1,1] -> "!G <ch> <-1000..1000>" (also feeds the watchdog)
//   * poll():       round-robins telemetry queries (?A ?V ?T ?FF) and parses replies
//   * configure():  sets the command-loss watchdog (^RWD) so the controller self-stops
// The controller-side ^RWD watchdog is the primary motor fail-safe; our SafetyStage
// (command -> 0) is the secondary.
#pragma once
#include "ControlTypes.h"
#include <Arduino.h>

class SerialController {
 public:
  void begin(HardwareSerial* port, uint8_t rx, uint8_t tx, uint32_t baud);
  void configure();                 // ^ECHOF, ^RWD — call once after begin()
  void setCommand(float cmd);       // -1..1 ; 0 = stop
  void poll(Telemetry& out);        // issue one query, parse into out
  bool online() const;              // a valid reply seen within hdc::ONLINE_TIMEOUT_MS

 private:
  bool sendLine(const char* line);
  bool query(const char* q, char* resp, size_t n);   // send q, read one reply line
  static long firstInt(const char* s);               // parse "X=123:456" -> 123

  HardwareSerial* port_    = nullptr;
  long            lastG_   = 0x7fffffff;   // force first send
  uint8_t         pollIdx_ = 0;
  uint32_t        lastRxMs_= 0;
};
