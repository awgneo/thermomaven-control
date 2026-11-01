"""Climate platform for ThermoMaven."""
import asyncio
import logging
import time
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MODELS, DOMAIN

_LOGGER = logging.getLogger(__name__)

# A probe's cook is running in these states, until it's ended: "ready" has reached the target, and it stays
# on to rest
ACTIVE_STATES = {"cooking", "ready", "resting", "remove"}
# How long a target ThermoMaven accepted shows before the device must have reported it (seconds)
PENDING_TARGET_SECONDS = 30
# A cook can't start from these, as far as the app's states say
UNREACHABLE_STATES = {"disconnected", "lost", "error"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ThermoMaven climate entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    # Wait for coordinator data
    if not coordinator.data or not coordinator.data.get("devices"):
        _LOGGER.debug("⏳ Waiting for coordinator data...")
        await asyncio.sleep(2)
        
        if not coordinator.data or not coordinator.data.get("devices"):
            _LOGGER.error("❌ No devices after waiting")
            return
    
    _LOGGER.debug("✅ Coordinator has %d device(s), proceeding with climate setup", 
                 len(coordinator.data.get("devices", [])))
    
    entities_to_add = []
    devices = coordinator.data.get("devices", [])
    
    for device in devices:
        device_id = str(device.get("deviceId"))
        
        if not device_id or device_id == "None":
            _LOGGER.warning("Skipping device with invalid deviceId: %s", device.get("deviceName"))
            continue
        
        device_model = device.get("deviceModel", "Unknown")
        num_probes = _get_num_probes(device_model)
        
        _LOGGER.debug("➕ Adding climate entities for device: %s (%s)", device.get("deviceName"), device_id)
        
        # Add climate entity for each probe
        for probe_num in range(1, num_probes + 1):
            entities_to_add.append(
                ThermoMavenClimate(
                    coordinator, api, device, probe_num, entry.entry_id
                )
            )
    
    # The select platform reaches each probe's climate entity through these
    hass.data[DOMAIN][entry.entry_id]["climates"] = {
        (entity._device_id, entity._probe_num): entity for entity in entities_to_add
    }

    if entities_to_add:
        _LOGGER.debug("🌡️ Adding %d climate entities", len(entities_to_add))
        async_add_entities(entities_to_add, update_before_add=False)
    else:
        _LOGGER.warning("⚠️ No climate entities to add")
    
    _LOGGER.debug("✅ Climate setup complete")


def _get_num_probes(device_model: str) -> int:
    """Get number of probes for a device model."""
    probe_counts = {
        "WT02": 2,  # P2
        "WT06": 4,  # P4
        "WT07": 2,  # G2
        "WT09": 4,  # G4
        "WT10": 1,  # G1
        "WT11": 1,  # P1
    }
    return probe_counts.get(device_model, 1)


class ThermoMavenClimate(CoordinatorEntity, RestoreEntity, ClimateEntity):
    """A probe's cook: on starts one at the target, off ends it, and the target changes a running one.

    With no cook running the target is only remembered, so choosing one never starts anything.
    """

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = 32
    _attr_max_temp = 572
    _attr_target_temperature_step = 1

    def __init__(self, coordinator, api, device, probe_num, entry_id):
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._api = api
        self._device = device
        self._device_id = str(device.get("deviceId"))
        self._device_model = device.get("deviceModel", "Unknown")
        self._probe_num = probe_num
        self._entry_id = entry_id
        self._next_target: float | None = None
        # What the next cook starts at when no target's been set: the probe's chosen meat and doneness
        self.default_target = None
        # A target ThermoMaven accepted, and when to stop waiting for the device to report it
        self._pending_target: float | None = None
        self._pending_until = 0.0

        self._attr_unique_id = f"{self._device_id}_probe_{probe_num}_climate"
        self._attr_name = f"Probe {probe_num} Control"
        self._attr_translation_key = f"probe_{probe_num}_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.get("deviceName", "ThermoMaven"),
            manufacturer="ThermoMaven",
            model=DEVICE_MODELS.get(self._device_model, self._device_model),
        )

    async def async_added_to_hass(self) -> None:
        """Remember the target across restarts."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            self._next_target = last_state.attributes.get(ATTR_TEMPERATURE)

    def _status(self) -> dict:
        """Return the device's last status report."""
        for device in (self.coordinator.data or {}).get("devices", []):
            if str(device.get("deviceId")) == self._device_id:
                return (device.get("lastStatusCmd") or {}).get("cmdData", {})
        return {}

    def _probe(self) -> dict:
        """Return this probe's part of the status, which names it probe1, probe2 and so on."""
        for probe in self._status().get("probes", []):
            if probe.get("probeColor") == f"probe{self._probe_num}":
                return probe
        return {}

    def _cook_is_running(self) -> bool:
        return self._probe().get("cookingState") in ACTIVE_STATES

    @property
    def current_temperature(self) -> float | None:
        """Return the probe's temperature (reported in tenths of a degree F)."""
        temperature = self._probe().get("curTemperature")
        return None if temperature is None else temperature / 10

    @property
    def target_temperature(self) -> float | None:
        """Return the running cook's target, or the one the next cook will start at."""
        if self._cook_is_running():
            for params in self._probe().get("setParams", []):
                if (temperature := params.get("setTemperature")) is not None:
                    return self._shown_target(temperature / 10)
        return self._idle_target()

    def _shown_target(self, reported: float) -> float:
        """Return a just-accepted target until the device reports it, or until it's taken too long."""
        if self._pending_target is None:
            return reported
        if reported == self._pending_target or time.monotonic() >= self._pending_until:
            self._pending_target = None
            return reported
        return self._pending_target

    def _idle_target(self) -> float | None:
        """Return the target the next cook starts at."""
        if self._next_target is not None:
            return self._next_target
        return self.default_target() if self.default_target else None

    @property
    def hvac_mode(self) -> HVACMode:
        """On while a cook runs."""
        return HVACMode.HEAT if self._cook_is_running() else HVACMode.OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Change the running cook's target, or remember the next one."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._next_target = temperature
        if self._cook_is_running():
            self._require_online()
            if not await self._api.async_change_cook(
                self._device_id, self._device_model, self._probe(), int(temperature * 10)
            ):
                raise HomeAssistantError(f"ThermoMaven refused the new target of {temperature}°F")
            self._pending_target = temperature
            self._pending_until = time.monotonic() + PENDING_TARGET_SECONDS
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Start or end the cook."""
        if hvac_mode == HVACMode.HEAT:
            await self.async_turn_on()
        elif hvac_mode == HVACMode.OFF:
            await self.async_turn_off()

    async def async_turn_on(self) -> None:
        """Start a cook at the target, unless one is running."""
        if self._cook_is_running():
            return
        target = self._idle_target()
        if target is None:
            raise HomeAssistantError("Set a target before starting a cook")
        state = self._probe().get("cookingState")
        if state in UNREACHABLE_STATES:
            raise HomeAssistantError(f"The probe can't start a cook while it's {state}")
        self._require_online()
        if not await self._api.async_start_cook(
            self._device_id, self._device_model, f"probe{self._probe_num}", int(target * 10)
        ):
            raise HomeAssistantError("ThermoMaven refused to start the cook")

    async def async_turn_off(self) -> None:
        """End the running cook."""
        if not self._cook_is_running():
            return
        self._require_online()
        if not await self._api.async_finish_cook(self._device_id, self._device_model, self._probe()):
            raise HomeAssistantError("ThermoMaven refused to end the cook")

    def _require_online(self) -> None:
        """A device that's offline can't take a command, which the app refuses too."""
        status = self._status().get("globalStatus")
        if status == "offline":
            raise HomeAssistantError("The thermometer is offline")
