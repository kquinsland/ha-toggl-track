# Development

Mostly just quick/dirty notes for myself.

## Setup

### HA Dev Containers

Basically mount the custom_components folder into the home assistant dev container by updating the `.devcontainer/devcontainer.json` file like so:

```json
{
  // ...
  "mounts": [
    // Store configuration externally
    //"source=${localEnv:HOME}/Projects/ha-toggl/ha-dev-cfg,target=${containerWorkspaceFolder}/config,type=bind",
    // Custom component
    "source=${localEnv:HOME}/Projects/ha-toggl/ha-toggl-track/custom_components,target=${containerWorkspaceFolder}/config/custom_components,type=bind",
    // manifest.json: requirements only really supports public github / PiPy repos
    // Load the local lib-toggl library as it's a dependency of the custom component
    // This will allow a `pip` install via local terminal/shell to work
    //      pip install /workspaces/ha-core/config/custom_libraries/lib-toggl
    "source=${localEnv:HOME}/Projects/ha-toggl/lib-toggl,target=${containerWorkspaceFolder}/config/custom_libraries/lib-toggl,type=bind"
  ]
}
```

Then just install updated `lib-toggl` directly into the dev container via the terminal:

```shell
vscode ➜ /workspaces/ha-core (add-toggl-track) $ pip install /workspaces/ha-core/config/custom_libraries/lib-toggl
```

You can then edit the `lib-toggl` library from the same context as the rest of the Home Assistant code base.
This is considerably easier than trying to get all the Home Assistant code / types ... etc setup in the same context as the lib-toggle code or this custom component.

### `doctoc`

The table of contents in `readme.md` is updated with [`doctoc`](https://github.com/thlorenz/doctoc)

```shell
❯ docker run --rm -v "$(pwd)":/app peterdavehello/npm-doctoc doctoc /app/README.md
<...>
```

### pre-commit

Assuming you've [installed the `pre-commit` tool](https://pre-commit.com/#install), just run the following to install the git hooks:

```shell
❯ pre-commit install
pre-commit installed at .git/hooks/pre-commit
```

## HA Logging

In dev container, the `logger` component of `config.yaml` can be set up to log the custom component at a debug level:

```yaml
logger:
  default: info
  logs:
    custom_components.toggl_track: debug
    custom_components.toggl_track.services: debug
```
