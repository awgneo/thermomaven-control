"""Select platform for ThermoMaven: a probe's meat and doneness, which set its target."""
from dataclasses import dataclass, field

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

# Each meat's donenesses and their targets (°F), mildest first
TARGETS = {
    "Beef": {"Rare": 125, "Medium Rare": 135, "Medium": 145, "Medium Well": 150, "Well Done": 160},
    "Pork": {"Medium": 145, "Medium Well": 150, "Well Done": 160},
    "Lamb": {"Rare": 125, "Medium Rare": 135, "Medium": 145, "Well Done": 160},
    "Fish": {"Medium": 140, "Well Done": 145},
    "Poultry": {"Well Done": 165},
}


@dataclass
class ProbeChoice:
    """What's chosen for a probe, which its two entities share."""

    climate: object
    meat: str | None = None
    doneness: str | None = None
    entities: list[SelectEntity] = field(default_factory=list)

    def donenesses(self) -> list[str]:
        """Return the donenesses of the chosen meat."""
        return list(TARGETS.get(self.meat, {}))

    async def async_choose(self, meat: str | None = None, doneness: str | None = None) -> None:
        """Choose, then set the probe's target. A doneness the meat doesn't have becomes its most done."""
        self.meat = meat or self.meat
        self.doneness = doneness or self.doneness
        if self.doneness not in self.donenesses():
            self.doneness = None if self.doneness is None or self.meat is None else self.donenesses()[-1]
        if self.meat and self.doneness:
            await self.climate.async_set_temperature(temperature=TARGETS[self.meat][self.doneness])
        for entity in self.entities:
            entity.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add every probe's meat and doneness, beside its climate entity."""
    climates = hass.data[DOMAIN][entry.entry_id].get("climates", {})
    entities = []
    for (device_id, probe_num), climate in climates.items():
        choice = ProbeChoice(climate)
        pair = [
            ThermoMavenMeat(choice, device_id, probe_num),
            ThermoMavenDoneness(choice, device_id, probe_num),
        ]
        choice.entities.extend(pair)
        entities.extend(pair)
    async_add_entities(entities)


class ThermoMavenChoice(RestoreEntity, SelectEntity):
    """One of a probe's two choices, which it remembers across restarts."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    label = ""

    def __init__(self, choice: ProbeChoice, device_id: str, probe_num: int) -> None:
        """Initialize, on the probe's device. The first probe needs no number in its name."""
        self._choice = choice
        self._attr_name = f"Probe {probe_num} {self.label}" if probe_num > 1 else self.label
        self._attr_unique_id = f"{device_id}_probe_{probe_num}_{self.label.lower()}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device_id)})


class ThermoMavenMeat(ThermoMavenChoice):
    """The probe's meat."""

    label = "Meat"
    _attr_icon = "mdi:food-steak"
    _attr_options = list(TARGETS)

    @property
    def current_option(self) -> str | None:
        """Return the chosen meat."""
        return self._choice.meat

    async def async_added_to_hass(self) -> None:
        """Restore the meat, without setting a target."""
        if (last_state := await self.async_get_last_state()) is not None and last_state.state in TARGETS:
            self._choice.meat = last_state.state

    async def async_select_option(self, option: str) -> None:
        """Choose a meat."""
        await self._choice.async_choose(meat=option)


class ThermoMavenDoneness(ThermoMavenChoice):
    """The probe's doneness, among its meat's."""

    label = "Doneness"
    _attr_icon = "mdi:silverware-fork-knife"

    @property
    def options(self) -> list[str]:
        """Return what the chosen meat offers."""
        return self._choice.donenesses()

    @property
    def current_option(self) -> str | None:
        """Return the chosen doneness."""
        return self._choice.doneness

    async def async_added_to_hass(self) -> None:
        """Restore the doneness, without setting a target."""
        if (last_state := await self.async_get_last_state()) is not None and last_state.state not in (
            "unknown",
            "unavailable",
        ):
            self._choice.doneness = last_state.state

    async def async_select_option(self, option: str) -> None:
        """Choose a doneness."""
        await self._choice.async_choose(doneness=option)
