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
#define WIFI_RETRY_INTERVAL_MS 5000UL /* between Wi-Fi reconnect attempts        */
#define HTTP_TIMEOUT_MS 6000UL     /* socket read/write timeout                  */
#define SERIAL_BAUD 115200

/* --------------------------------------------------------------- pin map --- */
/* DHT12 / AM2302 data line (needs a 10 kOhm pull-up to 3V3/5V). */
#define PIN_DHT 2
#define DHT_TYPE DHT22      /* DHT12 in one-wire mode and AM2302 both use DHT22 */

#define PIN_RAIN_ANALOG A0  /* rain sensor analog output (LM393 board AO) */
#define PIN_LDR_ANALOG A1   /* LDR divider (GL5528 + 10 kOhm)              */
#define PIN_MQ135_ANALOG A2 /* MQ-135 analog output (after 24 h burn-in)   */

/* BMP280 uses the default I2C pins (SDA/SCL) on the UNO R4 WiFi. */
#define BMP280_I2C_ADDRESS 0x76 /* 0x77 when the SDO pin is tied high */
#define BMP280_SEA_LEVEL_HPA 1013.25F

/* Five risk LEDs: index 0 = level 1 ... index 4 = level 5. */
#define PIN_LED_1 3
#define PIN_LED_2 4
#define PIN_LED_3 5
#define PIN_LED_4 6
#define PIN_LED_5 7
#define LED_ACTIVE_HIGH 1   /* set 0 for active-low wiring */

/* Buzzer: D8. 0 = active buzzer (tone() with the fixed resonance frequency),
 * 1 = passive buzzer driven with tone(). Silence is always achievable. */
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

/* Consecutive sensor failures before the channel is reported as missing. */
#define SENSOR_FAILURE_LIMIT 3

/* --------------------------------------------------------------- robustness - */
/* A reading whose device clock differs from the server by more than this is
 * dropped by the backend, so the firmware only sends a timestamp when it has
 * synced with the server at least once. */
#define CLOCK_DRIFT_TOLERANCE_S 900

#endif /* ENVMON_CONFIG_H */
