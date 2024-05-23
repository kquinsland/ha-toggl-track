"""DataUpdateCoordinator for the Toggl Track API/component."""

import asyncio.timeouts as async_timeout
from datetime import timedelta
import logging

from lib_toggl.client import Toggl
from lib_toggl.time_entries import TimeEntry
from lib_toggl.workspace import Workspace

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)


class TogglTrackCoordinator(DataUpdateCoordinator):
    """Coordinator for updating time entry data from Toggl Track."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        update_interval: timedelta,
        api: Toggl,
    ) -> None:
        """Initialize the Toggl Track coordinator."""
        super().__init__(
            hass, logger, name="Toggl Track", update_interval=update_interval
        )
        self.api = api
        self._workspaces = None
        # Not yet implemented, but will be next
        self._tags = None

    async def _async_update_data(self) -> TimeEntry:
        """Fetch Currently running TimeEntry from Toggl Track.

        The value returned here will be what's accessible via the `data` property of the coordinator obj.
        """
        try:
            # Fail if we can't get a response within 10 seconds
            async with async_timeout.timeout(10):
                return await self.api.get_current_time_entry()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def async_get_workspaces(self) -> list[Workspace]:
        """Return Toggl Track workspaces.

        Will not be called as part of the regular coordinator update interval loop.
        That's OK, though.
        Workspaces really don't change much - especially the way they're being used in HA here.
        No sense in sending off a "what's $workspaces does $user have?" request every 30 seconds...
        """
        if self._workspaces is None:
            self._workspaces = await self.api.get_workspaces()
        return self._workspaces

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and any connection."""
        await self.api.close()
        await super().async_shutdown()
