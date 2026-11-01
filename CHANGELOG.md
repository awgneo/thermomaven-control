# Changelog

## 1.7.0 - 2026-11-01

### Changed
- Each MQTT status report reaches the entities at once, instead of waiting for a refresh, limited to one every 10 seconds.
- A target ThermoMaven accepted shows immediately, until the device reports it, or for 30 seconds if it never does.

### Fixed
- Starting up no longer deletes and recreates every entity, which could lose the climate entity and reset entity settings.
- Sensor setup adds a device's sensors once, instead of rebuilding them on every update.

## 1.6.1 - 2026-11-01

### Fixed
- Meat and Doneness always hold a real choice, and never read as unknown.

## 1.6.0 - 2026-11-01

### Added
- Each probe has Meat and Doneness selects, which set its target.

## 1.5.0 - 2026-11-01

### Changed
- Cooks are started, changed and ended over HTTP in the app's format, and nothing is published over MQTT.
- A probe's climate entity starts a cook when turned on and ends it when turned off.

### Fixed
- Each probe's area and ambient temperatures read that probe.
