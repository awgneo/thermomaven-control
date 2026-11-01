# ThermoMaven Control for Home Assistant

Run your ThermoMaven wireless thermometer's cooks from Home Assistant, with no need for the app.

## Features

Each probe has:

- **A climate entity that runs its cook.** Turning it on starts a cook at the target, changing the target changes a running cook, and turning it off ends the cook. With no cook running a target is only remembered, so choosing one never starts anything.
- **Meat and Doneness selects, which set the target.** Doneness offers only what the meat allows. They start at Beef and Medium Well, and the temperatures are in `select.py`.
- **Sensors:** the probe's temperature and five areas, ambient temperature, cook times, cooking state and mode, batteries and WiFi signal.

Readings arrive live over MQTT, and commands go over HTTP, the way the app works.

## Installation

### HACS

1. Go to HACS → Integrations → ⋮ → Custom repositories, and add this repository's URL as an Integration.
2. Download **ThermoMaven Control**, then restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → ThermoMaven Control**, and sign in with your ThermoMaven account.

## Development

| Command | What it does |
|---|---|
| `flow test` | Run the test suite |
| `flow lint` | Lint the integration and its tests |
| `flow build` | Fetch the ThermoMaven app into `.apks/`, the only source for its protocol, checked against its signing certificate and never installed. Needs `apkeep`, `jadx` and the Android SDK build-tools (`brew install apkeep jadx`; Android Studio installs the SDK) |

[PROTOCOL.md](PROTOCOL.md) records the protocol as the app speaks it.

## License

MIT: see [LICENSE](LICENSE).
