"""Handle Hue Service calls."""

from __future__ import annotations

import logging

from lib_toggl.time_entries import TimeEntry
from voluptuous import All, Any, Exclusive, Length, Optional, Required, Schema

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
import homeassistant.helpers.config_validation as cv

from .const import (
    ATTR_BILLABLE,
    ATTR_CREATED_WITH,
    ATTR_DESCRIPTION,
    ATTR_ID,
    ATTR_PROJECT_ID,
    ATTR_TAGS,
    ATTR_TIME_ENTRY_ID,
    ATTR_WORKSPACE_ID,
    DOMAIN,
    SERVICE_EDIT_TIME_ENTRY,
    SERVICE_NEW_TIME_ENTRY,
    SERVICE_STOP_TIME_ENTRY,
    SERVICE_WORKSPACE_ID_ENTITY_ID,
)
from .coordinator import TogglTrackCoordinator

_LOGGER = logging.getLogger(__name__)

# Not clear if there's an upper bound on the length of a tag so I'm going to just
#   use the same length as the description
_TAG_SCHEMA = Schema(cv.string, Length(min=1, max=255))

NEW_TIME_ENTRY_SERVICE_SCHEMA = Schema(
    {
        Required(ATTR_DESCRIPTION, description="Name of the Time Entry"): All(
            cv.string, Length(min=1, max=255)
        ),
        # One or the other must be provided but not both.
        Exclusive(ATTR_WORKSPACE_ID, "workspace_id_or_entity_id"): cv.positive_int,
        Exclusive(SERVICE_WORKSPACE_ID_ENTITY_ID, "workspace_id_or_entity_id"): str,
        Optional(ATTR_CREATED_WITH, description="test-description"): All(
            cv.string, Length(min=1, max=128)
        ),
        Optional(ATTR_PROJECT_ID): cv.positive_int,
        Optional(ATTR_TAGS): All(cv.ensure_list, [_TAG_SCHEMA]),
        Optional(ATTR_BILLABLE): bool,
        # TODO: add support for start/stop dates. This will allow creating a time entry for a past date
        # This will require more work on the lib-toggle side to make sure that start+duration = stop and other bits of validation that i'm not in the moooood for right now
    }
)


# Implementing Exclusive OR with Voluptuous is a bit roundabout.
# We have to define a valid workspace sensor entity ID schema and a valid workspace/time entry ID schema
# Then get the OR propery by wrapping them in the Any() function
ENTITY_ID_SCHEMA = Schema({Required(SERVICE_WORKSPACE_ID_ENTITY_ID): str})

WORKSPACE_AND_TIME_ENTRY_ID_SCHEMA = Schema(
    {
        Required(ATTR_WORKSPACE_ID): cv.positive_int,
        Required(ATTR_TIME_ENTRY_ID): cv.positive_int,
    }
)

STOP_TIME_ENTRY_SERVICE_SCHEMA = Any(
    ENTITY_ID_SCHEMA, WORKSPACE_AND_TIME_ENTRY_ID_SCHEMA
)

# The underlying API almost doesn't differentiate between creating and editing a time entry
# Exposing a much simpler set of functionality to the user via HA: change name / tags
EDIT_TIME_ENTRY_SERVICE_SCHEMA = Schema(
    {
        Optional(ATTR_DESCRIPTION, description="Name of the Time Entry"): All(
            cv.string, Length(min=1, max=255)
        ),
        Optional(ATTR_TAGS): All(cv.ensure_list, [_TAG_SCHEMA]),
        # One or the other must be provided but not both.
        Exclusive(ATTR_WORKSPACE_ID, "workspace_id_or_entity_id"): cv.positive_int,
        Exclusive(SERVICE_WORKSPACE_ID_ENTITY_ID, "workspace_id_or_entity_id"): str,
        # We need the time entry ID, obviously. If user does not explicitly provide it, we'll try to get it from the entity ID
        Exclusive(ATTR_TIME_ENTRY_ID, "time_entry_id_or_entity_id"): cv.positive_int,
        Exclusive(SERVICE_WORKSPACE_ID_ENTITY_ID, "time_entry_id_or_entity_id"): str,
    }
)


def _get_attr_from_entity_id(
    attr_name: str, call: ServiceCall, hass: HomeAssistant
) -> Any | None:
    """Get $attr from entity ID.

    Returns None if the entity ID does not exist or does not have $attr.
    """
    if attr_name is None:
        _LOGGER.error("Invalid attr_name passed to _get_attr_from_entity_id()")
        return None

    if SERVICE_WORKSPACE_ID_ENTITY_ID not in call.data:
        _LOGGER.error(
            "Entity ID not provided in service call data. Cannot do indirect lookup of %s",
            attr_name,
        )
        return None

    _LOGGER.debug(
        "Doing indirect lookup of %s from entity ID %s",
        attr_name,
        call.data[SERVICE_WORKSPACE_ID_ENTITY_ID],
    )

    entity_state = hass.states.get(
        call.data[SERVICE_WORKSPACE_ID_ENTITY_ID],
    )

    if entity_state is None:
        _LOGGER.error(
            "Entity ID '%s' does not exist",
            call.data[SERVICE_WORKSPACE_ID_ENTITY_ID],
        )
        return None

    if attr_name not in entity_state.attributes:
        _LOGGER.error(
            "Entity ID '%s' does not have an attribute named '%s'",
            call.data[SERVICE_WORKSPACE_ID_ENTITY_ID],
            attr_name,
        )
        return None
    return entity_state.attributes[attr_name]


def async_register_services(
    hass: HomeAssistant, coordinator: TogglTrackCoordinator
) -> None:
    """Register services for Toggl Track integration."""

    async def handle_start_new_time_entry(call: ServiceCall) -> dict:
        """Handle creating a new Time Entry."""

        _LOGGER.debug("handle_start_new_time_entry() called")
        # Call.data is immutable so we need to make a copy before we clear SERVICE_WORKSPACE_ID_ENTITY_ID and set the workspace ID
        _call_data = call.data.copy()

        if ATTR_WORKSPACE_ID not in call.data:
            workspace_id = _get_attr_from_entity_id(ATTR_WORKSPACE_ID, call, hass)
            if workspace_id is None:
                _err = f"Provided entity ID {call.data[SERVICE_WORKSPACE_ID_ENTITY_ID]} does not have a workspace ID"
                # TODO: ther's got to be a better way to surface errors to the user on the service call interface?
                _LOGGER.error(_err)
                return {"error": _err}

            _call_data[ATTR_WORKSPACE_ID] = workspace_id
            # Unset SERVICE_WORKSPACE_ID_ENTITY_ID in the copy before passing it to the lib_toggl code
            del _call_data[SERVICE_WORKSPACE_ID_ENTITY_ID]
        new_time_entry = TimeEntry(**_call_data)
        created_time_entry = await coordinator.api.create_new_time_entry(new_time_entry)

        # Indicates if the service call should return a response
        # I'm not sure how the user gets to opt into this?
        # At least as far as I can tell, toggl will not return anything for the create call?
        # If that's true, may want to change how service is registered
        if call.return_response:
            # Pydantic 1.x uses .dict() instead of model_dump()
            return created_time_entry.dict()
        # set support_response to optional, but still get error when returning none
        # so return empty dict for now
        return None

    async def handle_stop_new_time_entry(call: ServiceCall) -> dict:
        """Handle stopping a Time Entry. Requires a workspace ID and a Time Entry ID."""
        _LOGGER.debug("handle_stop_new_time_entry() called")

        _call_data = call.data.copy()

        if ATTR_WORKSPACE_ID not in call.data:
            # To stop, we need both workspace AND time entry ID
            workspace_id = _get_attr_from_entity_id(ATTR_WORKSPACE_ID, call, hass)
            if workspace_id is None:
                _err = f"Provided entity ID {call.data[SERVICE_WORKSPACE_ID_ENTITY_ID]} does not have a workspace ID"
                _LOGGER.error(_err)
                return {"error": _err}
        else:
            workspace_id = call.data[ATTR_WORKSPACE_ID]
        _call_data[ATTR_WORKSPACE_ID] = workspace_id

        if ATTR_TIME_ENTRY_ID not in call.data:
            time_entry_id = _get_attr_from_entity_id(ATTR_TIME_ENTRY_ID, call, hass)
            if time_entry_id is None:
                _err = f"Provided entity ID {call.data[SERVICE_WORKSPACE_ID_ENTITY_ID]} does not have a current time entry"
                _LOGGER.error(_err)
                return {"error": _err}
        else:
            time_entry_id = call.data[ATTR_TIME_ENTRY_ID]
        _call_data[ATTR_TIME_ENTRY_ID] = time_entry_id

        if SERVICE_WORKSPACE_ID_ENTITY_ID in _call_data:
            # Unset SERVICE_WORKSPACE_ID_ENTITY_ID in the copy before passing it to the lib_toggl code
            del _call_data[SERVICE_WORKSPACE_ID_ENTITY_ID]

        te_to_stop = TimeEntry(**_call_data)
        stopped_te = await coordinator.api.stop_time_entry(te_to_stop)
        _LOGGER.debug("Result of stop_time_entry: %s", stopped_te)

        if call.return_response:
            # Pydantic 1.x uses .dict() instead of model_dump()
            return stopped_te.dict()
        return {}

    async def handle_edit_new_time_entry(call: ServiceCall) -> dict:
        _LOGGER.debug("handle_edit_new_time_entry() called with: %s", call.data)
        # Immutable so copy.
        _call_data = call.data.copy()

        # TODO: a lot of this validation is shared with stop(); can probably refactor out.
        if ATTR_WORKSPACE_ID not in call.data:
            workspace_id = _get_attr_from_entity_id(ATTR_WORKSPACE_ID, call, hass)
            if workspace_id is None:
                _err = f"Provided entity ID {call.data[SERVICE_WORKSPACE_ID_ENTITY_ID]} does not have {ATTR_WORKSPACE_ID}."
                _LOGGER.error(_err)
                return {"error": _err}
        else:
            workspace_id = call.data[ATTR_WORKSPACE_ID]
        _call_data[ATTR_WORKSPACE_ID] = workspace_id

        if ATTR_TIME_ENTRY_ID not in call.data:
            # Remember, toggle API is inconsistent. TimeEntry has an `id` for creation and polling current active
            # But when updating, it's `time_entry_id` on the API.
            # Since the HA entity is populated from the poll/current API call, we have to use `id` here
            time_entry_id = _get_attr_from_entity_id(ATTR_ID, call, hass)
            if time_entry_id is None:
                _err = f"Provided entity ID {call.data[SERVICE_WORKSPACE_ID_ENTITY_ID]} does not have {ATTR_TIME_ENTRY_ID}."
                _LOGGER.error(_err)
                return {"error": _err}

        else:
            time_entry_id = call.data[ATTR_TIME_ENTRY_ID]
        # See note above; TODO, see if pydantic supports aliases?
        _call_data[ATTR_ID] = time_entry_id

        if SERVICE_WORKSPACE_ID_ENTITY_ID in _call_data:
            # Unset SERVICE_WORKSPACE_ID_ENTITY_ID in the copy before passing it to the lib_toggl code as
            #   the lib_toggl internals have no idea what to do with it
            del _call_data[SERVICE_WORKSPACE_ID_ENTITY_ID]

        edited_te = TimeEntry(**_call_data)
        edited_te = await coordinator.api.edit_time_entry(edited_te)
        _LOGGER.debug("Result of edit_time_entry: %s", edited_te)
        if edited_te is None:
            _LOGGER.error("Failed to edit Time Entry")
            return {"error": "Failed to edit Time Entry"}

        # Server resturns the updated Time Entry so we can update the entity state directly / immediately
        coordinator.async_set_updated_data(edited_te)
        if call.return_response:
            # Pydantic 1.x uses .dict() instead of model_dump()
            return edited_te.dict()
        return {}

    # Bail if the service has already been registered
    if not hass.services.has_service(DOMAIN, SERVICE_NEW_TIME_ENTRY):
        _LOGGER.debug(
            "Service '%s' not registered, doing so now", SERVICE_NEW_TIME_ENTRY
        )

        hass.services.async_register(
            DOMAIN,
            SERVICE_NEW_TIME_ENTRY,
            handle_start_new_time_entry,
            schema=NEW_TIME_ENTRY_SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_STOP_TIME_ENTRY):
        _LOGGER.debug(
            "Service '%s' not registered, doing so now", SERVICE_STOP_TIME_ENTRY
        )

        hass.services.async_register(
            DOMAIN,
            SERVICE_STOP_TIME_ENTRY,
            handle_stop_new_time_entry,
            schema=STOP_TIME_ENTRY_SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_EDIT_TIME_ENTRY):
        _LOGGER.debug(
            "Service '%s' not registered, doing so now", SERVICE_EDIT_TIME_ENTRY
        )

        hass.services.async_register(
            DOMAIN,
            SERVICE_EDIT_TIME_ENTRY,
            handle_edit_new_time_entry,
            schema=EDIT_TIME_ENTRY_SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
