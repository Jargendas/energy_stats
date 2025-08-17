from homeassistant.components import http
from homeassistant.components.http import HomeAssistantView
from aiohttp import web
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)


class EnergyStatsAPI(HomeAssistantView):
    url = "/api/energy_stats"
    name = "api:energy_stats"
    requires_auth = True

    def __init__(self, coordinator):
        self.coordinator = coordinator

    async def get(self, request):
        data = self.coordinator.data
        if "calculated_keys" in data:
            data.pop("calculated_keys")
        _LOGGER.debug("Returning data: " + str(data))
        return web.json_response(data)


def async_setup_api(hass, coordinator):
    _LOGGER.debug("Executing async_setup_api...")
    hass.http.register_view(EnergyStatsAPI(coordinator))
