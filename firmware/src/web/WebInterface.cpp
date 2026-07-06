#include "WebInterface.h"
#include "../Config.h"
#include <Arduino.h>
#include <ArduinoJson.h>
#include <AsyncJson.h>

// Minimal embedded dashboard. The full LittleFS SPA (persona editor, network config,
// diagnostics, telemetry graphs) is Phase 3 — see docs/ARCHITECTURE.md.
static const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>RA Roto Control</title><style>
body{font:14px ui-monospace,Menlo,monospace;background:#0e1420;color:#e6ecf5;margin:0;padding:20px}
h1{font-size:16px;color:#f0a830;letter-spacing:.12em;text-transform:uppercase}
h2{font-size:12px;color:#93a2bd;letter-spacing:.1em;text-transform:uppercase;margin:18px 0 6px}
.k{color:#93a2bd}.v{color:#e6ecf5;font-weight:600}
table{border-collapse:collapse}td{padding:4px 14px 4px 0}
.row{margin:10px 0}button{font:inherit;background:#1b2536;color:#e6ecf5;border:1px solid #46587a;border-radius:6px;padding:6px 12px;cursor:pointer}
button.on{background:#a8382b;border-color:#d1584a}input[type=range]{width:240px;vertical-align:middle}
.fs{color:#d1584a}.ok{color:#46c483}.off{color:#d1584a}
</style></head><body>
<h1>RA Roto Control</h1>
<h2>command</h2>
<table>
<tr><td class=k>source</td><td class=v id=src>-</td></tr>
<tr><td class=k>input</td><td class=v id=d>-</td></tr>
<tr><td class=k>target</td><td class=v id=tc>-</td></tr>
<tr><td class=k>output</td><td class=v id=oc>-</td></tr>
<tr><td class=k>state</td><td class=v id=st>-</td></tr>
</table>
<h2>controller (HDC2450)</h2>
<table>
<tr><td class=k>serial</td><td class=v id=con>-</td></tr>
<tr><td class=k>motor amps</td><td class=v id=amps>-</td></tr>
<tr><td class=k>battery</td><td class=v id=bat>-</td></tr>
<tr><td class=k>temp</td><td class=v id=tmp>-</td></tr>
<tr><td class=k>faults</td><td class=v id=ff>-</td></tr>
</table>
<h2>system</h2>
<table>
<tr><td class=k>ethernet</td><td class=v id=eth>-</td></tr>
<tr><td class=k>uptime</td><td class=v id=up>-</td></tr>
</table>
<div class=row><button id=ob onclick=tgl()>OVERRIDE: OFF</button>
<input type=range min=0 max=100 value=50 id=osl oninput=snd()> <span id=ov2>50% (0=rev,50=stop,100=fwd)</span></div>
<script>
let on=false;
function tgl(){on=!on;snd()}
function snd(){let v=document.getElementById('osl').value;document.getElementById('ov2').textContent=v+'% (0=rev,50=stop,100=fwd)';
document.getElementById('ob').textContent='OVERRIDE: '+(on?'ON':'OFF');document.getElementById('ob').className=on?'on':'';
fetch('/api/override?on='+(on?1:0)+'&v='+(v/100),{method:'POST'})}
function pct(x){return (x*100).toFixed(1)+'%'}
async function poll(){try{let s=await(await fetch('/api/status')).json();
src.textContent=s.source;d.textContent=pct(s.d);tc.textContent=pct(s.targetCmd);oc.textContent=pct(s.outputCmd);
st.innerHTML=s.failSafe?'<span class=fs>FAIL-SAFE (stop)</span>':'<span class=ok>running</span>';
con.innerHTML=s.controllerOnline?'<span class=ok>online</span>':'<span class=off>offline</span>';
amps.textContent=s.amps.toFixed(1)+' A';bat.textContent=s.battery.toFixed(1)+' V';
tmp.textContent=s.temp+' °C';ff.textContent='0x'+s.faults.toString(16);
eth.textContent=s.eth?('up '+s.ip):'down';up.textContent=s.uptime+' s';}catch(e){}}
setInterval(poll,500);poll();
</script></body></html>
)HTML";

void WebInterface::begin(ControlState* state, Settings* settings, InputMux* mux, ChangedCb onChanged) {
  state_ = state; settings_ = settings; mux_ = mux; onChanged_ = onChanged;

  server_.on("/", HTTP_GET, [](AsyncWebServerRequest* r) {
    r->send(200, "text/html", INDEX_HTML);
  });
  server_.on("/api/status", HTTP_GET, [this](AsyncWebServerRequest* r) {
    r->send(200, "application/json", statusJson());
  });
  server_.on("/api/settings", HTTP_GET, [this](AsyncWebServerRequest* r) {
    r->send(200, "application/json", settingsJson());
  });

  auto* settingsPost = new AsyncCallbackJsonWebHandler(
      "/api/settings", [this](AsyncWebServerRequest* r, JsonVariant& j) {
        applySettings(j);
        if (onChanged_) onChanged_();
        r->send(200, "application/json", settingsJson());
      });
  server_.addHandler(settingsPost);

  server_.on("/api/override", HTTP_POST, [this](AsyncWebServerRequest* r) {
    bool on = r->hasParam("on", true) ? r->getParam("on", true)->value().toInt()
            : (r->hasParam("on")      ? r->getParam("on")->value().toInt() : 0);
    float v = r->hasParam("v", true) ? r->getParam("v", true)->value().toFloat()
            : (r->hasParam("v")      ? r->getParam("v")->value().toFloat() : 0.5f);
    if (mux_) mux_->setOverride(on != 0, v);
    r->send(200, "application/json", "{\"ok\":true}");
  });

  server_.addHandler(&ws_);
  server_.begin();
}

void WebInterface::loop() {
  ws_.cleanupClients();
  const uint32_t now = millis();
  if (now - lastPush_ >= timing::TELEMETRY_MS) {
    lastPush_ = now;
    if (ws_.count() > 0) ws_.textAll(statusJson());
  }
}

String WebInterface::statusJson() const {
  JsonDocument doc;
  if (state_) {
    doc["source"]    = toString(state_->activeSource);
    doc["d"]         = state_->normalizedD;
    doc["targetCmd"] = state_->targetCmd;
    doc["outputCmd"] = state_->outputCmd;
    doc["failSafe"]  = state_->failSafe;
    doc["override"]  = state_->overrideOn;
    doc["estop"]     = state_->estopActive;
    doc["controllerOnline"] = state_->controllerOnline;
    doc["amps"]      = state_->tele.motorAmps;
    doc["battery"]   = state_->tele.batteryV;
    doc["temp"]      = state_->tele.tempC;
    doc["faults"]    = state_->tele.faultFlags;
    doc["eth"]       = state_->ethLinkUp;
    doc["ip"]        = state_->ip;
    doc["uptime"]    = state_->uptimeS;
  }
  String out;
  serializeJson(doc, out);
  return out;
}

String WebInterface::settingsJson() const {
  JsonDocument doc;
  if (settings_) {
    const Settings& s = *settings_;
    doc["persona"]    = int(s.persona);
    doc["dmxStart"]   = s.dmxStart;
    doc["multiplier"] = s.multiplier;
    doc["deadband"]   = s.deadband;
    doc["slewLimit"]  = s.slewLimit;
    doc["invert"]     = s.invert;
    doc["artnet"]     = s.artnetEnabled;
    doc["sacn"]       = s.sacnEnabled;
    doc["dmx512"]     = s.dmx512Enabled;
    doc["artnetUni"]  = s.artnetUniverse;
    doc["sacnUni"]    = s.sacnUniverse;
  }
  String out;
  serializeJson(doc, out);
  return out;
}

void WebInterface::applySettings(const JsonVariant& j) {
  if (!settings_) return;
  Settings& s = *settings_;
  if (j["persona"].is<int>())      s.persona      = Persona(uint8_t(j["persona"].as<int>()));
  if (j["dmxStart"].is<int>())     s.dmxStart     = constrain(j["dmxStart"].as<int>(), 1, 512);
  if (j["multiplier"].is<float>()) s.multiplier   = constrain(j["multiplier"].as<float>(), 0.0f, 1.0f);
  if (j["deadband"].is<int>())     s.deadband     = constrain(j["deadband"].as<int>(), 0, 40);
  if (j["slewLimit"].is<float>())  s.slewLimit    = max(0.0f, j["slewLimit"].as<float>());
  if (j["invert"].is<bool>())      s.invert       = j["invert"].as<bool>();
  if (j["artnet"].is<bool>())      s.artnetEnabled= j["artnet"].as<bool>();
  if (j["sacn"].is<bool>())        s.sacnEnabled  = j["sacn"].as<bool>();
  if (j["dmx512"].is<bool>())      s.dmx512Enabled= j["dmx512"].as<bool>();
  if (j["artnetUni"].is<int>())    s.artnetUniverse = j["artnetUni"].as<int>();
  if (j["sacnUni"].is<int>())      s.sacnUniverse   = constrain(j["sacnUni"].as<int>(), 1, 63999);
}
