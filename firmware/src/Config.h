// Config.h — pin map, constants, and defaults. Encodes the locked hardware decisions.
// Control path: RS232 to the Roboteq HDC2450 (via MAX3232). See docs/HARDWARE.md and CLAUDE.md.
// VERIFY GPIO assignments against your exact Olimex board revision schematic before soldering.
#pragma once
#include <stdint.h>

// ---- Firmware identity -----------------------------------------------------
#define RA_FW_VERSION "0.2.0-serial"
#define RA_HOSTNAME_DEFAULT "ra-roto"

// ---- ESP32-POE-ISO pin map -------------------------------------------------
// Ethernet RMII reserves GPIO 0,12,17,18,19,21,22,23,25,26,27 — NEVER reuse.
// (ESP32-PoE-ISO clocks the PHY on GPIO17; GPIO12 is PHY power.)
namespace pins {
  constexpr uint8_t HDC_TX      = 14;   // -> MAX3232 T1IN  -> DB25 pin 3 (controller RxData)
  constexpr uint8_t HDC_RX      = 13;   // <- MAX3232 R1OUT <- DB25 pin 2 (controller TxData)
  constexpr uint8_t DMX_RX      = 35;   // <- MAX485 RO (optional physical DMX512; input-only)
  constexpr uint8_t PWRCTRL_EN  = 32;   // -> S8050 -> KF0602D SSR (optional remote enable)
  constexpr uint8_t ESTOP_IN    = 39;   // <- E-stop / deadman (optional, input-only, ext pull-up)
  constexpr uint8_t STATUS_LED  = 33;   // -> status LED
}

// ---- Ethernet PHY (Olimex ESP32-POE-ISO) -----------------------------------
namespace eth {
  constexpr int PHY_ADDR  = 0;
  constexpr int PHY_POWER = 12;
  constexpr int PHY_MDC   = 23;
  constexpr int PHY_MDIO  = 18;
  // type = LAN8720, clock = GPIO17 output (set in NetworkManager).
}

// ---- Roboteq HDC2450 serial (RS232 via MAX3232) ----------------------------
namespace hdc {
  constexpr uint32_t BAUD             = 115200; // controller default; set to match Roborun+
  constexpr uint8_t  CHANNEL          = 1;      // we drive Motor 1
  constexpr int      CMD_MAX          = 1000;   // !G command range is -1000..+1000
  constexpr uint32_t WATCHDOG_MS      = 500;    // ^RWD: controller stops if silent this long
  constexpr uint32_t CMD_INTERVAL_MS  = 50;     // send !G at 20 Hz (also feeds the watchdog)
  constexpr uint32_t POLL_INTERVAL_MS = 250;    // telemetry query cadence
  constexpr uint32_t RX_TIMEOUT_MS    = 60;     // per-query response wait
  constexpr uint32_t ONLINE_TIMEOUT_MS= 1500;   // "controller online" if a reply seen within this
}

// ---- Command constants -----------------------------------------------------
namespace cmd {
  constexpr float STOP = 0.0f;   // normalized command for stop (also the fail-safe)
  constexpr float FWD  = 1.0f;   // full forward
  constexpr float REV  = -1.0f;  // full reverse
}

// ---- Networking ports ------------------------------------------------------
namespace net {
  constexpr uint16_t ARTNET_PORT = 6454;
  constexpr uint16_t SACN_PORT   = 5568;
  constexpr uint16_t HTTP_PORT   = 80;
}

// ---- Timing ----------------------------------------------------------------
namespace timing {
  constexpr uint32_t CONTROL_TICK_US   = 5000;   // 200 Hz control loop (slew accuracy)
  constexpr uint32_t SOURCE_TIMEOUT_MS = 2000;   // a source is "stale" after this
  constexpr uint32_t TELEMETRY_MS      = 200;    // web/WS push cadence
  constexpr uint32_t WDT_TIMEOUT_S     = 4;      // ESP task watchdog
}
