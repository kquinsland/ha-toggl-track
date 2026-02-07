# Repository Guidelines

## Project Structure & Module Organization

This repository is a Home Assistant custom integration for Toggl Track.

- `custom_components/toggl_track/`: integration runtime code (`__init__.py`, `config_flow.py`, `coordinator.py`, `sensor.py`, `services.py`, `const.py`), plus `manifest.json`, `services.yaml`, and translations.
- `tests/`: pytest-based tests (currently `test_init.py`) and test config helpers.
- `docs/`: development notes and screenshots under `docs/_files/` used by `README.md`.
- Root config files: `setup.cfg`, `.editorconfig`, `.pre-commit-config.yaml`, `requirements.test.txt`.

## Build, Test, and Development Commands

- `python -m venv .venv && source .venv/bin/activate`: create local environment.
- `pip install -r requirements.test.txt`: install test dependencies.
- `pytest`: run all tests with strict mode and coverage for `custom_components`.
- `pytest tests/test_init.py -q`: run a focused test during iteration.
- `pre-commit install`: install local git hooks.
- `pre-commit run -a`: run format/lint checks (isort, yamllint, markdownlint, JSON/YAML checks).

## Coding Style & Naming Conventions

- Follow `.editorconfig`: 4 spaces for Python, 2 spaces for YAML/JSON/Markdown, LF line endings.
- Python style targets 88-character lines (`flake8`/`isort` settings in `setup.cfg`).
- Use snake_case for module/function names, UPPER_CASE for constants in `const.py`.
- Follow Home Assistant async patterns (`async_*` methods, coordinator-based updates).

## Testing Guidelines

- Framework: `pytest` + `pytest-homeassistant-custom-component`.
- Place tests in `tests/` with names `test_*.py` and clear behavior-focused test names.
- For new features, add or update tests alongside code changes; keep coverage focused on changed integration paths.

## Commit & Pull Request Guidelines

- Prefer short, imperative commit subjects (examples from history: `Fix broken documentation link`, `Update ... to v6`).
- Keep commits scoped to one concern when practical.
- PRs should include:
  - what changed and why,
  - linked issue(s) when relevant,
  - validation steps run (`pytest`, `pre-commit run -a`),
  - screenshots for UI/config-flow changes.

## Security & Configuration Tips

- Never commit API tokens or local secrets.
- Keep integration credentials in Home Assistant config flow, not source files.
