// RA Roto Control — firmware entry point.
// Signal chain: DMX/Art-Net/sACN -> InputMux -> PersonaEngine -> SafetyStage -> SerialController -> HDC2450.
// Safety: we command STOP before enabling the controller, send !G continuously (which also feeds
// the HDC2450's ^RWD watchdog), and an ESP task watchdog resets us into the stop state on a hang.
#include <Arduino.h>
#include <esp_task_wdt.h>

#include "Config.h"
#include "ControlTypes.h"
#include "ConfigStore.h"
#include "SerialController.h"
#include "PersonaEngine.h"
#include "SafetyStage.h"
#include "InputMux.h"
#include "net/NetworkManager.h"
#include "net/ArtnetInput.h"
#include "net/SacnInput.h"
#include "web/WebInterface.h"

static Settings         settings;
static ControlState     state;
static HardwareSerial   HdcSerial(1);        // UART1 -> MAX3232 -> HDC2450 RS232
static SerialController  hdcCtl;
static SafetyStage       safety;
static InputMux          mux;
static ArtnetInput       artnet;
static SacnInput         sacn;
static WebInterface      web;

static uint32_t lastControlUs = 0;
static uint32_t lastCmdMs     = 0;
static uint32_t lastPollMs    = 0;
static uint32_t lastHouseMs   = 0;
static uint32_t bootMs        = 0;
static bool     configured_   = false;       // HDC2450 ^RWD/echo set since last reconnect

static bool estopActive() {
  // Active-low: external pull-up, switch to GND. (Nothing wired -> reads HIGH -> inactive.)
  return digitalRead(pins::ESTOP_IN) == LOW;
}
static void setPwrCtrl(bool on) { digitalWrite(pins::PWRCTRL_EN, on ? HIGH : LOW); }

static void onSettingsChanged() {
  ConfigStore::save(settings);
  safety.setSlew(settings.slewLimit);
  artnet.setUniverse(settings.artnetUniverse);
  // NOTE: changing the sACN universe needs a multicast re-join (listener restart) — TODO Phase 3.
}

void setup() {
  Serial.begin(115200);
  bootMs = millis();

  pinMode(pins::STATUS_LED, OUTPUT);
  pinMode(pins::PWRCTRL_EN, OUTPUT);
  setPwrCtrl(false);
  pinMode(pins::ESTOP_IN, INPUT);

  ConfigStore::load(settings);

  // --- Safety-critical: serial up + command STOP before the controller is powered ---
  hdcCtl.begin(&HdcSerial, pins::HDC_RX, pins::HDC_TX, hdc::BAUD);
  hdcCtl.setCommand(cmd::STOP);
  safety.begin(cmd::STOP, settings.slewLimit);

  mux.begin(&settings);
  NetworkManager::begin(settings, RA_HOSTNAME_DEFAULT);
  if (settings.artnetEnabled) artnet.begin(&mux, settings.artnetUniverse);
  if (settings.sacnEnabled)   sacn.begin(&mux, settings.sacnUniverse);
  web.begin(&state, &settings, &mux, onSettingsChanged);

  esp_task_wdt_init(timing::WDT_TIMEOUT_S, /*panic=*/true);
  esp_task_wdt_add(NULL);

  // Power the controller now that we are already commanding stop (unless E-stopped).
  setPwrCtrl(!estopActive());

  lastControlUs = micros();
  Serial.printf("[RA] %s ready. persona=%s\n", RA_FW_VERSION, toString(settings.persona));
}

void loop() {
  esp_task_wdt_reset();
  const uint32_t nowUs = micros();
  const uint32_t nowMs = millis();

  // --- Control loop (200 Hz) ---
  if (nowUs - lastControlUs >= timing::CONTROL_TICK_US) {
    const float dt = (nowUs - lastControlUs) / 1e6f;
    lastControlUs = nowUs;

    const bool estop = estopActive();
    safety.forceFailSafe(estop);
    if (estop) setPwrCtrl(false);

    InputMux::Selected sel = mux.select(nowMs);
    const float targetCmd = PersonaEngine::toCommand(settings, sel.d);
    const float outCmd    = safety.update(targetCmd, dt, sel.live);

    state.activeSource = safety.inFailSafe() ? CommandSource::FailSafe : sel.src;
    state.normalizedD  = sel.d;
    state.targetCmd    = targetCmd;
    state.outputCmd    = outCmd;
    state.failSafe     = safety.inFailSafe();
    state.overrideOn   = mux.overrideActive();
    state.estopActive  = estop;
  }

  // --- Send command to the HDC2450 (20 Hz; also feeds the ^RWD watchdog) ---
  if (nowMs - lastCmdMs >= hdc::CMD_INTERVAL_MS) {
    lastCmdMs = nowMs;
    hdcCtl.setCommand(state.outputCmd);
  }

  // --- Telemetry poll + (re)configure on reconnect ---
  if (nowMs - lastPollMs >= hdc::POLL_INTERVAL_MS) {
    lastPollMs = nowMs;
    hdcCtl.poll(state.tele);
    state.controllerOnline = hdcCtl.online();
    if (state.controllerOnline && !configured_) { hdcCtl.configure(); configured_ = true; }
    if (!state.controllerOnline) configured_ = false;
  }

  // --- Housekeeping / status ---
  if (nowMs - lastHouseMs >= timing::TELEMETRY_MS) {
    lastHouseMs     = nowMs;
    state.ethLinkUp = NetworkManager::linkUp();
    strncpy(state.ip, NetworkManager::ipString(), sizeof(state.ip) - 1);
    state.uptimeS   = (nowMs - bootMs) / 1000;
    digitalWrite(pins::STATUS_LED, state.failSafe ? ((nowMs / 250) & 1) : HIGH);
  }

  web.loop();
}
