import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN, SENSOR_KEYS, CONF_DAILY_RESET


class EnergyStatsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, vol.Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors = {}
        if user_input is not None:
            data = {}
            for k in SENSOR_KEYS.keys():
                data[k] = user_input.get(k)
            data[CONF_DAILY_RESET] = user_input.get(CONF_DAILY_RESET)
            entries = self._async_current_entries()
            if entries:
                self.hass.config_entries.async_update_entry(entries[0], data=user_input)
                return self.async_abort(reason="Reconfigured!")
            else:
                return self.async_create_entry(title="Energy Stats", data=data)

        schema_dict = {}

        entries = self._async_current_entries()
        defaults = entries[0].data if entries else {}

        # Daily reset time
        schema_dict[
            vol.Required(
                CONF_DAILY_RESET, default=defaults.get(CONF_DAILY_RESET, "00:00")
            )
        ] = selector.TimeSelector()

        for key, params in SENSOR_KEYS.items():
            volKey = None
            if params[1] == "optional":
                volKey = vol.Optional(
                    key, description={"suggested_value": defaults.get(key)}
                )
            else:
                volKey = vol.Required(
                    key, description={"suggested_value": defaults.get(key)}
                )

            schema_dict[volKey] = selector.selector(
                {
                    "entity": {
                        "filter": {
                            "domain": (
                                "binary_sensor" if (params[0] == "plug") else "sensor"
                            ),
                            "device_class": params[0],
                        }
                    }
                }
            )

        # Build voluptuous schema but we will use selectors in UI - Home Assistant will map entity pickers by key
        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            description_placeholders={},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, vol.Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            entry = self.context.get("entry")
            if entry is None:
                return self.async_abort(reason="no_entry_found")
            self.hass.config_entries.async_update_entry(entry, data=user_input)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="Reconfigured!")

        return await self.async_step_user(None)
