// WebInterface.h — async HTTP + WebSocket: live status, settings, manual override.
// Serves a minimal embedded dashboard; the full LittleFS SPA is a later phase.
#pragma once
#include "../ControlTypes.h"
#include "../InputMux.h"
#include <ESPAsyncWebServer.h>
#include <functional>

class WebInterface {
 public:
  using ChangedCb = std::function<void()>;

  void begin(ControlState* state, Settings* settings, InputMux* mux, ChangedCb onChanged);
  void loop();                 // ws housekeeping + telemetry push

 private:
  String statusJson() const;
  String settingsJson() const;
  void   applySettings(const JsonVariant& j);

  AsyncWebServer server_{80};
  AsyncWebSocket ws_{"/ws"};
  ControlState*  state_    = nullptr;
  Settings*      settings_ = nullptr;
  InputMux*      mux_      = nullptr;
  ChangedCb      onChanged_;
  uint32_t       lastPush_ = 0;
};
