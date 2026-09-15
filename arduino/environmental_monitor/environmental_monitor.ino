/*
 * ===========================================================================
 *  Environmental Intelligence Platform - Arduino UNO R4 WiFi edge node
 * ===========================================================================
 *
 *  Sensors - AUTHORITATIVE PIN MAP. This table, arduino/README.md,
 *  docs/hardware.md and config.h must always agree; if they disagree, this
 *  table and config.h win because they are what actually compiles.
 *    - AM2302 / DHT22   temperature + relative humidity   (D2, one-wire)
 *      or DHT12 (I2C)   temperature + relative humidity   (I2C 0x5C, SDA/SCL)
 *                       - selected by TEMP_HUMIDITY_SENSOR in config.h
 *    - BMP280           barometric pressure + temperature (I2C, 0x76/0x77)
 *    - Rain sensor      analog wetness                    (A0)
 *    - LDR              analog illumination               (A1)
 *    - MQ-135           analog air-quality                (A2)
 *
 *  Actuators
 *    - 5 LEDs           D3 D4 D5 D6 D7 = risk level 1..5. See updateLeds() for
 *                       exactly which of them is lit for each level.
 *    - 1 buzzer         D8, pattern driven by the same backend assessment
 *
 *  Note on the temperature/humidity sensor
 *    The AM2302/DHT22 and the DHT12 do NOT share a protocol. A DHT12 in
 *    one-wire mode speaks the DHT11-style frame (integer + decimal bytes) with
 *    an ~18 ms wake-up, so reading it as DHT22 with the Adafruit DHT library
 *    would produce garbage values rather than a clean error. This firmware
 *    therefore supports exactly two explicit configurations and refuses the
 *    invalid combination at compile time - it never pretends the two sensors
 *    are interchangeable. See the selection block in config.h.
 *
 *  Data flow
 *    read sensors -> validate -> JSON payload -> HTTP POST (X-API-Key) ->
 *    FastAPI validates/stores/scores -> polls GET /device/{id}/risk-state ->
 *    LEDs + buzzer mirror the backend's risk level
 *
 *  Design rules honoured here
 *    * No secret is hardcoded: credentials live in config.h (git-ignored).
 *    * Nothing blocks indefinitely: every network step has a deadline and the
 *      main loop stays responsive so the indicators never freeze.
 *    * The firmware never invents a risk level. It mirrors the backend; when the
 *      backend cannot be reached it keeps the last known level and shows a
 *      clearly visible "stale" blink instead of guessing.
 *    * Invalid sensor readings are omitted (and reported as missing) rather than
 *      sent as garbage data.
 *
 *  Required libraries (Arduino IDE -> Library Manager)
 *    - DHT sensor library (Adafruit)          [only when TEMP_HUMIDITY_SENSOR
 *                                              == SENSOR_AM2302_DHT22]
 *    - Adafruit BMP280 Library  (+ Adafruit Unified Sensor, installed with it)
 *    - ArduinoJson (>= 7.0)
 *    WiFiS3 / Wire ship with the Arduino UNO R4 core and need no install.
 *
 *  IMPORTANT: this firmware has NOT been executed on physical hardware yet -
 *  the Arduino IDE/toolchain was unavailable where it was written. It is
 *  statically reviewed and written to be UNO R4 WiFi (+ WiFiS3) correct, but
 *  "compiles" and "reads the right values on a bench" are claims that require
 *  the real toolchain and real sensors. See arduino/README.md.
 * ===========================================================================
 */

#include <ArduinoJson.h>
#include <Adafruit_BMP280.h>
#include <Wire.h>
#include <WiFiS3.h>

#include <math.h>
#include <stdio.h>
#include <string.h>

#if __has_include("config.h")
#include "config.h"
#else
#include "config.example.h"
#define USING_TEMPLATE_CONFIG 1
#endif

/* The Adafruit DHT library is only pulled in for the AM2302/DHT22 build; the
 * DHT12 is read directly over I2C (see readTempHumidity) and must not be fed to
 * a DHT22 decoder. */
#if TEMP_HUMIDITY_SENSOR == SENSOR_AM2302_DHT22
#include <DHT.h>
#elif TEMP_HUMIDITY_SENSOR == SENSOR_DHT12_I2C
#else
#error "TEMP_HUMIDITY_SENSOR must be SENSOR_AM2302_DHT22 or SENSOR_DHT12_I2C (see config.h)"
#endif

/* -------------------------------------------------------------------------- */
/*  Compile-time pin-map verification                                          */
/* -------------------------------------------------------------------------- */

/* Every signal pin must be distinct: no LED may share a pin with another LED,
 * with a sensor, or with the buzzer. A wiring table the compiler checks cannot
 * silently drift away from the documentation. */
namespace pincheck {
constexpr uint8_t PINS[] = {PIN_RAIN_ANALOG, PIN_LDR_ANALOG, PIN_MQ135_ANALOG, PIN_LED_1,
                            PIN_LED_2,       PIN_LED_3,       PIN_LED_4,        PIN_LED_5,
                            PIN_BUZZER};
constexpr size_t COUNT = sizeof(PINS) / sizeof(PINS[0]);
constexpr bool allDistinct() {
  for (size_t i = 0; i < COUNT; i++) {
    for (size_t j = i + 1; j < COUNT; j++) {
      if (PINS[i] == PINS[j]) return false;
    }
  }
  return true;
}
constexpr bool dhtClear() {
#if TEMP_HUMIDITY_SENSOR == SENSOR_AM2302_DHT22
  for (size_t i = 0; i < COUNT; i++) {
    if (PINS[i] == PIN_DHT) return false;
  }
#endif
  return true;
}
static_assert(allDistinct(), "Pin conflict: two of rain/LDR/MQ-135/LEDs/buzzer share a pin");
static_assert(dhtClear(), "Pin conflict: PIN_DHT collides with an LED or the buzzer pin");
}  // namespace pincheck

/* -------------------------------------------------------------------------- */
/*  Runtime state                                                             */
/* -------------------------------------------------------------------------- */

namespace {

WiFiClient httpClient;
Adafruit_BMP280 bmp;

#if TEMP_HUMIDITY_SENSOR == SENSOR_AM2302_DHT22
DHT dht(PIN_DHT, DHT_TYPE);
#else
/* The DHT12 speaks I2C at a fixed address; nothing but Wire is needed. */
constexpr uint8_t DHT12_ADDRESS = DHT12_I2C_ADDRESS;
#endif

/* Forward declarations: the HTTP helpers call each other before their bodies. */
int contentLengthOf(const String &raw);
void applyRiskStateFromIngestion(const JsonDocument &response);

const uint8_t LED_PINS[5] = {PIN_LED_1, PIN_LED_2, PIN_LED_3, PIN_LED_4, PIN_LED_5};

/* Latest valid readings. ``has*`` flags let us omit a failed channel instead of
 * transmitting a stale or fabricated number. */
struct SensorValues {
  bool hasTempHum = false;
  float temperatureC = NAN;
  float humidityPct = NAN;

  bool hasBmp = false;
  float bmpTemperatureC = NAN;
  float pressureHpa = NAN;

  bool hasRain = false;
  int rainRaw = 0;
  bool hasLight = false;
  int lightRaw = 0;
  bool hasAir = false;
  int airRaw = 0;
};

SensorValues sensors;

uint8_t sensorFailures = 0;      /* consecutive failed read cycles */
uint32_t sequence = 0;

/* Backend-driven indicator state. */
int riskLevel = 0;               /* 0 = no assessment received yet            */
bool riskStale = false;          /* backend reachable, but data is stale      */
bool haveRiskState = false;
int activeAlerts = 0;
char buzzerPattern[24] = "silent";

/* Clock: the UNO R4 has no RTC, so the node learns the wall clock from the
 * backend's ``server_time`` field and keeps counting with millis(). Until that
 * happens the payload simply omits ``timestamp`` and the backend stamps the
 * arrival time itself (never a wrong time). */
bool clockSynced = false;
uint32_t clockAnchorMillis = 0;
uint32_t clockEpochAtAnchor = 0;

uint32_t lastSendAt = 0;
uint32_t lastRiskPollAt = 0;
uint32_t lastWifiAttemptAt = 0;
uint32_t wifiDownSince = 0;
uint32_t successfulPosts = 0;
uint32_t failedPosts = 0;

/* ---- non-blocking buzzer pattern player ---------------------------------- */
enum class BuzzerMode : uint8_t { Silent, SingleShort, DoubleShort, CriticalAlarm };

BuzzerMode buzzerMode = BuzzerMode::Silent;
uint8_t buzzerStep = 0;
uint32_t buzzerStepStart = 0;
uint32_t buzzerCycleStart = 0;
bool buzzerOn = false;

/* BUZZER_PASSIVE selects how "sound" is produced, and equally how silence is
 * produced. An active buzzer module has its own oscillator, so plain HIGH is
 * the correct drive and tone() is unnecessary; a passive piezo needs tone() at
 * BUZZER_FREQUENCY_HZ because a static level makes no sound at all. Both paths
 * are non-blocking: the pattern player below only flips state on millis(). */
inline void buzzerStart() {
#if BUZZER_PASSIVE
  tone(PIN_BUZZER, BUZZER_FREQUENCY_HZ);
#else
  digitalWrite(PIN_BUZZER, HIGH);
#endif
}

inline void buzzerStop() {
#if BUZZER_PASSIVE
  noTone(PIN_BUZZER);
#else
  digitalWrite(PIN_BUZZER, LOW);
#endif
}

const char *modeName(BuzzerMode mode) {
  switch (mode) {
    case BuzzerMode::Silent: return "silent";
    case BuzzerMode::SingleShort: return "single_short_60s";
    case BuzzerMode::DoubleShort: return "double_short_30s";
    case BuzzerMode::CriticalAlarm: return "critical_alarm";
  }
  return "silent";
}

BuzzerMode modeFromPattern(const char *pattern) {
  if (pattern == nullptr) return BuzzerMode::Silent;
  if (strcmp(pattern, "critical_alarm") == 0) return BuzzerMode::CriticalAlarm;
  if (strcmp(pattern, "double_short_30s") == 0) return BuzzerMode::DoubleShort;
  if (strcmp(pattern, "single_short_60s") == 0) return BuzzerMode::SingleShort;
  return BuzzerMode::Silent;
}

/* -------------------------------------------------------------------------- */
/*  Serial diagnostics (never logs credentials)                               */
/* -------------------------------------------------------------------------- */

void logLine(const char *level, const String &message) {
  Serial.print('[');
  Serial.print(millis() / 1000UL);
  Serial.print("s] ");
  Serial.print(level);
  Serial.print(": ");
  Serial.println(message);
}

void logInfo(const String &message) { logLine("INFO", message); }
void logWarn(const String &message) { logLine("WARN", message); }
void logError(const String &message) { logLine("ERROR", message); }

/* -------------------------------------------------------------------------- */
/*  Time helpers                                                              */
/* -------------------------------------------------------------------------- */

/* Days since 1970-01-01 for a civil date (Howard Hinnant's algorithm). */
uint32_t daysFromCivil(int year, unsigned month, unsigned day) {
  year -= month <= 2;
  const int era = (year >= 0 ? year : year - 399) / 400;
  const unsigned yoe = static_cast<unsigned>(year - era * 400);
  const unsigned doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return static_cast<uint32_t>(era * 146097 + static_cast<int>(doe) - 719468);
}

/* Parses the backend's ISO-8601 ``server_time`` (UTC, e.g. 2026-09-15T12:30:05Z
 * or with a +00:00 offset). Returns false when the string is not understood. */
bool parseServerTime(const char *iso, uint32_t &epochOut) {
  if (iso == nullptr || strlen(iso) < 19) return false;
  int year = 0, month = 0, day = 0, hour = 0, minute = 0, second = 0;
  if (sscanf(iso, "%4d-%2d-%2dT%2d:%2d:%2d", &year, &month, &day, &hour, &minute, &second) != 6) {
    return false;
  }
  if (month < 1 || month > 12 || day < 1 || day > 31) return false;
  epochOut = daysFromCivil(year, static_cast<unsigned>(month), static_cast<unsigned>(day)) * 86400UL +
             static_cast<uint32_t>(hour) * 3600UL + static_cast<uint32_t>(minute) * 60UL +
             static_cast<uint32_t>(second);
  return true;
}

/* ISO-8601 UTC string for the current reading, or an empty string when the
 * node has never learned the wall clock (the backend then adds the timestamp). */
String currentTimestampIso() {
  if (!clockSynced) return String();
  const uint32_t epoch = clockEpochAtAnchor + (millis() - clockAnchorMillis) / 1000UL;
  const uint32_t days = epoch / 86400UL;
  uint32_t rem = epoch % 86400UL;
  const uint8_t hour = rem / 3600UL;
  rem %= 3600UL;
  const uint8_t minute = rem / 60UL;
  const uint8_t second = rem % 60UL;

  /* inverse of daysFromCivil */
  int z = static_cast<int>(days) + 719468;
  const int era = (z >= 0 ? z : z - 146096) / 146097;
  const unsigned doe = static_cast<unsigned>(z - era * 146097);
  const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const int year = static_cast<int>(yoe) + era * 400;
  const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const unsigned mp = (5 * doy + 2) / 153;
  const unsigned day = doy - (153 * mp + 2) / 5 + 1;
  const unsigned month = mp + (mp < 10 ? 3 : -9);
  const int fullYear = year + (month <= 2);

  char buffer[24];
  snprintf(buffer, sizeof(buffer), "%04d-%02u-%02uT%02u:%02u:%02uZ", fullYear, month, day, hour, minute, second);
  return String(buffer);
}

void syncClockFrom(const char *serverTime) {
  uint32_t epoch = 0;
  if (!parseServerTime(serverTime, epoch)) return;
  clockEpochAtAnchor = epoch;
  clockAnchorMillis = millis();
  if (!clockSynced) logInfo("Clock synchronised with the backend server time");
  clockSynced = true;
}

/* -------------------------------------------------------------------------- */
/*  Sensor reads                                                              */
/* -------------------------------------------------------------------------- */

int readAdcAveraged(uint8_t pin, uint8_t samples = 8) {
  uint32_t total = 0;
  for (uint8_t i = 0; i < samples; i++) {
    total += analogRead(pin);
    delay(2);
  }
  return static_cast<int>(total / samples);
}

float mapFloat(float value, float inMin, float inMax, float outMin, float outMax) {
  if (inMax == inMin) return outMin;
  float result = (value - inMin) * (outMax - outMin) / (inMax - inMin) + outMin;
  if (result < outMin) result = outMin;
  if (result > outMax) result = outMax;
  return result;
}

float rainPercent(int raw) {
  /* High ADC = dry board, low ADC = wet: invert so 0 % = dry, 100 % = soaked. */
  return mapFloat(static_cast<float>(raw), RAIN_WET_ADC, RAIN_DRY_ADC, 100.0F, 0.0F);
}

float lightPercent(int raw) {
  return mapFloat(static_cast<float>(raw), LIGHT_DARK_ADC, LIGHT_BRIGHT_ADC, 0.0F, 100.0F);
}

const char *rainStatus(float percent) {
  if (percent < 10.0F) return "dry";
  if (percent < 40.0F) return "light rain";
  if (percent < 70.0F) return "rain";
  return "heavy rain";
}

const char *lightStatus(float percent) {
  if (percent < 15.0F) return "dark";
  if (percent < 45.0F) return "low";
  if (percent < 75.0F) return "medium";
  return "high";
}

const char *airQualityStatus(int raw) {
  /* Relative index against a clean-air baseline - the backend publishes the
   * authoritative index; this string is only used for the serial log and to
   * help spot a disconnected sensor (a floating pin reads near 0 or 1023). */
  if (raw <= 0 || raw >= ADC_MAX) return "disconnected";
  const float ratio = static_cast<float>(raw) / AIR_QUALITY_CLEAN_ADC;
  if (ratio < 1.25F) return "good";
  if (ratio < 1.8F) return "moderate";
  if (ratio < 2.6F) return "poor";
  return "very poor";
}

/* Reads temperature + humidity from whichever sensor config.h selected.
 *
 * Both branches discard anything outside the physical window instead of sending
 * it, and both set ``hasTempHum`` only when *both* values are usable - a
 * half-valid pair would let the backend compute a heat index from one real and
 * one stale number. */
void readTempHumidity() {
#if TEMP_HUMIDITY_SENSOR == SENSOR_AM2302_DHT22
  const float temperature = dht.readTemperature();
  const float humidity = dht.readHumidity();
#else
  /* DHT12 over I2C: 5 bytes starting at register 0x00 -
   *   [0] humidity integer   [1] humidity decimal (tenths)
   *   [2] temperature integer [3] temperature decimal, bit7 = negative sign
   *   [4] checksum = (0x00+0x01+0x02+0x03) & 0xFF
   * This is the DHT12's own protocol; decoding it as a DHT22 16-bit frame (as
   * happens if you point the Adafruit library at it) would be wrong. */
  float temperature = NAN;
  float humidity = NAN;
  Wire.beginTransmission(DHT12_ADDRESS);
  Wire.write(static_cast<uint8_t>(0x00));
  if (Wire.endTransmission(false) == 0 && Wire.requestFrom(DHT12_ADDRESS, 5) == 5) {
    uint8_t bytes[5];
    for (uint8_t i = 0; i < 5; i++) bytes[i] = static_cast<uint8_t>(Wire.read());
    const uint8_t checksum = static_cast<uint8_t>(bytes[0] + bytes[1] + bytes[2] + bytes[3]);
    if (bytes[4] == checksum) {
      humidity = bytes[0] + bytes[1] * 0.1F;
      temperature = bytes[2] + (bytes[3] & 0x7F) * 0.1F;
      if (bytes[3] & 0x80) temperature = -temperature; /* sign lives in byte 3 */
    } else {
      /* A non-zero checksum means the I2C read was corrupted; leave both values
       * NaN so the channel is reported missing rather than sending noise. */
      return;
    }
  } else {
    return;
  }
#endif

  const bool tempOk = !isnan(temperature) && temperature >= TEMP_MIN_C && temperature <= TEMP_MAX_C;
  const bool humidityOk = !isnan(humidity) && humidity >= HUMIDITY_MIN_PCT && humidity <= HUMIDITY_MAX_PCT;

  if (tempOk) sensors.temperatureC = temperature;
  if (humidityOk) sensors.humidityPct = humidity;
  sensors.hasTempHum = tempOk && humidityOk;
}

void readBmpSensor() {
  const float temperature = bmp.readTemperature();
  const float pressure = bmp.readPressure() / 100.0F; /* Pa -> hPa */

  const bool tempOk = !isnan(temperature) && temperature >= TEMP_MIN_C && temperature <= TEMP_MAX_C;
  const bool pressureOk = !isnan(pressure) && pressure >= PRESSURE_MIN_HPA && pressure <= PRESSURE_MAX_HPA;

  if (tempOk) sensors.bmpTemperatureC = temperature;
  if (pressureOk) sensors.pressureHpa = pressure;
  sensors.hasBmp = pressureOk; /* pressure is the reason the BMP280 is on the node */
}

/* A channel that reads a hard zero is treated as disconnected (floating input /
 * broken wiring). Full-scale is a valid value for a saturated LDR, so it is
 * kept - the backend calibrates the raw counts into engineering units. */
bool readAnalogSensor(uint8_t pin, int &rawOut, const char *name) {
  const int raw = readAdcAveraged(pin);
  if (raw <= 0) {
    logWarn(String("Analog channel '") + name + "' reads 0 - treated as not connected");
    return false;
  }
  rawOut = raw;
  return true;
}

void readAllSensors() {
  readTempHumidity();
  readBmpSensor();
  sensors.hasRain = readAnalogSensor(PIN_RAIN_ANALOG, sensors.rainRaw, "rain");
  sensors.hasLight = readAnalogSensor(PIN_LDR_ANALOG, sensors.lightRaw, "light");
  sensors.hasAir = readAnalogSensor(PIN_MQ135_ANALOG, sensors.airRaw, "air_quality");

  const bool anyOk = sensors.hasTempHum || sensors.hasBmp || sensors.hasRain || sensors.hasLight ||
                     sensors.hasAir;
  if (anyOk) {
    sensorFailures = 0;
  } else {
    sensorFailures++;
    logError(String("No sensor produced a valid reading (cycle ") + sensorFailures + " of " +
             SENSOR_FAILURE_LIMIT + ")");
  }
}

/* True when the payload would carry at least one real measurement. Transmitting
 * an empty payload would only earn an HTTP 422 from the backend. */
bool haveAnyReading() {
  return sensors.hasTempHum || sensors.hasBmp || sensors.hasRain || sensors.hasLight || sensors.hasAir;
}

/* -------------------------------------------------------------------------- */
/*  Payload                                                                   */
/* -------------------------------------------------------------------------- */

void buildPayload(JsonDocument &doc) {
  doc["device_id"] = DEVICE_ID;
  doc["firmware_version"] = FIRMWARE_VERSION;
  doc["sequence"] = sequence;
  doc["uptime_ms"] = millis();
  doc["transmission_interval_ms"] = SEND_INTERVAL_MS;
  doc["source"] = "arduino";

  /* Wi-Fi telemetry: lets the dashboard show link quality and IP. */
  if (WiFi.status() == WL_CONNECTED) {
    IPAddress ip = WiFi.localIP();
    char ipBuffer[16];
    snprintf(ipBuffer, sizeof(ipBuffer), "%u.%u.%u.%u", ip[0], ip[1], ip[2], ip[3]);
    doc["ip_address"] = ipBuffer;
    doc["rssi"] = WiFi.RSSI();
  }

  const String timestamp = currentTimestampIso();
  if (timestamp.length() > 0) doc["timestamp"] = timestamp;

  if (sensors.hasTempHum) {
    doc["temperature_c"] = serialized(String(sensors.temperatureC, 1));
    doc["humidity_pct"] = serialized(String(sensors.humidityPct, 1));
  }
  if (sensors.hasBmp) {
    doc["bmp_temperature_c"] = serialized(String(sensors.bmpTemperatureC, 1));
    doc["pressure_hpa"] = serialized(String(sensors.pressureHpa, 2));
  }
  if (sensors.hasRain) {
    doc["rain_raw"] = sensors.rainRaw;
    doc["rain_status"] = rainStatus(rainPercent(sensors.rainRaw));
  }
  if (sensors.hasLight) {
    doc["ldr_raw"] = sensors.lightRaw;
    doc["light_status"] = lightStatus(lightPercent(sensors.lightRaw));
  }
  if (sensors.hasAir) {
    doc["air_quality_raw"] = sensors.airRaw;
  }

  /* Explicit channel availability so the backend can distinguish "sensor
   * missing" from "value was zero". */
  JsonArray available = doc["sensors_available"].to<JsonArray>();
  JsonArray missing = doc["sensors_missing"].to<JsonArray>();
  if (sensors.hasTempHum) {
    available.add("temperature_c");
    available.add("humidity_pct");
  } else {
    missing.add("temperature_c");
    missing.add("humidity_pct");
  }
  if (sensors.hasBmp) {
    available.add("pressure_hpa");
    available.add("bmp_temperature_c");
  } else {
    missing.add("pressure_hpa");
    missing.add("bmp_temperature_c");
  }
  (sensors.hasRain ? available : missing).add("rain_raw");
  (sensors.hasLight ? available : missing).add("ldr_raw");
  (sensors.hasAir ? available : missing).add("air_quality_raw");
}

/* -------------------------------------------------------------------------- */
/*  HTTP                                                                      */
/* -------------------------------------------------------------------------- */

bool waitForWifi(uint32_t timeoutMs) {
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - started > timeoutMs) return false;
    delay(50);
  }
  return true;
}

/* Opens a TCP connection to the backend with a deadline. */
uint16_t backendConnectFailures = 0;

bool connectBackend() {
  if (WiFi.status() != WL_CONNECTED) return false;
  if (httpClient.connected()) return true;
  httpClient.setTimeout(HTTP_TIMEOUT_MS);
  if (!httpClient.connect(BACKEND_HOST, BACKEND_PORT)) {
    backendConnectFailures++;
    /* Log the first failure in full and then every tenth one: a node that has
     * been offline overnight must not fill the serial buffer with the same line
     * 5760 times, but the condition must stay visible. */
    if (backendConnectFailures == 1 || backendConnectFailures % 10 == 0) {
      char failureBuffer[192];
      snprintf(failureBuffer, sizeof(failureBuffer),
               "Cannot open TCP connection to %s:%d (failure %u). Check that BACKEND_HOST is "
               "the PC's LAN IP (never localhost/127.0.0.1), that both devices share one "
               "network, and that the firewall allows inbound TCP on that port.",
               BACKEND_HOST, BACKEND_PORT, static_cast<unsigned>(backendConnectFailures));
      logWarn(String(failureBuffer));
    }
    return false;
  }
  if (backendConnectFailures) {
    logInfo(String("Backend reachable again after ") + backendConnectFailures + " failures");
    backendConnectFailures = 0;
  }
  return true;
}

int contentLengthOf(const String &raw) {
  const int headerEnd = raw.indexOf("\r\n\r\n");
  if (headerEnd < 0) return -1;
  const String head = raw.substring(0, headerEnd);
  const int index = head.indexOf("Content-Length:");
  if (index < 0) return -1;
  return head.substring(index + 15).toInt();
}

/* Reads the whole response (status line + headers + body) into a bounded
 * String. Returns the HTTP status code, or 0 on timeout/transport failure.
 * The deadline guarantees this never blocks indefinitely, even if the backend
 * accepts the connection and then stalls. */
int readHttpResponse(String &bodyOut) {
  const uint32_t deadline = millis() + HTTP_TIMEOUT_MS;
  String raw;
  raw.reserve(1024);
  int headerEnd = -1;
  int expectedLength = -1;

  while (millis() < deadline) {
    while (httpClient.available()) {
      raw += static_cast<char>(httpClient.read());
      if (raw.length() >= 4096) break; /* payloads here are small; stay bounded */
    }
    if (headerEnd < 0) {
      headerEnd = raw.indexOf("\r\n\r\n");
      if (headerEnd >= 0) {
        headerEnd += 4;
        expectedLength = contentLengthOf(raw);
      }
    }
    const bool bodyComplete = headerEnd >= 0 && expectedLength >= 0 &&
                              static_cast<int>(raw.length()) - headerEnd >= expectedLength;
    if (bodyComplete) break;
    if (!httpClient.connected() && !httpClient.available()) break;
    delay(5);
  }
  httpClient.stop();

  if (raw.length() == 0) return 0;

  const int firstSpace = raw.indexOf(' ');
  if (firstSpace < 0) return 0;
  const int statusCode = raw.substring(firstSpace + 1, firstSpace + 4).toInt();

  const int separator = raw.indexOf("\r\n\r\n");
  bodyOut = (separator >= 0) ? raw.substring(separator + 4) : String();
  bodyOut.trim();
  return statusCode;
}

/* Applies the backend's risk-state fields to the LEDs/buzzer state. */
void applyRiskState(const JsonDocument &doc) {
  if (doc["risk_level"].is<int>()) {
    const int level = doc["risk_level"].as<int>();
    if (level >= 1 && level <= 5) {
      if (!haveRiskState || level != riskLevel) {
        logInfo(String("Risk level from backend: L") + level + " (" + doc["risk_label"].as<const char *>() +
                ", score " + doc["risk_score"].as<float>() + "/100)");
      }
      riskLevel = level;
    }
  }
  riskStale = doc["stale"].as<bool>();
  haveRiskState = true;
  activeAlerts = doc["alerts_active"] | 0;

  const char *pattern = doc["buzzer_pattern"] | "silent";
  if (strncmp(buzzerPattern, pattern, sizeof(buzzerPattern) - 1) != 0) {
    strncpy(buzzerPattern, pattern, sizeof(buzzerPattern) - 1);
    buzzerPattern[sizeof(buzzerPattern) - 1] = '\0';
    buzzerMode = modeFromPattern(buzzerPattern);
    buzzerStep = 0;
    buzzerCycleStart = millis();
    if (buzzerMode == BuzzerMode::Silent) {
      buzzerStop();
      buzzerOn = false;
    }
    logInfo(String("Buzzer pattern: ") + buzzerPattern);
  }
  syncClockFrom(doc["server_time"] | "");
}

/* POST one reading. Returns true when the backend accepted it. */
bool postReading() {
  JsonDocument doc;
  buildPayload(doc);
  String body;
  serializeJson(doc, body);

  if (!connectBackend()) return false;

  String request;
  request.reserve(512);
  request += "POST ";
  request += BACKEND_PATH;
  request += " HTTP/1.1\r\nHost: ";
  request += BACKEND_HOST;
  request += "\r\nContent-Type: application/json\r\n";
  request += "X-API-Key: ";
  request += API_KEY;
  request += "\r\nConnection: close\r\nContent-Length: ";
  request += body.length();
  request += "\r\n\r\n";
  request += body;

  const size_t written = httpClient.print(request);
  if (written != request.length()) {
    logWarn("Short write while sending the payload - retrying next cycle");
  }

  String responseBody;
  const int status = readHttpResponse(responseBody);

  if (status == 200) {
    JsonDocument response;
    if (deserializeJson(response, responseBody) == DeserializationError::Ok) {
      applyRiskStateFromIngestion(response);
    }
    return true;
  }
  if (status == 401 || status == 403) {
    /* Never log the key itself - only that it was rejected. */
    logError("Backend rejected the API key (HTTP " + String(status) + "). Check API_KEY vs backend/.env");
    return false;
  }
  if (status == 422) {
    logError("Backend rejected the payload (HTTP 422): " + responseBody);
    return false;
  }
  if (status == 0) {
    logWarn("No HTTP response within the timeout - payload not confirmed");
    return false;
  }
  logWarn("Backend returned HTTP " + String(status) + ": " + responseBody);
  return false;
}

/* The ingestion response carries risk_score/risk_level; use it directly so the
 * indicators update during the regular POST and the risk poll is only a top-up. */
void applyRiskStateFromIngestion(const JsonDocument &response) {
  const int level = response["risk_level"] | 0;
  if (level >= 1 && level <= 5) {
    riskLevel = level;
    haveRiskState = true;
    riskStale = false;
    if (!response["duplicate"].as<bool>()) {
      logInfo(String("Payload accepted (id ") + (response["reading_id"] | 0L) + ") - risk L" + level + " " +
              (response["risk_label"] | "") + " " + (response["risk_score"] | 0.0F) + "/100" +
              (response["warnings"].is<JsonArray>() && response["warnings"].size() > 0
                   ? String(" | ") + response["warnings"][0].as<const char *>()
                   : String()));
    }
  }
  syncClockFrom(response["server_time"] | "");
}

/* GET the compact risk state (LEDs + buzzer) so the physical indicators stay in
 * step even when the node is not the one producing readings. */
void pollRiskState() {
  if (!connectBackend()) return;

  char path[96];
  snprintf(path, sizeof(path), RISK_STATE_PATH, DEVICE_ID);

  String request;
  request.reserve(256);
  request += "GET ";
  request += path;
  request += " HTTP/1.1\r\nHost: ";
  request += BACKEND_HOST;
  request += "\r\nX-API-Key: ";
  request += API_KEY;
  request += "\r\nConnection: close\r\n\r\n";
  httpClient.print(request);

  String responseBody;
  const int status = readHttpResponse(responseBody);
  if (status != 200) {
    if (status != 0) logWarn("Risk-state poll returned HTTP " + String(status));
    return;
  }

  JsonDocument doc;
  if (deserializeJson(doc, responseBody) != DeserializationError::Ok) {
    logWarn("Risk-state response was not valid JSON");
    return;
  }
  applyRiskState(doc);
}

/* -------------------------------------------------------------------------- */
/*  Indicators (5 LEDs + buzzer)                                              */
/* -------------------------------------------------------------------------- */

void writeLed(uint8_t index, bool on) {
  const uint8_t pin = LED_PINS[index];
#if LED_ACTIVE_HIGH
  digitalWrite(pin, on ? HIGH : LOW);
#else
  digitalWrite(pin, on ? LOW : HIGH);
#endif
}

void allLedsOff() {
  for (uint8_t i = 0; i < 5; i++) writeLed(i, false);
}

/* LED N lights up with the backend's level; LEDs above the level stay dark.
 * When the backend cannot be reached the pattern blinks so the state is
 * unmistakably "not current" rather than a stale solid reading. */
void updateLeds() {
  static uint32_t lastBlink = 0;
  static bool blinkOn = false;

  if (!haveRiskState) {
    /* No assessment yet: LED 1 pulses slowly to show the node is alive but has
     * no risk verdict, and nothing else is lit. */
    const bool on = (millis() / 750UL) % 2UL == 0UL;
    allLedsOff();
    writeLed(0, on);
    return;
  }

  const bool connectionLost = WiFi.status() != WL_CONNECTED;

  if (riskStale || connectionLost) {
    if (millis() - lastBlink > 400UL) {
      lastBlink = millis();
      blinkOn = !blinkOn;
    }
    allLedsOff();
    if (blinkOn) {
      for (uint8_t i = 0; i < static_cast<uint8_t>(riskLevel) && i < 5; i++) writeLed(i, true);
    }
    return;
  }

  for (uint8_t i = 0; i < 5; i++) writeLed(i, i < static_cast<uint8_t>(riskLevel));
}

/* Non-blocking patterns. Level 1/2 are silent, level 3 beeps once a minute,
 * level 4 twice every 30 s and level 5 loops a critical alarm. */
void updateBuzzer() {
  const uint32_t now = millis();

  if (buzzerMode == BuzzerMode::Silent) {
    if (buzzerOn) {
      buzzerStop();
      buzzerOn = false;
    }
    return;
  }

  const uint16_t cycleMs = (buzzerMode == BuzzerMode::SingleShort) ? 60000U
                          : (buzzerMode == BuzzerMode::DoubleShort) ? 30000U
                                                                    : 6000U;
  const uint16_t beepMs = (buzzerMode == BuzzerMode::CriticalAlarm) ? 350U : 120U;
  const uint8_t beepsPerCycle = (buzzerMode == BuzzerMode::SingleShort) ? 1
                               : (buzzerMode == BuzzerMode::DoubleShort) ? 2
                                                                          : 3;

  if (now - buzzerCycleStart >= cycleMs) {
    buzzerCycleStart = now;
    buzzerStep = 0;
    buzzerStepStart = now;
  }

  const uint16_t gapMs = 250U;
  const uint32_t stepDuration = (buzzerStep % 2U == 0U) ? beepMs : gapMs;

  if (now - buzzerStepStart >= stepDuration) {
    buzzerStepStart = now;
    buzzerStep++;
    if (buzzerStep >= static_cast<uint8_t>(beepsPerCycle * 2U)) {
      buzzerStep = 0;
      if (buzzerOn) {
        buzzerStop();
        buzzerOn = false;
      }
      return;
    }
  }

  const bool shouldSound = (buzzerStep % 2U == 0U);
  if (shouldSound && !buzzerOn) {
    buzzerStart();
    buzzerOn = true;
  } else if (!shouldSound && buzzerOn) {
    buzzerStop();
    buzzerOn = false;
  }
}

/* -------------------------------------------------------------------------- */
/*  Wi-Fi                                                                     */
/* -------------------------------------------------------------------------- */

/* Non-blocking Wi-Fi association state machine.
 *
 * Calling WiFi.begin() again on every loop pass is a classic WiFiS3 bug: each
 * call restarts the association attempt, so the radio never gets the several
 * seconds it needs and the node stays offline forever. Instead we start an
 * attempt, then only poll; a new attempt is made only after
 * WIFI_ASSOC_TIMEOUT_MS has elapsed without success, or after a drop. */
uint32_t wifiAttemptStartedAt = 0;
bool wifiAttemptInFlight = false;

void logWifiAddress() {
  IPAddress ip = WiFi.localIP();
  char ipBuffer[16];
  snprintf(ipBuffer, sizeof(ipBuffer), "%u.%u.%u.%u", ip[0], ip[1], ip[2], ip[3]);
  logInfo(String("Wi-Fi connected. IP ") + ipBuffer + " RSSI " + WiFi.RSSI() + " dBm");
  logInfo(String("Posting to http://") + BACKEND_HOST + ":" + BACKEND_PORT + BACKEND_PATH);
}

/* Starts one association attempt. Returns immediately; the caller polls. */
void startWifiAttempt() {
  logInfo("Connecting to Wi-Fi '" WIFI_SSID "' ...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  wifiAttemptStartedAt = millis();
  lastWifiAttemptAt = wifiAttemptStartedAt;
  wifiAttemptInFlight = true;
}

void connectWifi() {
  const uint32_t now = millis();

  if (WiFi.status() == WL_CONNECTED) {
    if (wifiAttemptInFlight || wifiDownSince != 0) logWifiAddress();
    wifiDownSince = 0;
    wifiAttemptInFlight = false;
    return;
  }

  if (wifiDownSince == 0) wifiDownSince = now;

  if (wifiAttemptInFlight) {
    if (now - wifiAttemptStartedAt < WIFI_ASSOC_TIMEOUT_MS) return; /* keep waiting */
    logWarn(String("Wi-Fi association timed out after ") + (WIFI_ASSOC_TIMEOUT_MS / 1000UL) +
            " s (status " + String(WiFi.status()) + ") - restarting the attempt");
    wifiAttemptInFlight = false;
    WiFi.disconnect();
  }

  if (now - lastWifiAttemptAt < WIFI_RETRY_INTERVAL_MS) return;
  startWifiAttempt();
}

}  // namespace

/* -------------------------------------------------------------------------- */
/*  setup / loop                                                              */
/* -------------------------------------------------------------------------- */

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(200);
  Serial.println();
  Serial.println(F("====================================================="));
  Serial.println(F(" Environmental Intelligence Platform - Arduino UNO R4"));
  Serial.println(F("====================================================="));

#ifdef USING_TEMPLATE_CONFIG
  Serial.println(F("!! Using config.example.h - create config.h with YOUR"));
  Serial.println(F("!! Wi-Fi credentials and API key before flashing."));
#endif

  for (uint8_t i = 0; i < 5; i++) {
    pinMode(LED_PINS[i], OUTPUT);
    writeLed(i, false);
  }
  pinMode(PIN_BUZZER, OUTPUT);
  buzzerStop();

  /* Lamp test: proves every LED and the buzzer are wired correctly. It lights
   * the LEDs one at a time (each is switched off before the next comes on) so a
   * shorted pair is obvious rather than hidden behind the cumulative display
   * used during normal operation. */
  for (uint8_t i = 0; i < 5; i++) {
    allLedsOff();
    writeLed(i, true);
    delay(120);
  }
  allLedsOff();
  buzzerStart();
  delay(150);
  buzzerStop();
  delay(50);

#if TEMP_HUMIDITY_SENSOR == SENSOR_AM2302_DHT22
  {
    dht.begin();
    char sensorBuffer[96];
    snprintf(sensorBuffer, sizeof(sensorBuffer),
             "Temperature/humidity sensor: AM2302/DHT22 on D%d (one-wire, DHT22 frame)",
             PIN_DHT);
    logInfo(String(sensorBuffer));
  }
#else
  {
    char sensorBuffer[96];
    snprintf(sensorBuffer, sizeof(sensorBuffer),
             "Temperature/humidity sensor: DHT12 on I2C address 0x%02X (SDA/SCL)",
             DHT12_I2C_ADDRESS);
    logInfo(String(sensorBuffer));
  }
#endif

  Wire.begin();
#if TEMP_HUMIDITY_SENSOR == SENSOR_DHT12_I2C
  /* Fail loudly at boot: a DHT12 that does not answer on the bus is a wiring
   * problem, and silently reporting "no temperature" for hours is worse. */
  Wire.beginTransmission(DHT12_ADDRESS);
  if (Wire.endTransmission() != 0) {
    logError("DHT12 did not acknowledge on the I2C bus - check SDA/SCL and the 3V3 supply");
  }
#endif
  if (bmp.begin(BMP280_I2C_ADDRESS)) {
    /* Indoor monitoring: local pressure is what matters, not sea-level. */
    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                    Adafruit_BMP280::SAMPLING_X2,   /* temperature oversampling */
                    Adafruit_BMP280::SAMPLING_X16,  /* pressure oversampling    */
                    Adafruit_BMP280::FILTER_X16,
                    Adafruit_BMP280::STANDBY_MS_500);
    logInfo("BMP280 initialised");
  } else {
    logError("BMP280 not found on the I2C bus - check SDA/SCL and the address jumper");
  }

  analogReadResolution(10); /* 0..1023, matching the backend calibration */

  /* Report the pin map once at boot: this is the wiring the firmware actually
   * compiled with, so bench bring-up is a matter of comparing two lines instead
   * of reading the sketch. A0 is 14 on the UNO R4, so the channel is printed as
   * A0/A1/A2 the way the wiring table names it. */
  {
    char pinBuffer[128];
    snprintf(pinBuffer, sizeof(pinBuffer),
             "Pin map: rain=A%d light=A%d air=A%d LEDs=D%d/D%d/D%d/D%d/D%d buzzer=D%d %s",
             PIN_RAIN_ANALOG - A0, PIN_LDR_ANALOG - A0, PIN_MQ135_ANALOG - A0, PIN_LED_1,
             PIN_LED_2, PIN_LED_3, PIN_LED_4, PIN_LED_5, PIN_BUZZER,
             LED_ACTIVE_HIGH ? "(LEDs active-high)" : "(LEDs active-low)");
    logInfo(String(pinBuffer));
  }

  /* One bounded attempt at boot so the first reading can be posted promptly;
   * the non-blocking state machine in the main loop owns it from then on. */
  startWifiAttempt();
  if (waitForWifi(8000)) {
    logWifiAddress();
    wifiAttemptInFlight = false;
  } else {
    logWarn("Wi-Fi unavailable at boot - the main loop keeps retrying");
  }

  /* First sample immediately so the dashboard is live within seconds. */
  readAllSensors();
  lastSendAt = millis() - SEND_INTERVAL_MS;
  lastRiskPollAt = millis() - RISK_POLL_INTERVAL_MS;
}

void loop() {
  connectWifi();

  /* Keep the physical indicators responsive every pass. */
  updateLeds();
  updateBuzzer();

  const uint32_t now = millis();

  if (now - lastSendAt >= SEND_INTERVAL_MS) {
    lastSendAt = now;
    readAllSensors();

    if (!haveAnyReading()) {
      /* Nothing usable came back: an empty payload would only be rejected with
       * HTTP 422, so the node stays quiet and says exactly what is wrong. */
      logError(String("Skipping transmission: no valid sensor readings this cycle (failure ") +
               sensorFailures + " of " + SENSOR_FAILURE_LIMIT + ")");
      if (sensorFailures >= SENSOR_FAILURE_LIMIT) {
        logError("Check sensor power and wiring: every channel has been unavailable for " +
                 String(SENSOR_FAILURE_LIMIT) + " consecutive cycles");
      }
    } else {
      sequence++;
      if (postReading()) {
        successfulPosts++;
      } else {
        failedPosts++;
      }
    }
  }

  if (now - lastRiskPollAt >= RISK_POLL_INTERVAL_MS) {
    lastRiskPollAt = now;
    pollRiskState();
  }

  /* A brief status line every ~30 s keeps long serial sessions useful. */
  static uint32_t lastStatusAt = 0;
  if (millis() - lastStatusAt >= 30000UL) {
    lastStatusAt = millis();
    String status = String("wifi=") + (WiFi.status() == WL_CONNECTED ? "up" : "down") +
                    " posts=" + successfulPosts + " failed=" + failedPosts +
                    " risk=L" + (haveRiskState ? String(riskLevel) : String("?")) +
                    " pattern=" + buzzerPattern +
                    " stale=" + (riskStale ? "yes" : "no") +
                    " alerts=" + activeAlerts;
    logInfo(status);
  }

  delay(20); /* yield to the Wi-Fi stack; the loop is otherwise non-blocking */
}
