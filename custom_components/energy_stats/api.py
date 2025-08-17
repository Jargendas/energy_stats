"""API implementation of Energy Stats integration."""

import logging

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView

from .coordinator import EnergyStatsCoordinator

_LOGGER = logging.getLogger(__name__)


class EnergyStatsAPI(HomeAssistantView):
    """API handling class for Energy Stats integration."""

    url = "/api/energy_stats"
    name = "api:energy_stats"
    requires_auth = True

    def __init__(self, coordinator: EnergyStatsCoordinator) -> None:
        """Initialize API functionality with provided coordinator."""
        self.coordinator = coordinator

    async def get(self, _request) -> web.Response:  # noqa: ANN001
        """Handle the API get requests."""
        data = self.coordinator.data
        if "calculated_keys" in data:
            data.pop("calculated_keys")
        _LOGGER.debug("Returning data: %s", str(data))
        return web.json_response(data)


def async_setup_api(hass: HomeAssistant, coordinator: EnergyStatsCoordinator) -> None:
    """Set up the API."""
    _LOGGER.debug("Executing async_setup_api...")
    hass.http.register_view(EnergyStatsAPI(coordinator))
