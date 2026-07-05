#include "DacDriver.h"
#include "Config.h"
#include <Arduino.h>
#include <Wire.h>

bool DacDriver::begin(uint8_t sda, uint8_t scl, uint8_t addr, uint32_t hz) {
  addr_ = addr;
  Wire.begin(sda, scl, hz);
  // Probe for ACK.
  Wire.beginTransmission(addr_);
  healthy_ = (Wire.endTransmission() == 0);
  return healthy_;
}

void DacDriver::setCalibration(uint16_t code0V, uint16_t code5V) {
  // Guard against a degenerate calibration that would divide by zero.
  if (code5V != code0V) {
    code0V_ = code0V;
    code5V_ = code5V;
  }
}

uint16_t DacDriver::voltsToCode(float v) const {
  if (v < cmd::VOLT_MIN) v = cmd::VOLT_MIN;
  if (v > cmd::VOLT_MAX) v = cmd::VOLT_MAX;
  const float frac = v / cmd::VOLT_MAX;                       // 0..1
  float code = code0V_ + frac * (float(code5V_) - float(code0V_));
  if (code < 0) code = 0;
  if (code > dac::CODE_MAX) code = dac::CODE_MAX;
  return uint16_t(code + 0.5f);
}

bool DacDriver::writeCode(uint16_t code) {
  if (code > dac::CODE_MAX) code = dac::CODE_MAX;
  // MCP4725 fast-mode write: [0 0 PD1 PD0 D11..D8][D7..D0], PD=00 (normal).
  Wire.beginTransmission(addr_);
  Wire.write(uint8_t((code >> 8) & 0x0F));
  Wire.write(uint8_t(code & 0xFF));
  healthy_ = (Wire.endTransmission() == 0);
  return healthy_;
}

bool DacDriver::writeVoltage(float volts) {
  lastVoltage_ = volts;
  return writeCode(voltsToCode(volts));
}
