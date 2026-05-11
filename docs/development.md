# Development Guide

## Prerequisites

- Python 3.12+
- Node.js 20+ (for the frontend panel)

## Python environment setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
```

## Running the test suite

```bash
pytest
```

## Linting and type checking

```bash
ruff check custom_components tests
ruff format --check custom_components tests
mypy custom_components
```

## Frontend setup

```bash
cd frontend
npm install
npm run typecheck
npm run build
```

## Installing in a dev Home Assistant instance

1. Clone this repository into the `custom_components` directory of your HA config, or symlink it:
   ```bash
   ln -s /path/to/media_room_manager/custom_components/media_room_manager \
     /path/to/ha-config/custom_components/media_room_manager
   ```
2. Restart Home Assistant.
3. Navigate to **Settings → Integrations → Add Integration** and search for "Media Room Manager".
4. Click through the single-step config flow and confirm installation.
5. The integration should appear in the installed integrations list with no errors in the HA log.

## Project structure

See `CLAUDE.md` for the canonical directory layout and coding standards.
