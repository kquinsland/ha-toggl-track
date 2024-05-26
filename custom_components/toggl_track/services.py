"""Handle Toggl Track Service calls."""

from __future__ import annotations

import logging

from aiohttp.client_exceptions import ClientResponseError
from lib_toggl.time_entries import TimeEntry
from voluptuous import All, Any, Invalid, Length, Optional, Required, Schema

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
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
        # Will use XOR
        ATTR_WORKSPACE_ID: cv.positive_int,
        SERVICE_WORKSPACE_ID_ENTITY_ID: str,
        Optional(ATTR_CREATED_WITH, description="test-description"): All(
            cv.string, Length(min=1, max=128)
        ),
        Optional(ATTR_PROJECT_ID): cv.positive_int,
        Optional(ATTR_TAGS): All(cv.ensure_list, [_TAG_SCHEMA]),
        Optional(ATTR_BILLABLE): bool,
        # TODO: add support for start/stop dates. This will allow creating a time entry for a past date
        # This will require more work on the lib-toggle side to make sure that start+duration = stop and other bits of validation that i'm not in the mood for right now
    }
)


def _xor_validator(incoming_data):
    """Exclusive Or validator for stop/edit time entry schema.

    Either the sensor entity id is specified or both the workspace and time entry ID must be.
    """
    # Voluptuous will have already done basic type validation so we just check for presence/absence of keys
    if SERVICE_WORKSPACE_ID_ENTITY_ID not in incoming_data:
        # If the entity ID is not present, we need both workspace and time entry IDs
        if ATTR_WORKSPACE_ID in incoming_data and ATTR_TIME_ENTRY_ID in incoming_data:
            return incoming_data

        raise Invalid(
            "If Sensor Entity ID not provided, BOTH Workspace ID and Time Entry ID must be provided."
        )
    # We know that the entity ID is present
    if ATTR_WORKSPACE_ID in incoming_data or ATTR_TIME_ENTRY_ID in incoming_data:
        raise Invalid(
            "If Sensor Entity ID is provided, Workspace ID and Time Entry ID must NOT be provided."
        )
    return incoming_data


def _new_te_xor_validator(incoming_data):
    """Exclusive Or validator for new time entry schema.

    There's no good way to do Exclusive() and Required() at the same time w/o nesting the data.
    Nesting is not possible so we roll our own.
    The logic is more or less the same but with the new time entry service, we have fewer inputs that
        the XOR logic needs to be applied to
    """
    # Voluptuous will have already done basic type validation so we just check for presence/absence of keys
    if SERVICE_WORKSPACE_ID_ENTITY_ID not in incoming_data:
        # If the entity ID is not present, we need both workspace and time entry IDs
        if ATTR_WORKSPACE_ID in incoming_data:
            return incoming_data

    if SERVICE_WORKSPACE_ID_ENTITY_ID in incoming_data:
        if ATTR_WORKSPACE_ID not in incoming_data:
            return incoming_data
    raise Invalid("If Sensor Entity ID not provided, Workspace ID must be provided.")


# Stop service takes nothing but a workspace ID and time entry ID
STOP_TIME_ENTRY_SERVICE_SCHEMA = Schema(
    All(
        # Do a basic check to make sure that if it's provided, it's at least the right type
        {
            ATTR_TIME_ENTRY_ID: cv.positive_int,
            ATTR_WORKSPACE_ID: cv.positive_int,
            SERVICE_WORKSPACE_ID_ENTITY_ID: str,
        },
        # Then do the XOR check
        _xor_validator,
    )
)


# The underlying API allows for editing just about every aspect of a time entry.
# At least for now, the edit service is just for changing the name and tags on a time entry.
##
# Like Stop, Edit requires either explicit workspace/time entry IDs or an entity ID in addition to the description and tags
EDIT_TIME_ENTRY_SERVICE_SCHEMA = Schema(
    All(
        # Do a basic check to make sure that if it's provided, it's at least the right type
        {
            Optional(ATTR_DESCRIPTION, description="Name of the Time Entry"): All(
                cv.string, Length(min=1, max=255)
            ),
            Optional(ATTR_TAGS): All(cv.ensure_list, [_TAG_SCHEMA]),
            ATTR_TIME_ENTRY_ID: cv.positive_int,
            ATTR_WORKSPACE_ID: cv.positive_int,
            SERVICE_WORKSPACE_ID_ENTITY_ID: str,
        },
        # Then do the XOR check
        _xor_validator,
    )
)


def _get_attr_from_entity_id(
    attr_name: str, call_data: dict, hass: HomeAssistant
) -> Any | None:
    """Get $attr from entity ID.

    Returns None if the entity ID does not exist or does not have $attr.
    """

    if SERVICE_WORKSPACE_ID_ENTITY_ID not in call_data:
        _LOGGER.error(
            "Entity ID not provided in service call data. Cannot do indirect lookup of %s",
            attr_name,
        )
        return None

    _LOGGER.debug(
        "Doing indirect lookup of %s from entity ID %s",
        attr_name,
        call_data[SERVICE_WORKSPACE_ID_ENTITY_ID],
    )

    entity_state = hass.states.get(
        call_data[SERVICE_WORKSPACE_ID_ENTITY_ID],
    )

    if entity_state is None:
        _LOGGER.error(
            "Entity ID '%s' does not exist",
            call_data[SERVICE_WORKSPACE_ID_ENTITY_ID],
        )
        return None

    if attr_name not in entity_state.attributes:
        _LOGGER.error(
            "Entity ID '%s' does not have an attribute named '%s'",
            call_data[SERVICE_WORKSPACE_ID_ENTITY_ID],
            attr_name,
        )
        return None
    return entity_state.attributes[attr_name]


def _handle_workspace_id(hass: HomeAssistant, call_data: dict[str, Any]):
    if ATTR_WORKSPACE_ID not in call_data:
        if attr_value := _get_attr_from_entity_id(ATTR_WORKSPACE_ID, call_data, hass):
            call_data[ATTR_WORKSPACE_ID] = attr_value
        else:
            # pylint: disable=line-too-long
            _err = f"Provided entity ID {call_data[SERVICE_WORKSPACE_ID_ENTITY_ID]} does not have a workspace ID"
            _LOGGER.error(_err)
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cant_fetch_ws_id_from_entity_id",
                translation_placeholders={
                    "entity_id": call_data[SERVICE_WORKSPACE_ID_ENTITY_ID]
                },
            )


def _handle_time_entry_id(hass: HomeAssistant, call_data: dict[str, Any]):
    # The toggle track API is inconsistent. Depending on the verb/API endpoint
    #   they payload may need to refer to a time entry with _just_ `id` or `time_entry_id`.
    # Internal to lib-toggl and the underlying Pydantic models, it's _always_ `id` and is adjusted
    #   on the fly based on the API endpoint/verb.
    # But for the stop and edit service calls, it's always called `ATTR_TIME_ENTRY_ID`
    # So we need to re-write and then drop after extracting the value
    ##
    if ATTR_TIME_ENTRY_ID not in call_data:
        if attr_value := _get_attr_from_entity_id(ATTR_ID, call_data, hass):
            call_data[ATTR_ID] = attr_value
        else:
            # pylint: disable=line-too-long
            _err = f"Provided entity ID {call_data[SERVICE_WORKSPACE_ID_ENTITY_ID]} does not have a time entry ID"
            _LOGGER.error(_err)
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cant_fetch_te_id_from_entity_id",
                translation_placeholders={
                    "entity_id": call_data[SERVICE_WORKSPACE_ID_ENTITY_ID]
                },
            )
    else:
        call_data[ATTR_ID] = call_data[ATTR_TIME_ENTRY_ID]
        del call_data[ATTR_TIME_ENTRY_ID]


def _clean_call_data(call_data: dict[str, Any]) -> dict[str, Any]:
    """Remove any keys from call_data that are not expected by the lib-toggl API."""
    if SERVICE_WORKSPACE_ID_ENTITY_ID in call_data:
        del call_data[SERVICE_WORKSPACE_ID_ENTITY_ID]


def async_register_services(
    hass: HomeAssistant, coordinator: TogglTrackCoordinator
) -> None:
    """Register services for Toggl Track integration."""

    async def handle_start_new_time_entry(call: ServiceCall) -> dict:
        """Handle creating a new Time Entry."""

        _LOGGER.debug("handle_start_new_time_entry() called")
        # Call.data is immutable; copy before we clear SERVICE_WORKSPACE_ID_ENTITY_ID
        #   and set the workspace ID
        call_data = call.data.copy()

        _handle_workspace_id(hass, call_data)
        _clean_call_data(call_data)

        new_time_entry = TimeEntry(**call_data)
        try:
            created_time_entry = await coordinator.api.create_new_time_entry(
                new_time_entry
            )
            # Update entity immediately so we don't have to wait for the next poll
            coordinator.async_set_updated_data(created_time_entry)

        except ClientResponseError as err:
            # TODO: in lib-toggl catch he various 4XX family and raise a more specific error
            raise HomeAssistantError(f"Error creating Time Entry: {err}") from err

        else:
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

        call_data = call.data.copy()

        _handle_workspace_id(hass, call_data)
        _handle_time_entry_id(hass, call_data)
        _clean_call_data(call_data)

        te_to_stop = TimeEntry(**call_data)
        try:
            stopped_te = await coordinator.api.stop_time_entry(te_to_stop)
        except ClientResponseError as err:
            # TODO: in lib-toggl catch he various 4XX family and raise a more specific error
            raise HomeAssistantError(f"Error stopping Time Entry: {err}") from err

        if call.return_response:
            # Pydantic 1.x uses .dict() instead of model_dump()
            return stopped_te.dict()
        return {}

    async def handle_edit_new_time_entry(call: ServiceCall) -> dict:
        _LOGGER.debug("handle_edit_new_time_entry() called with: %s", call.data)
        # Immutable so copy.
        call_data = call.data.copy()

        _handle_workspace_id(hass, call_data)
        _handle_time_entry_id(hass, call_data)
        _clean_call_data(call_data)

        edited_te = TimeEntry(**call_data)
        try:
            edited_te = await coordinator.api.edit_time_entry(edited_te)
            # Server returns the updated Time Entry so we can update the entity state directly / immediately
            coordinator.async_set_updated_data(edited_te)
        except ClientResponseError as err:
            # TODO: in lib-toggl catch he various 4XX family and raise a more specific error
            raise HomeAssistantError(f"Error editing Time Entry: {err}") from err
        else:
            if edited_te is None:
                _LOGGER.error("Failed to edit Time Entry")
                raise HomeAssistantError("Failed to edit Time Entry")

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
            schema=All(NEW_TIME_ENTRY_SERVICE_SCHEMA, _new_te_xor_validator),
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
