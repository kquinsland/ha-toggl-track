"""Platform for sensor integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_AT,
    ATTR_BILLABLE,
    ATTR_DURATION,
    ATTR_ID,
    ATTR_PROJECT_ID,
    ATTR_START,
    ATTR_STOP,
    ATTR_TAG_IDS,
    ATTR_TAGS,
    ATTR_TASK_ID,
    ATTR_USER_ID,
    ATTR_WORKSPACE_ID,
    ATTR_WORKSPACE_NAME,
    CONF_WORKSPACES,
    DOMAIN,
)
from .coordinator import TogglTrackCoordinator

# Various attributes that each time entry has
TE_SPECIFIC_ATTR_KEYS = [
    ATTR_ID,
    ATTR_AT,
    ATTR_START,
    ATTR_STOP,
    ATTR_DURATION,
    ATTR_BILLABLE,
    ATTR_PROJECT_ID,
    ATTR_TASK_ID,
    ATTR_USER_ID,
    ATTR_TAGS,
    ATTR_TAG_IDS,
    ATTR_WORKSPACE_ID,
]

# Attributes that are "static".
# Either the TimeEntry object won't have this attribute on it or the value will be the same for all time entries for a given workspace/account
ACCT_ATTR_KEYS = [
    ATTR_WORKSPACE_ID,
    ATTR_WORKSPACE_NAME,
]


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    _LOGGER.debug("async_setup_entry is alive")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    _acct = await coordinator.api.get_account_details()
    # Will be a dict where key is ID, value is name
    _workspaces = config_entry.options[CONF_WORKSPACES]

    async_add_entities(
        [
            # Multiple workspaces are a premium thing; I can't test this as is.
            # This _should_ work with multiple workspaces but I've got just the one for now...
            ##
            TogglTrackWorkspaceSensorEntity(
                coordinator,
                config_entry.entry_id,
                _acct.id,
                workspace_id,
                workspace_name,
            )
            for workspace_id, workspace_name in _workspaces.items()
        ]
    )


# Long term, would be nice to have workspace selection as part of init/options flow
# But for now, just create a sensor for each worksapce. User can always disable the ones they don't want
# This way we have an easy / user-friendly way to show the worksapce name and ID
# Then can select other workspace entities in the create time track service call...
##
class TogglTrackWorkspaceSensorEntity(
    CoordinatorEntity[TogglTrackCoordinator], SensorEntity
):
    """Sensor representing workspace details.

    Workspace(s) are mostly read-only; this is just a "helper" that
    makes it easier to see the workspace name and ID in the UI.
    """

    def __init__(
        self,
        coordinator: TogglTrackCoordinator,
        config_entry_id: str,
        account_id: int,
        workspace_id: int,
        workspace_name: str,
    ) -> None:
        """Pass coordinator to CoordinatorEntity and store some UUIDs."""
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("TogglTrackWorkspaceSensorEntity is alive")
        self._toggle_acct_id = account_id
        self._workspace_id = workspace_id
        self._workspace_name = workspace_name

        # Human friendly name in HA ui
        self._attr_name = f"{workspace_name}"
        # UUID is used internally to HA
        self._attr_unique_id = f"{config_entry_id}_{account_id}_{workspace_id}"

        self._state = None

        # Can set workspace name/ID immediately.
        # Once first Time Entry comes back, can update the rest of the attributes
        self._attrs: dict[str, Any] = {
            ATTR_WORKSPACE_ID: workspace_id,
            ATTR_WORKSPACE_NAME: workspace_name,
        }

        # If things went well, coordinator should have already fetched the current time entry
        # Check and use it's values for state/attrs so we don't have to wait for the next update in ~ 60s
        self._update_state()

    def _update_state(self) -> None:
        """Update the state of the sensor."""
        # If there is no time entry running, remove all the attributes that are specific to the time entry
        if self.coordinator.data is None:
            _LOGGER.debug(
                "No current time entry running; state to become None and attrs to be cleared"
            )
            self._state = None

            # Clear all attributes that are not 'static'
            for k in list(set(TE_SPECIFIC_ATTR_KEYS) - set(ACCT_ATTR_KEYS)):
                if k in self._attrs:
                    del self._attrs[k]

        else:
            # If there is a time entry running, set all the attributes that are specific to the time entry
            # We don't bother with tag and tag IDs individually; zip them up into a dict
            self._state = self.coordinator.data.description

            for k in TE_SPECIFIC_ATTR_KEYS:
                self._attrs[k] = getattr(self.coordinator.data, k)

            # Everything copied in, zip up then clean up
            self._attrs[ATTR_TAGS] = dict(
                zip(self._attrs[ATTR_TAG_IDS], self._attrs[ATTR_TAGS])
            )
            self._attrs.pop(ATTR_TAG_IDS)
        # This is a bit of a hack, but it works
        # For reasons that are going to suck to track down, the workspace ID is
        #   showing up as an integer when first set but as soon as we get a None for
        #   time entry / state, the workspace ID is showing up as a string
        ##
        self._attrs[ATTR_WORKSPACE_ID] = self._workspace_id
        self._attrs[ATTR_WORKSPACE_NAME] = self._workspace_name

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return "mdi:timeline-clock"

    @property
    def state(self) -> StateType | None:
        """Return the state of the sensor."""
        return self._state

    @property
    def state_attributes(self) -> dict[str, str | int | float]:
        """Return the state attributes."""
        return self._attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state()
        super()._handle_coordinator_update()
