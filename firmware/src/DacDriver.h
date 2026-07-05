// DacDriver.h — MCP4725 12-bit I2C DAC. Calibrated voltage->code mapping for AnaCmd1.
// Uses fast-mode writes only (never touches EEPROM -> no wear).
#pragma once
#include <stdint.h>

class DacDriver {
 public:
  bool  begin(uint8_t sda, uint8_t scl, uint8_t addr, uint32_t hz);
  // code0V/code5V come from Phase 1 bench calibration (linear between them).
  void  setCalibration(uint16_t code0V, uint16_t code5V);

  bool  writeVoltage(float volts);   // clamps to [0,5], maps via calibration
  bool  writeCode(uint16_t code);    // raw 0..4095 (for calibration sweeps)

  float lastVoltage() const { return lastVoltage_; }
  bool  healthy()     const { return healthy_; }

 private:
  uint16_t voltsToCode(float v) const;

  uint8_t  addr_     = 0x62;
  uint16_t code0V_   = 0;
  uint16_t code5V_   = 4030;
  float    lastVoltage_ = 0.0f;
  bool     healthy_  = false;
};
