import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_DAILY_RESET, SENSOR_KEYS

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = "energy_stats_data"


class EnergyStatsCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.hass = hass
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name="Energy Stats",
            update_interval=timedelta(seconds=5),
            config_entry=entry,
        )
        self.entry_id = entry.entry_id
        self.sensors = {k: entry.data.get(k) for k in SENSOR_KEYS.keys()}
        self.daily_reset = entry.data.get(CONF_DAILY_RESET, "00:00")
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")

        self._last_update = datetime.now()
        self._energy_sums = {}  # kWh seit letztem Reset (keys wie 'gridInEnergy', 'PVEnergy' ...)
        self._last_reset = datetime.now()
        self._energy_baselines = {}
        self._pv_sums = {}
        self._grid_sums = {}

        _LOGGER.info("Update interval is %s", self.update_interval)

    async def _async_update_data(self):  # noqa: C901, PLR0912, PLR0915
        _LOGGER.debug("Executing _async_update_data")

        if not self._energy_sums:
            stored = await self._store.async_load()
            if stored:
                self._energy_sums = stored.get("energy_sums", {}) or {}
                self._energy_baselines = stored.get("energy_baselines", {}) or {}
                self._pv_sums = stored.get("pv_sums", {}) or {}
                self._grid_sums = stored.get("grid_sums", {}) or {}
                last_reset_str = stored.get("last_reset")
                try:
                    self._last_reset = (
                        datetime.fromisoformat(last_reset_str)
                        if last_reset_str
                        else datetime.now()
                    )
                except Exception:
                    self._last_reset = datetime.now()
            else:
                self._energy_sums = {}
                self._energy_baselines = {}
                self._pv_sums = {}
                self._grid_sums = {}
                self._last_reset = datetime.now()

        now = datetime.now()
        elapsed_h = (
            (now - self._last_update).total_seconds() / 3600.0
            if self._last_update
            else 0
        )
        self._last_update = now

        state = self.hass.states

        result = {}
        self._calculated_keys = []

        def get_value(entity_id):
            if not entity_id:
                return None
            st = state.get(entity_id)
            if not st or st.state in ("unknown", "unavailable", None):
                return None
            try:
                return float(st.state)
            except (ValueError, TypeError):
                if st.state == "on":
                    return True
                if st.state == "off":
                    return False
                return None

        # Get raw values
        raw_vals = {}
        for key in SENSOR_KEYS:
            entity_id = self.sensors.get(key)
            if entity_id is not None:
                value = get_value(entity_id)
                if value is None:
                    _LOGGER.debug(f"Entity {entity_id} is not ready!")
                    raise UpdateFailed(f"Entity {entity_id} is not ready!")
                raw_vals[key] = value
                _LOGGER.debug(f"Value for {key}: {str(raw_vals[key])}")
            else:
                _LOGGER.debug(f"No Entity found for {key}")
                raw_vals[key] = None

        # --- Momentane Werte (Leistung) ---
        if raw_vals["grid_power"] is not None:
            result["grid_power"] = raw_vals["grid_power"]

        if raw_vals["car_charging_power"] is not None:
            result["car_charging_power"] = raw_vals["car_charging_power"]

        if raw_vals["pv_power"] is not None:
            result["pv_power"] = raw_vals["pv_power"]

        if raw_vals["battery_power"] is not None:
            result["battery_power"] = raw_vals["battery_power"]

        if raw_vals["car_connected"] is not None:
            result["car_connected"] = int(raw_vals["car_connected"])

        if raw_vals["car_soc"] is not None:
            result["car_soc"] = raw_vals["car_soc"]

        # --- Energiezähler aktualisieren (entweder Zählerwerte oder Integration aus Leistung) ---
        self._update_energy(
            "grid_in_energy_daily",
            raw_vals["grid_in_energy"],
            raw_vals["grid_power"],
            elapsed_h,
        )
        self._update_energy(
            "grid_out_energy_daily",
            raw_vals["grid_out_energy"],
            -raw_vals["grid_power"] if raw_vals["grid_power"] is not None else None,
            elapsed_h,
        )
        self._update_energy(
            "pv_energy_daily", raw_vals["pv_energy"], raw_vals["pv_power"], elapsed_h
        )
        self._update_energy(
            "car_charging_energy",
            raw_vals["car_charging_energy"],
            raw_vals["car_charging_power"],
            elapsed_h,
            use_baseline=False,
        )

        if raw_vals["battery_energy"] is not None:
            self._energy_sums["battery_energy"] = raw_vals["battery_energy"]

        # Hausverbrauch berechnen: Haushaltsenergie = (Netzbezug + PV-Erzeugung - Netzeinspeisung)
        grid_in = self._energy_sums.get("grid_in_energy")
        grid_out = self._energy_sums.get("grid_out_energy", 0.0)
        pv_e = self._energy_sums.get("pv_energy")
        if grid_in is not None and pv_e is not None:
            home_energy = grid_in + pv_e - grid_out
            # home_energy kann negativ sein, guarden wir dennoch
            self._energy_sums["home_energy_daily"] = home_energy

        # Füge die aufsummierten Energiewerte in result ein
        for k, v in self._energy_sums.items():
            result[k] = v

        def _mix_ratio(key):
            pv_sum = self._pv_sums.get(key, 0.0)
            grid_sum = self._grid_sums.get(key, 0.0)
            total = pv_sum + grid_sum
            return pv_sum / total if total > 0 else 0

        # --- Energy Mixes ---
        if raw_vals["battery_power"] and raw_vals["battery_power"] > 0:
            self._add_mix_energy(
                "battery_power",
                raw_vals["pv_power"],
                raw_vals["grid_power"],
                elapsed_h,
            )
            result["battery_energy_mix_daily"] = _mix_ratio("battery_energy")
            self._calculated_keys.append("battery_energy_mix_daily")

        self._add_mix_energy(
            "home_energy_daily",
            raw_vals["pv_power"],
            raw_vals["grid_power"],
            elapsed_h,
            result.get("battery_power"),
            result.get("battery_energy_mix_daily"),
        )
        result["home_energy_mix_daily"] = _mix_ratio("home_energy_daily")
        self._calculated_keys.append("home_energy_mix_daily")

        if raw_vals["car_charging_power"] is not None:
            self._add_mix_energy(
                "car_charging_energy",
                raw_vals["pv_power"],
                raw_vals["grid_power"],
                elapsed_h,
                result.get("battery_power"),
                result.get("battery_energy_mix_daily"),
            )
            result["car_charging_energy_mix"] = _mix_ratio("car_charging_energy")
            self._calculated_keys.append("car_charging_energy_mix")

        # --- Reset-Check täglich zur konfigurierten Uhrzeit ---
        try:
            hour, minute = (int(x) for x in self.daily_reset.split(":"))
        except Exception:
            hour, minute = 0, 0
        reset_time_today = now.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if now >= reset_time_today and self._last_reset < reset_time_today:
            _LOGGER.info("Energy Stats: Resetting daily values to 0.")
            self._energy_sums = {}
            self._energy_baselines = {}
            self._pv_sums = {}
            self._grid_sums = {}
            self._last_reset = now

        result["calculated_keys"] = self._calculated_keys

        try:
            await self._store.async_save(
                {
                    "energy_sums": self._energy_sums,
                    "pv_sums": self._pv_sums,
                    "grid_sums": self._grid_sums,
                    "energy_baselines": self._energy_baselines,
                    "last_reset": self._last_reset.isoformat(),
                }
            )
        except Exception as exc:
            _LOGGER.exception("Fehler beim Speichern der Power Mixer Daten: %s", exc)

        _LOGGER.debug("Done running update: " + str(result))

        return result

    def _update_energy(
        self, key, energy_sensor_value, power_sensor_value, elapsed_h, use_baseline=True
    ):
        if energy_sensor_value is not None:
            baseline = 0
            if use_baseline:
                baseline = self._energy_baselines.get(key)
                if baseline is None:
                    self._energy_baselines[key] = energy_sensor_value
                    baseline = energy_sensor_value
                self._calculated_keys.append(key)
            self._energy_sums[key] = max(0.0, energy_sensor_value - baseline)
            return

        if power_sensor_value is not None and elapsed_h > 0 and power_sensor_value > 0:
            prev = self._energy_sums.get(key, 0.0)
            self._energy_sums[key] = prev + (power_sensor_value / 1000.0) * elapsed_h
            self._calculated_keys.append(key)

    def _add_mix_energy(
        self,
        key,
        pv_power,
        grid_power,
        elapsed_h,
        battery_power=None,
        battery_pv_factor=None,
    ):
        if pv_power is None:
            pv_power = 0
        if grid_power is None:
            grid_power = 0
            return

        if battery_power is not None and battery_power > 0:
            if battery_pv_factor is not None:
                grid_power += (1 - battery_pv_factor) * battery_power
                pv_power += battery_pv_factor * battery_power
            else:
                grid_power += battery_power

        pv_part = max(0.0, pv_power) * elapsed_h
        grid_part = max(0.0, grid_power) * elapsed_h
        self._pv_sums[key] = self._pv_sums.get(key, 0.0) + pv_part
        self._grid_sums[key] = self._grid_sums.get(key, 0.0) + grid_part

        _LOGGER.debug("%s: %f, %f", key, self._pv_sums[key], self._grid_sums[key])
