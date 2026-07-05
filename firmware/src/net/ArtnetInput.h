// ArtnetInput.h — minimal Art-Net (ArtDMX, OpCode 0x5000) receiver over AsyncUDP.
#pragma once
#include "../ControlTypes.h"
#include "../InputMux.h"
#include <AsyncUDP.h>

class ArtnetInput {
 public:
  bool begin(InputMux* mux, uint16_t universe);
  void setUniverse(uint16_t u) { universe_ = u; }

 private:
  void handle(AsyncUDPPacket& p);
  InputMux* mux_      = nullptr;
  uint16_t  universe_ = 0;      // 15-bit port-address
  AsyncUDP  udp_;
};
