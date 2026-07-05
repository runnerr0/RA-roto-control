// Config.h — pin map, constants, and defaults. Encodes the locked hardware decisions.
// See docs/HARDWARE.md and CLAUDE.md. VERIFY GPIO assignments against your exact Olimex
// board revision schematic before soldering.
#pragma once
#include <stdint.h>

// ---- Firmware identity -----------------------------------------------------
#define RA_FW_VERSION "0.1.0-scaffold"
#define RA_HOSTNAME_DEFAULT "ra-roto"

// ---- ESP32-POE-ISO pin map -------------------------------------------------
// Ethernet RMII reserves GPIO 0,12,17,18,19,21,22,23,25,26,27 — NEVER reuse.
// (ESP32-PoE-ISO clocks the PHY on GPIO17; GPIO12 is PHY power.)
namespace pins {
  constexpr uint8_t I2C_SDA      = 13;   // -> MCP4725 SDA (Olimex UEXT; verify on board rev)
  constexpr uint8_t I2C_SCL      = 16;   // -> MCP4725 SCL
  constexpr uint8_t SENSE_ADC    = 36;   // <- op-amp output via /2 divider (ADC1, input-only)
  constexpr uint8_t DMX_RX       = 35;   // <- MAX485 RO (optional physical DMX512; input-only)
  constexpr uint8_t PWRCTRL_EN   = 32;   // -> S8050 -> KF0602D SSR (optional remote enable)
  constexpr uint8_t ESTOP_IN     = 39;   // <- E-stop / deadman (optional, input-only, ext pull-up)
  constexpr uint8_t STATUS_LED   = 33;   // -> status LED
}

// ---- Ethernet PHY (Olimex ESP32-POE-ISO) -----------------------------------
// Consumed by NetworkManager. Correct for the -ISO revision.
namespace eth {
  constexpr int      PHY_ADDR  = 0;
  constexpr int      PHY_POWER = 12;
  constexpr int      PHY_MDC   = 23;
  constexpr int      PHY_MDIO  = 18;
  // PHY type = LAN8720, clock mode = GPIO17 output. Set in NetworkManager (enum types).
}

// ---- MCP4725 ---------------------------------------------------------------
namespace dac {
  constexpr uint8_t  I2C_ADDR   = 0x62;  // A0=GND (0x62). Adafruit breakout default 0x62.
  constexpr uint32_t I2C_HZ     = 400000;
  constexpr uint16_t CODE_MAX   = 4095;  // 12-bit
  // Calibration defaults (overwritten by measured values in ConfigStore after Phase 1).
  // Linear: code0V -> 0.000 V at AnaCmd1, code5V -> 5.000 V. Gain stage nominal x1.515.
  constexpr uint16_t CAL_CODE_0V = 0;
  constexpr uint16_t CAL_CODE_5V = 4030;
}

// ---- Analog / command constants --------------------------------------------
namespace cmd {
  constexpr float VOLT_MIN   = 0.0f;   // full reverse (bidirectional)
  constexpr float VOLT_STOP  = 2.5f;   // center / stop
  constexpr float VOLT_MAX   = 5.0f;   // full forward
  constexpr float SENSE_DIV  = 2.0f;   // /2 resistor divider on GPIO36
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
  constexpr uint32_t WDT_TIMEOUT_S     = 4;      // task watchdog
}
