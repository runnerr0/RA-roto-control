#include "NetworkManager.h"
#include "../Config.h"
#include <ETH.h>
#include <WiFi.h>   // for the ARDUINO_EVENT_ETH_* enum + WiFi.onEvent

namespace {
  volatile bool linkUp_ = false;
  volatile bool gotIp_  = false;
  char ip_[16] = "0.0.0.0";

  void onEvent(WiFiEvent_t event) {
    switch (event) {
      case ARDUINO_EVENT_ETH_START:
        ETH.setHostname(RA_HOSTNAME_DEFAULT);
        break;
      case ARDUINO_EVENT_ETH_CONNECTED:
        linkUp_ = true;
        break;
      case ARDUINO_EVENT_ETH_GOT_IP:
        gotIp_ = true;
        strncpy(ip_, ETH.localIP().toString().c_str(), sizeof(ip_) - 1);
        ip_[sizeof(ip_) - 1] = '\0';
        break;
      case ARDUINO_EVENT_ETH_DISCONNECTED:
      case ARDUINO_EVENT_ETH_STOP:
        linkUp_ = false;
        gotIp_  = false;
        strncpy(ip_, "0.0.0.0", sizeof(ip_));
        break;
      default: break;
    }
  }
}

void NetworkManager::begin(const Settings& s, const char* hostname) {
  WiFi.onEvent(onEvent);
  ETH.begin(eth::PHY_ADDR, eth::PHY_POWER, eth::PHY_MDC, eth::PHY_MDIO,
            ETH_PHY_LAN8720, ETH_CLOCK_GPIO17_OUT);
  if (hostname && *hostname) ETH.setHostname(hostname);
  if (s.useStaticIp && s.staticIp) {
    ETH.config(IPAddress(s.staticIp), IPAddress(s.staticGw),
               IPAddress(s.staticMask));
  }
}

bool NetworkManager::linkUp() { return linkUp_ && gotIp_; }
const char* NetworkManager::ipString() { return ip_; }
