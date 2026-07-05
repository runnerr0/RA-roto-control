#include "ArtnetInput.h"
#include "../Config.h"
#include <Arduino.h>
#include <string.h>

// ArtDMX layout: "Art-Net\0"(8) op(2 LE) protHi/Lo seq phys subUni net lenHi lenLo data...
static constexpr uint16_t OP_DMX     = 0x5000;
static constexpr size_t   HDR_LEN    = 18;

bool ArtnetInput::begin(InputMux* mux, uint16_t universe) {
  mux_ = mux;
  universe_ = universe;
  if (!udp_.listen(net::ARTNET_PORT)) return false;
  udp_.onPacket([this](AsyncUDPPacket p) { handle(p); });
  return true;
}

void ArtnetInput::handle(AsyncUDPPacket& p) {
  const uint8_t* d = p.data();
  const size_t   n = p.length();
  if (n < HDR_LEN || !mux_) return;
  if (memcmp(d, "Art-Net\0", 8) != 0) return;

  const uint16_t op = uint16_t(d[8]) | (uint16_t(d[9]) << 8);   // little-endian
  if (op != OP_DMX) return;

  const uint16_t univ = (uint16_t(d[15]) << 8) | d[14];          // Net<<8 | SubUni
  if (univ != universe_) return;

  uint16_t len = (uint16_t(d[16]) << 8) | d[17];                 // big-endian
  const size_t avail = n - HDR_LEN;
  if (len > avail) len = avail;

  mux_->onDmxFrame(CommandSource::Artnet, d + HDR_LEN, len, millis());
}
