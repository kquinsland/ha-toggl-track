"""implements graphical configuration flow for setting up Toggl Track integration."""

from http import HTTPStatus
import logging
from typing import Any, Optional

from aiohttp.client_exceptions import ClientResponseError
from lib_toggl.account import Account
from lib_toggl.client import Toggl
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_WORKSPACES, DOMAIN, TOGGL_TRACK_PROFILE_URL

_LOGGER = logging.getLogger(__name__)

# Toggl does support a few different auth mechanisms but for now, API key is all that's supported here
AUTH_SCHEMA = vol.Schema(
    {
        # Use TextSelector for auto-complete functionality
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(
                # Treat the API key as a password so it's protected and so password managers can auto-fill
                type=TextSelectorType.PASSWORD,
                autocomplete="current-password",
            )
        ),
        # Allow user to set the polling interval; no faster than 30 seconds, no slower than 10 minutes
        vol.Optional(
            CONF_SCAN_INTERVAL, default=60, description="Toggl Track Polling interval"
        ): vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
    }
)


class TogglTrackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Toggl Track."""

    VERSION = 1
    MINOR_VERSION = 0

    # We need to instantiate a Toggl API client to validate the API key and
    # get the user's account details for uuid generation.
    ##

    def __init__(self) -> None:
        """Account details are how we confirm API key works and get the user's uuid.

        Workspace(s) are presented to user for selection during config flow.
        """
        self._api_key: str = None
        self._scan_interval: int = None

        self._acct_details: Account = None
        self._workspaces: dict[str, int] = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step if it's not already been done before.

        Prompt for API key and poll interval and show user the configured workspaces.
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=AUTH_SCHEMA,
                description_placeholders={"profile_url": TOGGL_TRACK_PROFILE_URL},
            )

        errors: dict[str, str] = {}
        try:
            # Use the toggl account ID as the unique ID for this entry
            # Only use the email (which can change) for human readable strings
            self._abort_if_unique_id_configured()
            async with Toggl(api_key=user_input[CONF_API_KEY]) as api:
                self._acct_details = await api.get_account_details()
                # Needed next, may as well fetch now
                self._workspaces = await api.get_workspaces()

                # Nothing blew up? Use toggl account ID as unique ID for this entry
                # Email can be changed, account ID cannot
                await self.async_set_unique_id(self._acct_details.id)

        # See:  https://developers.home-assistant.io/docs/integration_setup_failures
        # TODO: raise: ConfigValidationError?
        except ClientResponseError as http_err:
            _LOGGER.error("Error creating entry", extra={"http_err": http_err})
            if http_err.status == HTTPStatus.UNAUTHORIZED:
                errors[CONF_API_KEY] = "unauthorized"
            if http_err.status == HTTPStatus.FORBIDDEN:
                errors[CONF_API_KEY] = "forbidden"
            else:
                errors[CONF_API_KEY] = "cannot_connect"

        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.error("Error creating entry", extra={"e": e})
            errors[CONF_API_KEY] = "unknown"

        if errors:
            _LOGGER.debug(
                "Errors in user input. Showing form again. Errors: %s", errors
            )
            return self.async_show_form(
                step_id="user", data_schema=AUTH_SCHEMA, errors=errors
            )

        # No errors in user input and we have a valid API key, ask user to select workspaces
        _LOGGER.debug(
            "API key appears to work. Showing workspace selection form to user"
        )
        # The content of user_input doesn't accumulate between forms/steps and
        #   creating an entry is a finalizer so we need to stash the API key somewhere
        #   and then store it / everything else from this step in the next step
        ##
        self._api_key = user_input[CONF_API_KEY]
        self._scan_interval = user_input[CONF_SCAN_INTERVAL]

        return await self.async_step_workspaces()

    async def async_step_workspaces(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Do option flow for selecting workspaces to track."""

        # the multi_select helper is PICKY about the format of the dict
        # Can not do int -> str map between workspace ID and name
        # Must do str -> str map between workspace ID and name
        ##
        _ws_dict = {str(w.id): w.name for w in self._workspaces}

        if not user_input:
            _LOGGER.debug(
                "No user workspace selections. Getting workspaces for selection"
            )
            _ws_schema = vol.Schema(
                {
                    vol.Required(CONF_WORKSPACES): cv.multi_select(_ws_dict),
                }
            )
            return self.async_show_form(step_id="workspaces", data_schema=_ws_schema)

        _LOGGER.debug("User input received. Creating entry")
        return self.async_create_entry(
            title=f"Toggl Track: {self._acct_details.email}",
            data={
                CONF_API_KEY: self._api_key,
                CONF_SCAN_INTERVAL: self._scan_interval,
            },
            # From _ws_dict, store only the selected workspace id/names
            # I don't know if workspaces can be renamed. I am assuming that the ID will never
            #   change so long as the workspace exists.
            # Store the name just to save a few API calls later; if the name can change, it likely
            #   does not change often.
            options={
                CONF_WORKSPACES: {
                    k: v
                    for k, v in _ws_dict.items()
                    if k in user_input[CONF_WORKSPACES]
                }
            },
        )
