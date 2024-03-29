"""Constans and other special strings."""
DOMAIN = "toggl_track"

INTEGRATION_VERSION = "0.0.1"
ISSUE_URL = "https://github.com/kquinsland/ha-toggl/issues"


STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{DOMAIN}
Version: {INTEGRATION_VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""

CONF_WORKSPACES = "workspaces"
TOGGL_TRACK_PROFILE_URL = "https://track.toggl.com/profile"

## Internals; Time Entry / Workspace ...etc Attributes

# Time Entries have quite a few attributes, not all of which are useful for HA
# See: https://developers.track.toggl.com/docs/api/time_entries#200-1
##
ATTR_ID = "id"
ATTR_DESCRIPTION = "description"
ATTR_WORKSPACE_ID = "workspace_id"
ATTR_WORKSPACE_NAME = "name"
ATTR_PROJECT_ID = "project_id"
ATTR_TASK_ID = "task_id"
ATTR_BILLABLE = "billable"
ATTR_START = "start"
ATTR_STOP = "stop"
ATTR_DURATION = "duration"
ATTR_TAGS = "tags"
ATTR_TAG_IDS = "tag_ids"
ATTR_AT = "at"
ATTR_USER_ID = "user_id"
ATTR_CREATED_WITH = "created_with"

## Internals; HA Services

SERVICE_NEW_TIME_ENTRY = "new_time_entry"
SERVICE_STOP_TIME_ENTRY = "stop_time_entry"
SERVICE_WORKSPACE_ID_ENTITY_ID = "workspace_id_entity_id"
