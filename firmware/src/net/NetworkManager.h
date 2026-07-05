// NetworkManager.h — Olimex ESP32-POE-ISO Ethernet (LAN8720, clk GPIO17) bring-up.
// NOTE: uses the Arduino-ESP32 2.0.x ETH.begin() signature (see platformio.ini).
#pragma once
#include "../ControlTypes.h"
#include <Arduino.h>

namespace NetworkManager {
  void begin(const Settings& s, const char* hostname);
  bool linkUp();
  const char* ipString();   // "0.0.0.0" until DHCP/static assigned
}
