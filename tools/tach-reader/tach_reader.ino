/*
 * tach_reader.ino — single-sensor gear-tooth tachometer for RA Roto.
 *
 * Reads one tooth/slot sensor (Hall, inductive, or optical) watching a gear and
 * reports actual shaft speed to the control console over USB serial. Uses
 * PERIOD TIMING (interval between teeth), not count-per-window, so it stays
 * accurate at very low RPM — one fresh reading on every tooth, plus a clean
 * "stalled" flag when teeth stop arriving.
 *
 * Direction is NOT sensed (single sensor). The console already knows the
 * commanded direction, so magnitude + command sign is enough.
 *
 * Wiring: sensor output -> SENSOR_PIN (needs a clean digital edge; use a Hall/
 * comparator output or add a Schmitt trigger). Match voltage to your board.
 * Report line (parsed by the console):   RPM=<float> STALL=<0|1>
 */

const uint8_t SENSOR_PIN     = 2;      // must be an interrupt-capable pin
const uint16_t TEETH         = 20;     // teeth (or slots) per shaft revolution
const uint32_t MIN_INTERVAL_US = 500;  // glitch filter: ignore edges faster than this
const uint32_t STALL_US       = 2000000UL; // no tooth for 2 s -> stalled
const uint16_t REPORT_MS      = 100;   // ~10 Hz serial reports

volatile uint32_t lastEdgeUs = 0;      // time of the most recent valid edge
volatile uint32_t periodUs   = 0;      // interval between the last two teeth
volatile bool     gotTooth   = false;

void onEdge() {
  uint32_t now = micros();
  uint32_t dt = now - lastEdgeUs;
  if (dt < MIN_INTERVAL_US) return;    // debounce / glitch reject
  periodUs = dt;
  lastEdgeUs = now;
  gotTooth = true;
}

void setup() {
  Serial.begin(115200);
  pinMode(SENSOR_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(SENSOR_PIN), onEdge, FALLING);
  lastEdgeUs = micros();
}

void loop() {
  static uint32_t nextReport = 0;
  if (millis() < nextReport) return;
  nextReport = millis() + REPORT_MS;

  // snapshot volatiles
  noInterrupts();
  uint32_t p = periodUs;
  uint32_t last = lastEdgeUs;
  interrupts();

  uint32_t sinceLast = micros() - last;
  bool stalled = (sinceLast > STALL_US) || (p == 0);

  float rpm = 0.0f;
  if (!stalled && p > 0) {
    // seconds per tooth -> teeth/sec -> rev/sec -> rpm
    float teethPerSec = 1000000.0f / (float)p;
    rpm = (teethPerSec / (float)TEETH) * 60.0f;
    // if the shaft is decelerating, the current gap may already exceed the last
    // measured period — reflect that so RPM decays instead of latching high.
    if (sinceLast > p) {
      float est = (1000000.0f / (float)sinceLast) / (float)TEETH * 60.0f;
      if (est < rpm) rpm = est;
    }
  }

  Serial.print("RPM=");
  Serial.print(rpm, 2);
  Serial.print(" STALL=");
  Serial.println(stalled ? 1 : 0);
}
