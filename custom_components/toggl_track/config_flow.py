"""implements graphical configuration flow for setting up Toggl Track integration."""

from http import HTTPStatus
import logging
from typing import Any

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

from .const import (
    CONF_WORKSPACES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DOMAIN,
    MAX_POLL_INTERVAL_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
    TOGGL_TRACK_PROFILE_URL,
)

_LOGGER = logging.getLogger(__name__)

_poll_range = vol.Range(min=MIN_POLL_INTERVAL_SECONDS, max=MAX_POLL_INTERVAL_SECONDS)

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
        vol.Optional(
            CONF_SCAN_INTERVAL,
            default=DEFAULT_POLL_INTERVAL_SECONDS,
            description="Toggl Track Polling interval",
        ): vol.All(vol.Coerce(int), _poll_range),
    }
)


class TogglTrackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Toggl Track."""

    VERSION = 1
    MINOR_VERSION = 1

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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user initialted Reconfigure step.

        Allows changing the polling interval.

        TODO: API key? or is there a better flow for that?
        """
        errors: dict[str, str] = {}

        # It's not immediately obvious if there's a better way to do this...
        # Need to get access to the already instantiated TogglTrackCoordinator instance so we can get the scan interval.
        # This way, the reconfigure step can show the current scan interval as the default value in the form to inform the user of the current value.
        # Fortunately, we don't have to modify the value of the scan interval in the coordinator, it's updated / persisted on async_update_reload_and_abort()
        ##
        # TODO: assert/check?
        _entry_id = self._get_reconfigure_entry().entry_id
        _coordinator = self.hass.data[DOMAIN][_entry_id]
        self._scan_interval = _coordinator.update_interval.total_seconds()
        _LOGGER.debug("Scan interval: %s", self._scan_interval)

        SCAN_INTERVAL_SCHEMA = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    # When default is not specified, seems to fall back to the minimum value specified in _poll_range
                    default=self._scan_interval,
                    description="Toggl Track Polling interval",
                ): vol.All(vol.Coerce(int), _poll_range),
            }
        )

        if user_input is None:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=SCAN_INTERVAL_SCHEMA,
                errors=errors,
            )

        if user_input:
            if CONF_SCAN_INTERVAL not in user_input:
                # TODO: double check that this is the right error key for strings.json
                errors[CONF_SCAN_INTERVAL] = "required"
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=SCAN_INTERVAL_SCHEMA,
                    errors=errors,
                )

        return self.async_update_reload_and_abort(
            self._get_reconfigure_entry(),
            data_updates=user_input,
        )

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
                await self.async_set_unique_id(str(self._acct_details.id))

        # See:  https://developers.home-assistant.io/docs/integration_setup_failures
        # TODO: raise: ConfigValidationError?
        except ClientResponseError as http_err:
            _LOGGER.error("Error creating entry. http_err: %s", http_err)
            if http_err.status == HTTPStatus.UNAUTHORIZED:
                errors[CONF_API_KEY] = "unauthorized"
            if http_err.status == HTTPStatus.FORBIDDEN:
                errors[CONF_API_KEY] = "forbidden"
            else:
                errors[CONF_API_KEY] = "cannot_connect"

        except Exception as e:  # noqa: BLE001
            _LOGGER.error("Error creating entry. e: %s", e)
            errors[CONF_API_KEY] = "unknown"
            # Hacky info gathering for https://github.com/kquinsland/ha-toggl-track/issues/19
            _LOGGER.error("Exception on entity.create. e: %s", e)

        if errors:
            _LOGGER.debug(
                "Errors in user input. Showing form again. Errors: %s", errors
            )
            return self.async_show_form(
                step_id="user",
                data_schema=AUTH_SCHEMA,
                errors=errors,
                description_placeholders={"profile_url": TOGGL_TRACK_PROFILE_URL},
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
