#include "SerialController.h"
#include "Config.h"
#include <Arduino.h>
#include <string.h>
#include <stdlib.h>

void SerialController::begin(HardwareSerial* port, uint8_t rx, uint8_t tx, uint32_t baud) {
  port_ = port;
  port_->begin(baud, SERIAL_8N1, rx, tx);
}

void SerialController::configure() {
  if (!port_) return;
  sendLine("^ECHOF 1");                 // disable command echo -> simpler reply parsing
  char rwd[24];
  snprintf(rwd, sizeof(rwd), "^RWD %lu", (unsigned long)hdc::WATCHDOG_MS);
  sendLine(rwd);                        // controller self-stops if silent this long
}

bool SerialController::sendLine(const char* line) {
  if (!port_) return false;
  port_->print(line);
  port_->print('\r');                   // Roboteq commands terminate with CR
  return true;
}

void SerialController::setCommand(float cmd) {
  if (cmd < -1.0f) cmd = -1.0f;
  if (cmd >  1.0f) cmd =  1.0f;
  long g = lroundf(cmd * float(hdc::CMD_MAX));
  if (g >  hdc::CMD_MAX) g =  hdc::CMD_MAX;
  if (g < -hdc::CMD_MAX) g = -hdc::CMD_MAX;
  lastG_ = g;
  char line[24];
  snprintf(line, sizeof(line), "!G %u %ld", hdc::CHANNEL, g);
  sendLine(line);                       // sent every call -> also feeds the ^RWD watchdog
}

bool SerialController::query(const char* q, char* resp, size_t n) {
  if (!port_) return false;
  while (port_->available()) port_->read();   // flush stale bytes
  sendLine(q);
  const uint32_t deadline = millis() + hdc::RX_TIMEOUT_MS;
  size_t i = 0;
  while (millis() < deadline && i < n - 1) {
    if (port_->available()) {
      char c = char(port_->read());
      if (c == '\r' || c == '\n') { if (i > 0) break; else continue; }
      resp[i++] = c;
    }
  }
  resp[i] = '\0';
  return i > 0;
}

long SerialController::firstInt(const char* s) {
  const char* p = strchr(s, '=');
  p = p ? p + 1 : s;
  return strtol(p, nullptr, 10);
}

void SerialController::poll(Telemetry& out) {
  char resp[48];
  bool ok = false;
  // NOTE: value scaling below is the common Roboteq convention; verify against your
  // controller with Roborun+ and adjust (amps *10, volts *10 are typical). TODO Phase 4.
  switch (pollIdx_) {
    case 0: if ((ok = query("?A 1", resp, sizeof(resp)))) out.motorAmps  = firstInt(resp) / 10.0f; break;
    case 1: if ((ok = query("?V 2", resp, sizeof(resp)))) out.batteryV   = firstInt(resp) / 10.0f; break;
    case 2: if ((ok = query("?T",   resp, sizeof(resp)))) out.tempC      = int(firstInt(resp));     break;
    case 3: if ((ok = query("?FF",  resp, sizeof(resp)))) out.faultFlags = uint32_t(firstInt(resp));break;
  }
  pollIdx_ = (pollIdx_ + 1) & 0x03;
  if (ok) { lastRxMs_ = millis(); out.valid = true; }
}

bool SerialController::online() const {
  return lastRxMs_ != 0 && (millis() - lastRxMs_) < hdc::ONLINE_TIMEOUT_MS;
}
