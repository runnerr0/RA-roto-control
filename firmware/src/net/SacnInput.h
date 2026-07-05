// SacnInput.h — minimal sACN / E1.31 receiver over multicast AsyncUDP.
#pragma once
#include "../ControlTypes.h"
#include "../InputMux.h"
#include <AsyncUDP.h>

class SacnInput {
 public:
  bool begin(InputMux* mux, uint16_t universe);   // joins 239.255.<hi>.<lo>

 private:
  void handle(AsyncUDPPacket& p);
  InputMux* mux_      = nullptr;
  uint16_t  universe_ = 1;
  AsyncUDP  udp_;
};
