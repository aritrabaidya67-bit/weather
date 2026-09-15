/*
 * config.example.h - firmware configuration TEMPLATE
 * ---------------------------------------------------------------------------
 * Copy this file to `config.h` and fill in your own values:
 *
 *     cp config.example.h config.h
 *
 * `config.h` is git-ignored on purpose: it holds your Wi-Fi password and the
 * device API key, and those must never end up in version control.
 *
 * Every value below can be changed without touching the firmware logic.
 */
#ifndef ENVMON_CONFIG_H
#define ENVMON_CONFIG_H

/* ------------------------------------------------------------------ Wi-Fi -- */
/* The network the node and the backend share (a phone hotspot works fine). */
#define WIFI_SSID "YOUR_WIFI_OR_HOTSPOT_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

/* ---------------------------------------------------------------- backend -- */
/* LAN/hotspot IPv4 address of the machine running FastAPI.
 * NEVER "localhost" or "127.0.0.1": from the Arduino those mean the Arduino. */
#define BACKEND_HOST "192.168.1.50"
#define BACKEND_PORT 8000
#define BACKEND_PATH "/api/v1/sensors/data"
#define RISK_STATE_PATH "/api/v1/device/%s/risk-state"

/* Must equal API_KEY in backend/.env. Keep it out of source control. */
#define API_KEY "replace_with_the_same_key_as_backend_env"

/* Identifies this node in the database; must match DEVICE_ID in backend/.env. */
#define DEVICE_ID "arduino-r4-wifi-01"
#define FIRMWARE_VERSION "1.0.0"

/* ------------------------------------------------------------------ timing -- */
#define SEND_INTERVAL_MS 15000UL   /* POST a reading every 15 s                  */
#define RISK_POLL_INTERVAL_MS 15000UL /* poll LEDs/buzzer state every 15 s       */
#define WIFI_RETRY_INTERVAL_MS 5000UL /* minimum delay between reconnect attempts   */
/* How long one association attempt is given before it is abandoned and
 * restarted. Must be long enough for DHCP: restarting too eagerly is the most
 * common reason an UNO R4 never comes online. */
#define WIFI_ASSOC_TIMEOUT_MS 20000UL
#define HTTP_TIMEOUT_MS 6000UL     /* socket read/write timeout                  */
#define SERIAL_BAUD 115200

/* ============================================================================
 * TEMPERATURE / HUMIDITY SENSOR SELECTION - read this before wiring anything
 * ============================================================================
 * Only *one* of these can be enabled. The two sensors do NOT speak the same
 * protocol and they are NOT interchangeable:
 *
 *  SENSOR_AM2302_DHT22 (default)
 *      Aosong AM2302 / DHT22. One-wire single-bus, DHT22 frame (16-bit
 *      humidity, 16-bit signed temperature), 1 ms wake-up, 0.1 C / 0.1 %RH
 *      resolution, -40..80 C. Read with the Adafruit DHT library.
 *
 *  SENSOR_DHT12_I2C
 *      Aosong DHT12 wired in its **I2C** mode (fixed address 0x5C,
 *      SDA/SCL). 5-byte frame: humidity integer, humidity decimal,
 *      temperature integer, temperature decimal, checksum. Read directly on
 *      the I2C bus; the Adafruit DHT library is not used at all.
 *
 * DELIBERATELY NOT SUPPORTED: a DHT12 on a one-wire pin. A DHT12 in one-wire
 * mode uses the DHT11-style frame (integer + decimal bytes) and an ~18 ms
 * wake-up, which is a different protocol from the AM2302/DHT22 frame. Feeding
 * it to the Adafruit library as DHT22 would decode garbage (e.g. a plausible
 * 24 C / 52 %RH reading turning into "humidity 1331.8 %"), so this firmware
 * refuses the combination instead of pretending the two are equivalent.
 * If you have a DHT12, wire it to SDA/SCL and select SENSOR_DHT12_I2C.
 * ============================================================================ */
#define SENSOR_AM2302_DHT22 1
#define SENSOR_DHT12_I2C 2

#define TEMP_HUMIDITY_SENSOR SENSOR_AM2302_DHT22

/* --------------------------------------------------------------- pin map --- */
/* ONE-WIRE DATA LINE for AM2302/DHT22: Arduino pin D2 (= PIN_DHT).
 * Needs a 10 kOhm pull-up from DATA to 3V3. Only used when
 * TEMP_HUMIDITY_SENSOR == SENSOR_AM2302_DHT22. */
#define PIN_DHT 2
/* Protocol constant handed to the Adafruit DHT library. Correct for the
 * AM2302/DHT22 only; see the selection block above. */
#define DHT_TYPE DHT22

/* Fixed I2C address of the DHT12. Only used when
 * TEMP_HUMIDITY_SENSOR == SENSOR_DHT12_I2C. */
#define DHT12_I2C_ADDRESS 0x5C

#define PIN_RAIN_ANALOG A0  /* rain sensor analog output (LM393 board AO) */
#define PIN_LDR_ANALOG A1   /* LDR divider (GL5528 + 10 kOhm)              */
#define PIN_MQ135_ANALOG A2 /* MQ-135 analog output (after 24 h burn-in)   */

/* BMP280 uses the default I2C pins (SDA/SCL) on the UNO R4 WiFi. */
#define BMP280_I2C_ADDRESS 0x76 /* 0x77 when the SDO pin is tied high */

/* Five risk LEDs: index 0 = level 1 ... index 4 = level 5. */
#define PIN_LED_1 3
#define PIN_LED_2 4
#define PIN_LED_3 5
#define PIN_LED_4 6
#define PIN_LED_5 7
#define LED_ACTIVE_HIGH 1   /* set 0 for active-low wiring */

/* Buzzer on D8.
 *   BUZZER_PASSIVE 1 -> passive piezo element, driven with tone() at
 *                       BUZZER_FREQUENCY_HZ (it has no oscillator of its own,
 *                       so a plain HIGH would be silent).
 *   BUZZER_PASSIVE 0 -> active buzzer module with its own oscillator; driven
 *                       with a plain HIGH/LOW, which on some modules is louder
 *                       and on all of them is more reliable than tone().
 * Either way the pattern player is non-blocking and silence is exact. */
#define PIN_BUZZER 8
#define BUZZER_PASSIVE 1
#define BUZZER_FREQUENCY_HZ 2300

/* --------------------------------------------------------- calibration ----- */
/* These MUST match the backend's SensorConfig so both sides agree on what a
 * raw ADC count means:
 *   backend/app/core/config.py -> rain_dry_adc / rain_wet_adc
 *                                 light_dark_adc / light_bright_adc
 *                                 air_quality_clean_baseline
 *   backend/app/core/sensors.py -> rain/light ADC ranges (10-bit, 0..1023)
 */
#define ADC_MAX 1023
#define RAIN_DRY_ADC 950        /* dry board reads high */
#define RAIN_WET_ADC 250        /* wet board reads low  */
#define LIGHT_DARK_ADC 40       /* covered LDR reads low */
#define LIGHT_BRIGHT_ADC 900    /* bright light reads high */
#define AIR_QUALITY_CLEAN_ADC 180 /* MQ-135 clean-air baseline (relative) */

/* ------------------------------------------------------------------ sensor -- */
/* Readings outside these physically plausible windows are treated as invalid
 * and are omitted from the payload instead of being sent as garbage. */
#define TEMP_MIN_C -40.0F
#define TEMP_MAX_C 85.0F
#define HUMIDITY_MIN_PCT 0.0F
#define HUMIDITY_MAX_PCT 100.0F
#define PRESSURE_MIN_HPA 300.0F
#define PRESSURE_MAX_HPA 1100.0F

/* Consecutive read cycles with no valid reading at all before the firmware
 * escalates the serial error and stops reporting the node as healthy. A cycle
 * with no valid measurement is never transmitted: the backend would reject an
 * empty payload with HTTP 422, so sending it would only waste the Wi-Fi stack. */
#define SENSOR_FAILURE_LIMIT 3

/* Wall-clock behaviour: the UNO R4 has no RTC, so the node learns the time from
 * the backend's `server_time` field and omits `timestamp` until it has. The
 * backend's MAX_TIMESTAMP_SKEW_SECONDS (default 900) is the authority on how
 * much drift is tolerated; the firmware never sends an unsynced clock. */

#endif /* ENVMON_CONFIG_H */
