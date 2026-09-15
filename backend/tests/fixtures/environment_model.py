"""Deterministic environmental model used **only** by the automated tests.

It produces payloads in exactly the Arduino firmware's shape and they are pushed
through the very same ``SensorService.ingest`` pipeline as real hardware, so the
production application ships without a single line of simulation code while the
test suite still covers the full data path.

Design goals:

* **No random nonsense.** Temperature follows a diurnal cycle plus a slow
  weather regime and AR(1) noise; humidity is inversely coupled to temperature
  (warmer air, lower relative humidity) and pushed up by rain; pressure follows a
  synoptic wave with a drift; rain is a Markov chain whose transition
  probabilities depend on humidity and pressure tendency; light follows a solar
  elevation curve attenuated by cloud; air quality has commuter peaks,
  ventilation dips and stagnation when the air is humid and still.
* **No fake precision.** Output values are rounded to what the physical sensors
  can actually resolve (DHT12 +-0.1 degC, BMP280 2 decimals, 10-bit ADC counts).
* **Reproducible.** Given a seed, the run is deterministic.
* **Fault injection.** The ``sensor_faults`` scenario freezes, disconnects and
  spikes sensors so the platform's sensor-health and anomaly paths can be tested
  without unplugging real hardware.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

#: 10-bit ADC (Arduino UNO R4 WiFi analogRead range used by this firmware).
ADC_MIN = 0
ADC_MAX = 1023

SCENARIOS: dict[str, dict[str, float | str]] = {
    "clear_day": {"label": "Clear, stable day", "temp_offset": 1.5, "cloud": 0.1, "rain_rate": 0.0},
    "mixed_weather": {"label": "Mixed weather with showers", "temp_offset": 0.0, "cloud": 0.4, "rain_rate": 0.08},
    "storm": {"label": "Approaching storm", "temp_offset": -2.0, "cloud": 0.9, "rain_rate": 0.45},
    "heatwave": {"label": "Heatwave", "temp_offset": 9.0, "cloud": 0.05, "rain_rate": 0.0},
    "cold_snap": {"label": "Cold snap", "temp_offset": -10.0, "cloud": 0.5, "rain_rate": 0.05},
    "pollution_event": {"label": "Air pollution episode", "temp_offset": 2.0, "cloud": 0.3, "rain_rate": 0.0},
    "sensor_faults": {"label": "Mixed weather with sensor faults", "temp_offset": 0.0, "cloud": 0.4, "rain_rate": 0.08},
    "random_walk": {"label": "Neutral random-walk baseline", "temp_offset": 0.0, "cloud": 0.3, "rain_rate": 0.05},
}


@dataclass
class SensorFaultConfig:
    frozen: list[str] = field(default_factory=list)
    disconnected: list[str] = field(default_factory=list)
    spiking: list[str] = field(default_factory=list)


@dataclass
class EnvironmentState:
    """Physical state of the simulated node."""

    temperature_c: float = 27.0
    humidity_pct: float = 62.0
    pressure_hpa: float = 1011.0
    wetness_pct: float = 0.0
    air_quality_raw: float = 210.0
    raining: bool = False
    rain_intensity: float = 0.0
    cloud_cover: float = 0.3
    regime: str = "mixed_weather"
    #: Normalised solar/cloud factor carried between step() and _payload().
    light_ratio: float = 0.0


class EnvironmentSimulator:
    """Time-stepping environmental model.

    Call :meth:`step` with the elapsed simulated seconds; it advances the model and
    returns a payload in the Arduino firmware's shape.
    """

    def __init__(
        self,
        scenario: str = "mixed_weather",
        *,
        seed: int | None = None,  # noqa: ARG002 - stored for describe()
        device_id: str = "arduino-r4-wifi-01",
        start_time: datetime | None = None,
        transmission_interval_ms: int = 15000,
        ip_address: str = "192.168.137.42",
        rssi: int = -58,
        latitude: float = 22.57,
        speed: float = 1.0,
        faults: SensorFaultConfig | None = None,
    ) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(
                f"Unknown scenario '{scenario}'. Available: {', '.join(sorted(SCENARIOS))}"
            )
        self.seed = seed
        self.random = random.Random(seed)
        self.scenario = scenario
        self.config = SCENARIOS[scenario]
        self.device_id = device_id
        self.transmission_interval_ms = transmission_interval_ms
        self.ip_address = ip_address
        self.rssi = rssi
        self.latitude = latitude
        self.speed = max(0.1, speed)
        self.faults = faults or (
            SensorFaultConfig(
                frozen=["pressure_hpa"],
                disconnected=["rain_raw"],
                spiking=["air_quality_raw"],
            )
            if scenario == "sensor_faults"
            else SensorFaultConfig()
        )

        # The physics clock starts at 06:30 local time so a demo shows sunrise
        # quickly, but payload timestamps must stay on the real wall clock so the
        # backend's clock-drift guard accepts them. ``_wall_start`` keeps the
        # real time; the offset between the two is constant.
        now = start_time or datetime.now(UTC).astimezone()
        self._wall_start = now
        local = now.astimezone().replace(hour=6, minute=30, second=0, microsecond=0)
        self.clock = local
        self.base_pressure = 1011.0 + self.random.uniform(-4, 4)
        self.state = EnvironmentState(
            temperature_c=20.0 + float(self.config["temp_offset"]),
            humidity_pct=70.0,
            pressure_hpa=self.base_pressure,
            air_quality_raw=200.0,
            cloud_cover=float(self.config["cloud"]),
            regime=scenario,
        )
        self._temperature_noise = 0.0
        self._humidity_noise = 0.0
        self._pressure_noise = 0.0
        self._air_noise = 0.0
        self._synoptic_phase = self.random.uniform(0, math.pi * 2)
        self._pollution_event_until: float | None = None
        self._elapsed_seconds = 0.0
        self._sequence = 0
        self._frozen_values: dict[str, float] = {}

    # ------------------------------------------------------------------ helpers
    @property
    def wall_clock(self) -> datetime:
        """Real time-of-day timestamp for the current step (UTC).

        The simulated clock may sit at a different hour of day (to make day/night
        behaviour visible during a short demo); the transmitted timestamp must
        still be honest about *when* the reading was produced, otherwise the
        backend correctly flags it as stale/clock-drifted.
        """
        return (self._wall_start + timedelta(seconds=self._elapsed_seconds)).astimezone(UTC)

    @property
    def local_hour(self) -> float:
        return self.clock.hour + self.clock.minute / 60.0 + self.clock.second / 3600.0

    def _solar_factor(self) -> float:
        hour = self.local_hour
        if hour < 6.0 or hour > 19.0:
            return 0.0
        return max(0.0, math.sin(math.pi * (hour - 6.0) / 13.0))

    def _ar1(self, previous: float, sigma: float, memory: float = 0.92) -> float:
        return memory * previous + self.random.gauss(0.0, sigma) * math.sqrt(1 - memory**2)

    # --------------------------------------------------------------------- step
    def step(self, dt_seconds: float = 15.0) -> dict:
        """Advance the model by ``dt_seconds`` of simulated time."""
        dt_seconds = max(1.0, dt_seconds)
        self._elapsed_seconds += dt_seconds
        self.clock += timedelta(seconds=dt_seconds)
        hours = dt_seconds / 3600.0
        state = self.state

        # --- temperature: diurnal cycle + regime offset + slow noise ----------
        day_phase = math.sin((self.local_hour - 9.0) / 24.0 * 2 * math.pi)
        diurnal = 4.5 * day_phase
        self._temperature_noise = self._ar1(self._temperature_noise, 0.35, memory=0.95)
        target_temp = (
            24.0 + float(self.config["temp_offset"]) + diurnal + self._temperature_noise
        )
        # rain cools the air, cloud cover trims the peak
        target_temp -= state.raining * 1.2
        target_temp -= state.cloud_cover * self._solar_factor() * 1.0
        state.temperature_c += (target_temp - state.temperature_c) * min(1.0, hours * 0.6)

        # --- humidity: inversely coupled to temperature, raised by rain -------
        self._humidity_noise = self._ar1(self._humidity_noise, 1.2, memory=0.9)
        comfort_target = 68.0 - (state.temperature_c - 24.0) * 1.6
        humidity_target = comfort_target + self._humidity_noise
        if state.raining:
            humidity_target = max(humidity_target, 88.0 + state.rain_intensity * 6.0)
        elif state.cloud_cover > 0.6:
            humidity_target += 6.0
        humidity_target = _clamp(humidity_target, 22.0, 99.0)
        state.humidity_pct += (humidity_target - state.humidity_pct) * min(1.0, hours * 0.8)

        # --- pressure: synoptic wave + slow drift ----------------------------
        self._pressure_noise = self._ar1(self._pressure_noise, 0.12, memory=0.97)
        self._synoptic_phase += hours * 0.25
        synoptic = 5.5 * math.sin(self._synoptic_phase)
        if self.scenario == "storm":
            synoptic -= self._elapsed_seconds / 3600.0 * 1.8  # steady fall
        elif self.scenario == "heatwave":
            synoptic += 4.0
        pressure_target = self.base_pressure + synoptic + self._pressure_noise
        state.pressure_hpa += (pressure_target - state.pressure_hpa) * min(1.0, hours * 0.5)
        state.pressure_hpa = _clamp(state.pressure_hpa, 950.0, 1050.0)

        # --- rain: Markov chain driven by humidity and pressure tendency ------
        base_rate = float(self.config["rain_rate"])
        humidity_push = max(0.0, (state.humidity_pct - 72.0) / 28.0)
        pressure_push = max(0.0, (1008.0 - state.pressure_hpa) / 15.0)
        onset_probability = min(0.75, base_rate * (0.4 + humidity_push + pressure_push))
        if state.raining:
            stop_probability = 0.28 * (1.0 - humidity_push)
            if self.random.random() < min(0.4, stop_probability * hours * 6):
                state.raining = False
                state.rain_intensity = 0.0
        elif self.random.random() < onset_probability * hours * 4:
            state.raining = True
            state.rain_intensity = self.random.uniform(0.35, 1.0)

        if state.raining:
            wetness_target = 45.0 + state.rain_intensity * 55.0
            state.wetness_pct += (wetness_target - state.wetness_pct) * min(1.0, hours * 1.4)
        else:
            # drying is exponential: ~10 % per 10 minutes in dry air, slower when humid
            dry_rate = 0.9 + (1.0 - state.humidity_pct / 100.0) * 2.4
            state.wetness_pct *= math.exp(-dry_rate * hours * 0.35)
        state.wetness_pct = _clamp(state.wetness_pct, 0.0, 100.0)
        state.cloud_cover = _clamp(
            float(self.config["cloud"]) + (0.45 if state.raining else 0.0), 0.0, 1.0
        )

        # --- light: solar curve attenuated by cloud, near zero at night -------
        solar = self._solar_factor()
        light_ratio = solar * (1.0 - 0.75 * state.cloud_cover)
        light_gain = max(0.0, light_ratio) ** 1.35
        # small artificial light floor after dusk (a real node usually sees some)
        light_floor = 0.06 if (self.local_hour < 6.0 or self.local_hour > 19.0) else 0.0
        light_ratio = max(light_gain, light_floor)
        state.light_ratio = light_ratio

        # --- air quality: commuter peaks, ventilation dips, stagnation --------
        self._air_noise = self._ar1(self._air_noise, 4.0, memory=0.9)
        hour = self.local_hour
        commuter = (
            math.exp(-((hour - 8.5) ** 2) / 2.2) * 55.0
            + math.exp(-((hour - 19.0) ** 2) / 2.6) * 45.0
        )
        night_stagnation = 28.0 if 0.0 <= hour < 6.0 else 0.0
        stagnant_humid = max(0.0, (state.humidity_pct - 70.0)) * 0.35
        air_target = 175.0 + commuter + night_stagnation + stagnant_humid + self._air_noise
        air_target -= state.wetness_pct * 0.25  # rain scavenges particulates
        if self.scenario == "pollution_event":
            until = self._pollution_event_until
            if until is None or self._elapsed_seconds > until:
                self._pollution_event_until = self._elapsed_seconds + self.random.uniform(1800, 5400)
            air_target += 260.0 + self.random.uniform(0, 80)
        state.air_quality_raw += (air_target - state.air_quality_raw) * min(1.0, hours * 0.9)
        state.air_quality_raw = _clamp(state.air_quality_raw, 120.0, 1000.0)

        return self._payload()

    # ------------------------------------------------------------------ outputs
    def _payload(self) -> dict:
        state = self.state
        self._sequence += 1

        # --- convert physics to sensor-domain values --------------------------
        temperature = round(state.temperature_c + self.random.gauss(0, 0.18), 1)
        humidity = round(_clamp(state.humidity_pct + self.random.gauss(0, 0.9), 0.0, 100.0), 1)
        bmp_temperature = round(state.temperature_c + self.random.gauss(0, 0.12), 1)
        pressure = round(state.pressure_hpa + self.random.gauss(0, 0.11), 2)

        # rain board: dry -> high ADC, wet -> low ADC (matching the normaliser)
        rain_ratio = state.wetness_pct / 100.0
        rain_raw = round(_clamp(950.0 - rain_ratio * 700.0 + self.random.gauss(0, 4), 0, 1023))
        rain_pct = round(rain_ratio * 100.0, 1)

        light_ratio = state.light_ratio
        light_pct = round(_clamp(
            (math.log1p(9.5 * max(light_ratio, 0.0)) / math.log1p(9.5)) * 100.0
            + self.random.gauss(0, 1.2),
            0.0,
            100.0,
        ), 1)
        ldr_raw = round(_clamp(40.0 + (light_pct / 100.0) * 860.0 + self.random.gauss(0, 6), 0, 1023))

        air_raw = round(_clamp(state.air_quality_raw + self.random.gauss(0, 3), 0, 1023))

        measurements: dict[str, float] = {
            "temperature_c": temperature,
            "humidity_pct": humidity,
            "bmp_temperature_c": bmp_temperature,
            "pressure_hpa": pressure,
            "rain_raw": float(rain_raw),
            "rain_pct": rain_pct,
            "ldr_raw": float(ldr_raw),
            "light_pct": light_pct,
            "air_quality_raw": float(air_raw),
        }

        # --- fault injection --------------------------------------------------
        missing: list[str] = []
        for key in self.faults.frozen:
            if key in measurements:
                self._frozen_values.setdefault(key, measurements[key])
                measurements[key] = self._frozen_values[key]
        for key in self.faults.disconnected:
            if key in measurements:
                measurements.pop(key)
                missing.append(key)
        for key in self.faults.spiking:
            if key in measurements and self.random.random() < 0.06:
                measurements[key] = _clamp(measurements[key] * like_spike(self.random), 0.0, 1023.0)

        payload: dict = {
            "device_id": self.device_id,
            "timestamp": self.wall_clock.isoformat(),
            "sequence": self._sequence,
            "firmware_version": "1.0.0",
            "uptime_ms": int(self._elapsed_seconds * 1000),
            "ip_address": self.ip_address,
            "rssi": self.rssi + int(self.random.gauss(0, 2)),
            "transmission_interval_ms": self.transmission_interval_ms,
            **{key: round(value, 2) for key, value in measurements.items()},
        }
        # The firmware also sends its locally derived classification strings; the
        # backend recomputes them, which is exactly the path we want to exercise.
        payload["rain_status"] = _rain_status(rain_pct)
        payload["light_status"] = _light_status(light_pct)
        if missing:
            payload["sensors_missing"] = missing
        return payload

    # ------------------------------------------------------------------ helpers
    def describe(self) -> dict:
        return {
            "scenario": self.scenario,
            "scenario_label": self.config["label"],
            "device_id": self.device_id,
            "seed": self.seed,
            "transmission_interval_ms": self.transmission_interval_ms,
            "clock": self.clock.isoformat(),
            "state": {
                "temperature_c": round(self.state.temperature_c, 2),
                "humidity_pct": round(self.state.humidity_pct, 2),
                "pressure_hpa": round(self.state.pressure_hpa, 2),
                "wetness_pct": round(self.state.wetness_pct, 2),
                "air_quality_raw": round(self.state.air_quality_raw, 2),
                "raining": self.state.raining,
            },
        }


def like_spike(random_source: random.Random) -> float:
    """A multiplicative spike factor for fault injection (1.3x - 2.2x)."""
    return random_source.uniform(1.3, 2.2)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _rain_status(rain_pct: float) -> str:
    if rain_pct <= 5:
        return "dry"
    if rain_pct <= 40:
        return "light rain"
    if rain_pct <= 75:
        return "rain"
    return "heavy rain"


def _light_status(light_pct: float) -> str:
    if light_pct <= 5:
        return "dark"
    if light_pct <= 35:
        return "dim"
    if light_pct <= 70:
        return "moderate"
    return "bright"


__all__ = ["EnvironmentSimulator", "EnvironmentState", "SensorFaultConfig", "SCENARIOS"]
