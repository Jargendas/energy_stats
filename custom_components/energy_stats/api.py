from homeassistant.components import http
from homeassistant.components.http import HomeAssistantView
from aiohttp import web
from .const import DOMAIN


class EnergyStatsAPI(HomeAssistantView):
    url = "/api/energy_stats"
    name = "api:energy_stats"
    requires_auth = True  # sicherer default; setze False nur wenn gewollt

    def __init__(self, coordinator):
        self.coordinator = coordinator

    async def get(self, request):
        # Gibt die zuletzt berechneten Daten als JSON zurück
        coordinator = request.app["hass"].data[DOMAIN]["coordinator"]
        return web.json_response(coordinator.data)


def async_setup_api(hass, coordinator):
    hass.http.register_view(EnergyStatsAPI(coordinator))
