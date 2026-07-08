/*
 * as5600_reader.ino — AS5600 magnetic encoder -> USB serial bridge for RA Roto.
 *
 * Reads an AS5600 12-bit absolute magnetic encoder over I2C and streams the
 * shaft angle, cumulative position, and SIGNED RPM (direction-aware) to the
 * control console over USB serial. This is the "is it actually moving?" sensor:
 * the console pairs it with the command to detect a TRUE STALL (commanded but
 * the shaft isn't turning) that open-loop current can't distinguish from a hold.
 *
 * Unlike the tooth-counting tach, the AS5600 gives absolute angle, so RPM is
 * computed from angle change and carries SIGN (forward/reverse). Reading the
 * angle every loop and reporting at ~10 Hz keeps the unwrap correct even at the
 * motor's top speed.
 *
 * Wiring (any Arduino / ESP32 / Pico with I2C):
 *   AS5600 VCC -> 3.3V   (the AS5600 is a 3.3V part; on a 5V board level-shift
 *                         SDA/SCL or use a 3.3V-logic board / an ESP32)
 *   AS5600 GND -> GND
 *   AS5600 SDA -> board SDA   (Uno/Nano A4, ESP32 GPIO21, Pico GP4 — check yours)
 *   AS5600 SCL -> board SCL   (Uno/Nano A5, ESP32 GPIO22, Pico GP5)
 *   Magnet: diametrically-magnetised, on the shaft END face, ~1-2 mm gap,
 *           centred on the AS5600 die.
 *
 * Report line (parsed by roto_bench.py --encoder):
 *   ANG=<0-4095> POS=<cumulative_counts> RPM=<signed float> MAG=<0|1> STALL=<0|1>
 */

#include <Wire.h>

const uint8_t  AS5600_ADDR = 0x36;
const uint8_t  REG_RAWANGLE = 0x0C;   // 0x0C hi, 0x0D lo (12-bit)
const uint8_t  REG_STATUS   = 0x0B;   // bit5 MD = magnet detected
const uint16_t COUNTS       = 4096;   // 12-bit per revolution
const uint16_t REPORT_MS    = 100;    // ~10 Hz reports
const float    STALL_RPM    = 0.5;    // |rpm| below this = not moving

long     cumulative = 0;              // total counts since boot (unwrapped)
int      lastRaw    = -1;
long     lastReportCum = 0;
uint32_t lastReportMs  = 0;

int readRaw() {                        // 12-bit raw angle, or -1 on I2C error
  Wire.beginTransmission(AS5600_ADDR);
  Wire.write(REG_RAWANGLE);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom((int)AS5600_ADDR, 2) != 2) return -1;
  int hi = Wire.read(), lo = Wire.read();
  return ((hi << 8) | lo) & 0x0FFF;
}

bool magnetOK() {
  Wire.beginTransmission(AS5600_ADDR);
  Wire.write(REG_STATUS);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)AS5600_ADDR, 1) != 1) return false;
  return (Wire.read() & 0x20) != 0;    // MD bit
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(400000);               // 400 kHz fast-mode I2C
  lastReportMs = millis();
}

void loop() {
  int raw = readRaw();
  if (raw >= 0) {
    if (lastRaw >= 0) {
      int delta = raw - lastRaw;       // unwrap across the 4095<->0 seam
      if (delta >  COUNTS / 2) delta -= COUNTS;
      if (delta < -COUNTS / 2) delta += COUNTS;
      cumulative += delta;
    }
    lastRaw = raw;
  }

  uint32_t now = millis();
  if (now - lastReportMs >= REPORT_MS) {
    float dt = (now - lastReportMs) / 1000.0f;                 // seconds
    long  dCount = cumulative - lastReportCum;
    float rpm = (dt > 0) ? ((dCount / (float)COUNTS) / dt) * 60.0f : 0.0f;
    bool  stalled = fabs(rpm) < STALL_RPM;

    Serial.print("ANG=");   Serial.print(lastRaw < 0 ? 0 : lastRaw);
    Serial.print(" POS=");  Serial.print(cumulative);
    Serial.print(" RPM=");  Serial.print(rpm, 2);
    Serial.print(" MAG=");  Serial.print(magnetOK() ? 1 : 0);
    Serial.print(" STALL="); Serial.println(stalled ? 1 : 0);

    lastReportMs  = now;
    lastReportCum = cumulative;
  }
}
