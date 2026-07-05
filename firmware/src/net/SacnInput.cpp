#include "SacnInput.h"
#include "../Config.h"
#include <Arduino.h>
#include <string.h>

// E1.31 fixed offsets (unicast/multicast, DMX start code 0x00):
//   4..15  ACN Packet Identifier "ASC-E1.17\0\0\0"
//   113..114 Universe (big-endian)
//   123..124 DMP property value count (big-endian) = 1 + slots
//   125    DMX start code
//   126..  channel data
static constexpr size_t E131_MIN      = 126;
static constexpr size_t OFF_ACN_ID    = 4;
static constexpr size_t OFF_UNIVERSE  = 113;
static constexpr size_t OFF_PROP_CNT  = 123;
static constexpr size_t OFF_STARTCODE = 125;
static constexpr size_t OFF_DATA      = 126;

bool SacnInput::begin(InputMux* mux, uint16_t universe) {
  mux_ = mux;
  universe_ = universe;
  const IPAddress mcast(239, 255, (universe >> 8) & 0xFF, universe & 0xFF);
  if (!udp_.listenMulticast(mcast, net::SACN_PORT)) return false;
  udp_.onPacket([this](AsyncUDPPacket p) { handle(p); });
  return true;
}

void SacnInput::handle(AsyncUDPPacket& p) {
  const uint8_t* d = p.data();
  const size_t   n = p.length();
  if (n < E131_MIN || !mux_) return;
  if (memcmp(d + OFF_ACN_ID, "ASC-E1.17", 9) != 0) return;

  const uint16_t univ = (uint16_t(d[OFF_UNIVERSE]) << 8) | d[OFF_UNIVERSE + 1];
  if (univ != universe_) return;
  if (d[OFF_STARTCODE] != 0x00) return;                 // only dimmer data

  uint16_t propCnt = (uint16_t(d[OFF_PROP_CNT]) << 8) | d[OFF_PROP_CNT + 1];
  uint16_t slots = (propCnt > 0) ? propCnt - 1 : 0;     // minus the start code
  const size_t avail = n - OFF_DATA;
  if (slots > avail) slots = avail;

  mux_->onDmxFrame(CommandSource::Sacn, d + OFF_DATA, slots, millis());
}
