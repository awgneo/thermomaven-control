"""A probe's meat and doneness set its target, and offer only what fits."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.thermomaven.select import (
    TARGETS,
    ProbeChoice,
    ThermoMavenDoneness,
    ThermoMavenMeat,
)


@pytest.fixture
def choice() -> ProbeChoice:
    """A probe's choice, with its two entities and a climate entity that records its target."""
    climate = MagicMock()
    climate.async_set_temperature = AsyncMock()
    probe = ProbeChoice(climate)
    probe.entities = [MagicMock(), MagicMock()]
    return probe


def target(choice: ProbeChoice) -> int | None:
    calls = choice.climate.async_set_temperature.await_args
    return calls.kwargs["temperature"] if calls else None


async def test_a_meat_alone_sets_no_target(choice):
    await choice.async_choose(meat="Beef")
    assert target(choice) is None
    assert choice.doneness is None


async def test_meat_and_doneness_set_the_target(choice):
    await choice.async_choose(meat="Beef")
    await choice.async_choose(doneness="Medium Well")
    assert target(choice) == 150


async def test_doneness_offers_only_what_the_meat_has(choice):
    await choice.async_choose(meat="Poultry")
    assert choice.donenesses() == ["Well Done"]
    await choice.async_choose(meat="Fish")
    assert choice.donenesses() == ["Medium", "Well Done"]


async def test_a_doneness_the_new_meat_lacks_becomes_its_most_done(choice):
    await choice.async_choose(meat="Beef")
    await choice.async_choose(doneness="Rare")
    await choice.async_choose(meat="Poultry")
    assert choice.doneness == "Well Done"
    assert target(choice) == 165


async def test_a_doneness_the_new_meat_has_stays(choice):
    await choice.async_choose(meat="Beef")
    await choice.async_choose(doneness="Medium")
    await choice.async_choose(meat="Pork")
    assert choice.doneness == "Medium"
    assert target(choice) == 145


async def test_a_choice_updates_both_entities(choice):
    await choice.async_choose(meat="Beef")
    for entity in choice.entities:
        entity.async_write_ha_state.assert_called_once()


@pytest.mark.parametrize("meat", TARGETS)
async def test_every_doneness_sets_its_target(choice, meat):
    await choice.async_choose(meat=meat)
    for doneness, temperature in TARGETS[meat].items():
        await choice.async_choose(doneness=doneness)
        assert target(choice) == temperature


async def test_the_table_only_gets_hotter():
    for donenesses in TARGETS.values():
        temperatures = list(donenesses.values())
        assert temperatures == sorted(temperatures)


async def test_the_first_probe_has_no_number_in_its_names(choice):
    meat = ThermoMavenMeat(choice, "1", 1)
    doneness = ThermoMavenDoneness(choice, "1", 1)
    assert (meat.name, meat.unique_id) == ("Meat", "1_probe_1_meat")
    assert (doneness.name, doneness.unique_id) == ("Doneness", "1_probe_1_doneness")


async def test_a_second_probe_is_named(choice):
    meat = ThermoMavenMeat(choice, "1", 2)
    assert (meat.name, meat.unique_id) == ("Probe 2 Meat", "1_probe_2_meat")


async def test_the_doneness_options_follow_the_meat(choice):
    doneness = ThermoMavenDoneness(choice, "1", 1)
    await choice.async_choose(meat="Fish")
    assert doneness.options == ["Medium", "Well Done"]
    assert doneness.current_option is None
