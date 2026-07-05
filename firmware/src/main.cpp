// RA Roto Control — firmware entry point.
// Signal chain: DMX/Art-Net/sACN -> InputMux -> PersonaEngine -> SafetyStage -> DacDriver -> MCP4725.
// Safety order of operations: the DAC is driven to the fail-safe (stop) voltage BEFORE
// anything else comes up, and a task watchdog resets us back into that state on a hang.
#include <Arduino.h>
#include <Wire.h>
#include <esp_task_wdt.h>

#include "Config.h"
#include "ControlTypes.h"
#include "ConfigStore.h"
#include "DacDriver.h"
#include "SenseAdc.h"
#include "PersonaEngine.h"
#include "SafetyStage.h"
#include "InputMux.h"
#include "net/NetworkManager.h"
#include "net/ArtnetInput.h"
#include "net/SacnInput.h"
#include "web/WebInterface.h"

static Settings      settings;
static ControlState  state;
static DacDriver     dacOut;
static SenseAdc      sense;
static SafetyStage   safety;
static InputMux      mux;
static ArtnetInput   artnet;
static SacnInput     sacn;
static WebInterface  web;

static uint32_t lastControlUs = 0;
static uint32_t lastSenseMs   = 0;
static uint32_t bootMs        = 0;

static bool estopActive() {
  // Active-low: external pull-up, button/switch to GND. (No E-stop wired -> reads HIGH -> inactive.)
  return digitalRead(pins::ESTOP_IN) == LOW;
}

static void setPwrCtrl(bool on) {
  digitalWrite(pins::PWRCTRL_EN, on ? HIGH : LOW);
}

// Re-apply settings that affect live modules after a web edit.
static void onSettingsChanged() {
  ConfigStore::save(settings);
  safety.setSlew(settings.slewLimitVps);
  safety.setFailSafe(settings.failSafeV);
  dacOut.setCalibration(settings.dacCode0V, settings.dacCode5V);
  artnet.setUniverse(settings.artnetUniverse);
  // NOTE: changing the sACN universe needs a multicast re-join (listener restart) — TODO Phase 3.
}

void setup() {
  Serial.begin(115200);
  bootMs = millis();

  pinMode(pins::STATUS_LED, OUTPUT);
  pinMode(pins::PWRCTRL_EN, OUTPUT);
  setPwrCtrl(false);                       // controller stays off until DAC is at stop
  pinMode(pins::ESTOP_IN, INPUT);          // external pull-up expected

  ConfigStore::load(settings);

  // --- Safety-critical: DAC to fail-safe (stop) BEFORE anything else ---
  dacOut.begin(pins::I2C_SDA, pins::I2C_SCL, dac::I2C_ADDR, dac::I2C_HZ);
  dacOut.setCalibration(settings.dacCode0V, settings.dacCode5V);
  dacOut.writeVoltage(settings.failSafeV);
  safety.begin(settings.failSafeV, settings.failSafeV, settings.slewLimitVps);

  sense.begin(pins::SENSE_ADC);
  mux.begin(&settings);

  NetworkManager::begin(settings, RA_HOSTNAME_DEFAULT);
  if (settings.artnetEnabled) artnet.begin(&mux, settings.artnetUniverse);
  if (settings.sacnEnabled)   sacn.begin(&mux, settings.sacnUniverse);
  web.begin(&state, &settings, &mux, onSettingsChanged);

  // Task watchdog: a hang resets the chip; setup() then re-drives the DAC to stop.
  esp_task_wdt_init(timing::WDT_TIMEOUT_S, /*panic=*/true);
  esp_task_wdt_add(NULL);

  // Controller only comes up now that the command line reads "stop", and only if no E-stop.
  setPwrCtrl(!estopActive());

  lastControlUs = micros();
  Serial.printf("[RA] %s ready. persona=%s failsafe=%.2fV\n",
                RA_FW_VERSION, toString(settings.persona), settings.failSafeV);
}

void loop() {
  esp_task_wdt_reset();
  const uint32_t nowUs = micros();

  if (nowUs - lastControlUs >= timing::CONTROL_TICK_US) {
    const float dt = (nowUs - lastControlUs) / 1e6f;
    lastControlUs = nowUs;
    const uint32_t nowMs = millis();

    const bool estop = estopActive();
    safety.forceFailSafe(estop);
    if (estop) setPwrCtrl(false);

    InputMux::Selected sel = mux.select(nowMs);
    const float targetV = PersonaEngine::toVoltage(settings, sel.d);
    const float outV    = safety.update(targetV, dt, sel.live);
    dacOut.writeVoltage(outV);

    state.activeSource = safety.inFailSafe() ? CommandSource::FailSafe : sel.src;
    state.normalizedD  = sel.d;
    state.targetV      = targetV;
    state.outputV      = outV;
    state.failSafe     = safety.inFailSafe();
    state.overrideOn   = mux.overrideActive();
    state.estopActive  = estop;
    state.dacHealthy   = dacOut.healthy();
  }

  const uint32_t nowMs = millis();
  if (nowMs - lastSenseMs >= timing::TELEMETRY_MS) {
    lastSenseMs        = nowMs;
    state.measuredV    = sense.readVoltage();
    state.ethLinkUp    = NetworkManager::linkUp();
    strncpy(state.ip, NetworkManager::ipString(), sizeof(state.ip) - 1);
    state.uptimeS      = (nowMs - bootMs) / 1000;
    digitalWrite(pins::STATUS_LED, state.failSafe ? ((nowMs / 250) & 1) : HIGH);
  }

  web.loop();
}
