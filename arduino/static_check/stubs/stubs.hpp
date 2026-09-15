/* ============================================================================
 *  Host-side API stubs for static compilation of the firmware
 * ============================================================================
 *
 *  WHAT THIS IS
 *    A minimal but signature-faithful model of the Arduino APIs the sketch
 *    uses (Arduino core, WiFiS3, Wire, ArduinoJson >= 7, Adafruit_BMP280,
 *    DHT). It exists so that `environmental_monitor.ino` can be compiled by a
 *    normal C++ compiler on a PC, which catches the class of defects that
 *    would otherwise only appear in the Arduino IDE:
 *
 *      * syntax errors and typos
 *      * wrong member names / wrong argument counts / wrong types
 *      * missing declarations and shadowing problems
 *      * pin-map conflicts (the sketch's static_asserts either pass or fail)
 *      * -Wall -Wextra diagnostics (unused variables, sign compare, ...)
 *
 *  WHAT THIS IS NOT
 *    It is NOT a simulation and it is NOT hardware validation. Nothing here
 *    reads a sensor, drives a pin or opens a socket; every function is a stub
 *    that either returns a constant or does nothing. It cannot prove that the
 *    firmware works on an UNO R4 WiFi, and it deliberately does not try to -
 *    see arduino/README.md for what still requires the real toolchain.
 *
 *  The stubs are intentionally *strict*: they do not accept implicit
 *  conversions the real libraries would reject, so a compile here is
 *  meaningful, and a failure here is a real defect in the sketch.
 * ============================================================================ */

#ifndef ENVMON_HOST_STUBS_HPP
#define ENVMON_HOST_STUBS_HPP

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>

/* ---------------------------------------------------------------- Arduino -- */
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1

#define A0 14
#define A1 15
#define A2 16
#define A3 17
#define A4 18
#define A5 19

#define WL_CONNECTED 3
#define WL_IDLE_STATUS 0

typedef uint8_t byte;

inline unsigned long millis() { return 0; }
inline void delay(unsigned long) {}
inline void delayMicroseconds(unsigned int) {}
inline void pinMode(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t, uint8_t) {}
inline int digitalRead(uint8_t) { return LOW; }
inline int analogRead(uint8_t) { return 0; }
inline void analogReadResolution(int) {}
inline void tone(uint8_t, unsigned int) {}
inline void tone(uint8_t, unsigned int, unsigned long) {}
inline void noTone(uint8_t) {}

#define F(x) (x)
#define PROGMEM

/* ------------------------------------------------------------------ String - */
class String {
 public:
  String() {}
  String(const char *s) : _data(s ? s : "") {}
  String(char c) : _data(1, c) {}
  String(int v) { char b[24]; snprintf(b, sizeof(b), "%d", v); _data = b; }
  String(unsigned int v) { char b[24]; snprintf(b, sizeof(b), "%u", v); _data = b; }
  String(long v) { char b[24]; snprintf(b, sizeof(b), "%ld", v); _data = b; }
  String(unsigned long v) { char b[24]; snprintf(b, sizeof(b), "%lu", v); _data = b; }
  /* Arduino's String has exact float *and* double constructors; keeping both is
   * what makes String(1.5f) unambiguous, so the stub mirrors that. */
  String(float v, int decimals = 2) {
    char b[32];
    snprintf(b, sizeof(b), "%.*f", decimals, static_cast<double>(v));
    _data = b;
  }
  String(double v, int decimals = 2) {
    char b[32];
    snprintf(b, sizeof(b), "%.*f", decimals, v);
    _data = b;
  }

  const char *c_str() const { return _data.c_str(); }
  unsigned int length() const { return static_cast<unsigned int>(_data.size()); }
  void reserve(unsigned int) {}
  void trim() {}
  int toInt() const { return atoi(_data.c_str()); }

  int indexOf(const char *needle) const {
    const size_t pos = _data.find(needle);
    return pos == std::string::npos ? -1 : static_cast<int>(pos);
  }
  int indexOf(char needle) const { return indexOf(std::string(1, needle).c_str()); }
  String substring(unsigned int from) const {
    return String(_data.substr(from).c_str());
  }
  String substring(unsigned int from, unsigned int to) const {
    if (to <= from) return String("");
    return String(_data.substr(from, to - from).c_str());
  }

  bool operator==(const String &other) const { return _data == other._data; }
  bool operator!=(const String &other) const { return !(*this == other); }
  char operator[](unsigned int i) const { return _data[i]; }

  /* The real String defines an overload for each of these exact types; without
   * the complete set, integral arguments are ambiguous, so the stub does too. */
  String &operator+=(const String &other) { _data += other._data; return *this; }
  String &operator+=(const char *other) { _data += other; return *this; }
  String &operator+=(char other) { _data += other; return *this; }
  String &operator+=(unsigned char other) { _data += String(other)._data; return *this; }
  String &operator+=(int other) { _data += String(other)._data; return *this; }
  String &operator+=(unsigned int other) { _data += String(other)._data; return *this; }
  String &operator+=(long other) { _data += String(other)._data; return *this; }
  String &operator+=(unsigned long other) { _data += String(other)._data; return *this; }
  String &operator+=(float other) { _data += String(other)._data; return *this; }
  String &operator+=(double other) { _data += String(other)._data; return *this; }

  /* The real String class is copiable and movable; code relies on both. */
  String(const String &) = default;
  String &operator=(const String &) = default;

  friend String operator+(const String &lhs, const String &rhs) {
    String out(lhs);
    out += rhs;
    return out;
  }

 private:
  std::string _data;
};

inline String operator+(const String &lhs, const char *rhs) {
  String out(lhs);
  out += rhs;
  return out;
}
inline String operator+(const char *lhs, const String &rhs) {
  String out(lhs);
  out += rhs;
  return out;
}
inline String operator+(const String &lhs, char rhs) {
  String out(lhs);
  out += rhs;
  return out;
}
inline String operator+(const String &lhs, int rhs) {
  String out(lhs);
  out += rhs;
  return out;
}
inline String operator+(const String &lhs, unsigned int rhs) {
  String out(lhs);
  out += String(rhs);
  return out;
}
inline String operator+(const String &lhs, unsigned long rhs) {
  String out(lhs);
  out += rhs;
  return out;
}
inline String operator+(const String &lhs, long rhs) {
  String out(lhs);
  out += rhs;
  return out;
}
inline String operator+(const String &lhs, float rhs) {
  String out(lhs);
  out += String(rhs);
  return out;
}
inline String operator+(const String &lhs, double rhs) {
  String out(lhs);
  out += String(rhs);
  return out;
}
inline String operator+(int lhs, const String &rhs) {
  String out(lhs);
  out += rhs;
  return out;
}
inline String operator+(unsigned long lhs, const String &rhs) {
  String out(lhs);
  out += rhs;
  return out;
}

/* ------------------------------------------------------------------ Serial - */
class HostSerial {
 public:
  void begin(unsigned long) {}
  void print(const String &) {}
  void print(const char *) {}
  void print(char) {}
  void print(int) {}
  void print(unsigned int) {}
  void print(long) {}
  void print(unsigned long) {}
  void print(double, int = 2) {}
  void println() {}
  void println(const String &) {}
  void println(const char *) {}
  void println(char) {}
  void println(int) {}
  void println(unsigned int) {}
  void println(long) {}
  void println(unsigned long) {}
  void println(double, int = 2) {}
  operator bool() const { return true; }
};
extern HostSerial Serial;

/* -------------------------------------------------------------- IPAddress -- */
class IPAddress {
 public:
  uint8_t operator[](int index) const { return _octets[index & 3]; }
  operator uint32_t() const { return 0; }

 private:
  uint8_t _octets[4] = {0, 0, 0, 0};
};

/* -------------------------------------------------------------- WiFiClient - */
class WiFiClient {
 public:
  int connect(const char *host, uint16_t port) { (void)host; (void)port; return 1; }
  int connect(IPAddress ip, uint16_t port) { (void)ip; (void)port; return 1; }
  void setTimeout(unsigned long) {}
  bool connected() { return true; }
  int available() { return 0; }
  int read() { return -1; }
  size_t print(const String &) { return 1; }
  size_t print(const char *) { return 1; }
  size_t print(char) { return 1; }
  size_t write(const uint8_t *, size_t) { return 1; }
  void flush() {}
  void stop() {}
  operator bool() const { return true; }
};

/* ------------------------------------------------------------------- WiFi -- */
class HostWiFi {
 public:
  int begin(const char *ssid, const char *password) {
    (void)ssid; (void)password; return WL_CONNECTED;
  }
  int status() { return WL_CONNECTED; }
  IPAddress localIP() { return IPAddress(); }
  int RSSI() { return -55; }
  void disconnect() {}
  void setTimeout(unsigned long) {}
};
extern HostWiFi WiFi;

/* ------------------------------------------------------------------- Wire -- */
class HostWire {
 public:
  void begin() {}
  void beginTransmission(uint8_t) {}
  size_t write(uint8_t) { return 1; }
  uint8_t endTransmission() { return 0; }
  uint8_t endTransmission(bool) { return 0; }
  uint8_t requestFrom(uint8_t, uint8_t count) { return count; }
  int read() { return 0; }
};
extern HostWire Wire;

/* -------------------------------------------------------------- ArduinoJson */
/* A strict-but-faithful model of the JsonDocument surface the sketch touches.
 * It is NOT a JSON parser: serializeJson/deserializeJson only satisfy the type
 * checker. Semantics of the payload are covered by the backend test suite. */
namespace ArduinoJson {

struct JsonArray;

/* Serialized<T> is what ArduinoJson returns from serialized(String) to avoid a
 * quoted string. Its only job here is to be a distinguishable assignment type. */
template <typename T>
struct SerializedValue {
  explicit SerializedValue(const T &v) : value(v) {}
  T value;
};
template <typename T>
SerializedValue<T> serialized(const T &value) {
  return SerializedValue<T>(value);
}

struct JsonVariantConst {
  template <typename T>
  bool is() const { return true; }
  template <typename T>
  T as() const { return T(); }
  size_t size() const { return 0; }
  bool isNull() const { return true; }
  JsonVariantConst operator[](size_t) const { return JsonVariantConst(); }
  template <typename T>
  T operator|(const T &fallback) const { return fallback; }
  const char *operator|(const char *fallback) const { return fallback; }
};

struct JsonVariant {
  JsonVariant() {}

  template <typename T>
  bool is() const { return true; }
  template <typename T>
  T as() const { return T(); }
  template <typename T>
  T as_or() const { return T(); }

  size_t size() const { return 0; }
  bool isNull() const { return true; }

  JsonArray toJsonArray() const;

  /* ArduinoJson 7: ``variant.to<JsonArray>()`` builds the array in place. */
  template <typename T>
  T to() const {
    return T();
  }

  JsonVariantConst operator[](size_t) const { return JsonVariantConst(); }

  JsonVariant operator[](const char *) { return JsonVariant(); }
  JsonVariantConst operator[](const char *) const { return JsonVariantConst(); }

  template <typename T>
  JsonVariant &operator=(const T &) { return *this; }

  /* ``doc["key"] | fallback`` (ArduinoJson's default-value operator). */
  template <typename T>
  T operator|(const T &fallback) const { return fallback; }
  const char *operator|(const char *fallback) const { return fallback; }

  /* Truthiness, used as ``if (!response["duplicate"].as<bool>())`` only via as<>(). */
  explicit operator bool() const { return false; }
};

struct JsonArray {
  size_t size() const { return 0; }
  void add(const char *) {}
  void add(int) {}
  void add(unsigned int) {}
  void add(long) {}
  void add(unsigned long) {}
  void add(double) {}
  void add(bool) {}
  JsonVariant operator[](size_t) const { return JsonVariant(); }
  bool isNull() const { return false; }
};

inline JsonArray JsonVariant::toJsonArray() const { return JsonArray(); }

struct JsonObject {
  JsonVariant operator[](const char *) const { return JsonVariant(); }
};

class JsonDocument {
 public:
  JsonVariant operator[](const char *) { return JsonVariant(); }
  JsonVariantConst operator[](const char *) const { return JsonVariantConst(); }
  bool isNull() const { return false; }
  size_t size() const { return 0; }

  template <typename T>
  T to() const {
    return T();
  }
};

enum class DeserializationErrorCode { Ok, EmptyInput, IncompleteInput, InvalidInput };

class DeserializationError {
 public:
  DeserializationError() : _code(DeserializationErrorCode::Ok) {}
  explicit DeserializationError(DeserializationErrorCode code) : _code(code) {}
  DeserializationErrorCode code() const { return _code; }
  const char *c_str() const { return "Ok"; }
  explicit operator bool() const { return _code != DeserializationErrorCode::Ok; }
  bool operator==(DeserializationErrorCode other) const { return _code == other; }
  bool operator!=(DeserializationErrorCode other) const { return _code != other; }
  static const DeserializationErrorCode Ok = DeserializationErrorCode::Ok;

 private:
  DeserializationErrorCode _code;
};

}  // namespace ArduinoJson

/* ``JsonDocument doc;`` / ``JsonArray`` / ``serialized`` used unqualified. */
using ArduinoJson::JsonArray;
using ArduinoJson::JsonDocument;
using ArduinoJson::JsonObject;
using ArduinoJson::DeserializationError;
using ArduinoJson::serialized;

inline size_t serializeJson(const JsonDocument &, String &) { return 1; }
inline void serializeJson(const JsonDocument &, char *, size_t) {}
inline DeserializationError deserializeJson(JsonDocument &, const String &) {
  return DeserializationError();
}
inline DeserializationError deserializeJson(JsonDocument &, const char *) {
  return DeserializationError();
}

/* --------------------------------------------------------- Adafruit_BMP280 - */
class Adafruit_BMP280 {
 public:
  enum sensor_mode { MODE_SLEEP, MODE_FORCED, MODE_NORMAL };
  enum sensor_sampling {
    SAMPLING_NONE,
    SAMPLING_X1,
    SAMPLING_X2,
    SAMPLING_X4,
    SAMPLING_X8,
    SAMPLING_X16
  };
  enum sensor_filter {
    FILTER_OFF,
    FILTER_X2,
    FILTER_X4,
    FILTER_X8,
    FILTER_X16
  };
  enum standby_duration {
    STANDBY_MS_0_5,
    STANDBY_MS_10,
    STANDBY_MS_20,
    STANDBY_MS_62_5,
    STANDBY_MS_125,
    STANDBY_MS_250,
    STANDBY_MS_500,
    STANDBY_MS_1000
  };

  bool begin(uint8_t addr = 0x77, uint8_t chipid = 0x58) {
    (void)addr; (void)chipid; return true;
  }
  void setSampling(sensor_mode, sensor_sampling, sensor_sampling, sensor_filter,
                   standby_duration) {}
  float readTemperature() { return 25.0f; }
  float readPressure() { return 101325.0f; }
  float readAltitude(float) { return 0.0f; }
};

/* --------------------------------------------------------------------- DHT - */
#define DHT11 11
#define DHT22 22
#define DHT21 21
#define AM2301 21

class DHT {
 public:
  DHT(uint8_t pin, uint8_t type) { (void)pin; (void)type; }
  void begin() {}
  float readTemperature(bool force = false) { (void)force; return 25.0f; }
  float readHumidity(bool force = false) { (void)force; return 50.0f; }
  void setWaitForReading(bool) {}
};

#endif /* ENVMON_HOST_STUBS_HPP */
