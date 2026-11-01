"""The integration set up for real, on a fake account: the selects find their climate entity and drive the cook."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thermomaven import ThermoMavenDataUpdateCoordinator
from custom_components.thermomaven.const import DOMAIN
from custom_components.thermomaven.thermomaven_api import ThermoMavenAPI

DEVICE = {
    "deviceId": "309302735543533569",
    "deviceModel": "WT10",
    "deviceName": "Kitchen Probe 1",
    "lastStatusCmd": {
        "cmdData": {
            "globalStatus": "online",
            "probes": [
                {
                    "probeColor": "probe1",
                    "cookingState": "cooking",
                    "cookingMode": "manual",
                    "cookUuid": "the-cook",
                    "startClient": "android",
                    "curTemperature": 793,
                    "setParams": [{"setTemperature": 1900}],
                }
            ],
        }
    },
}


@pytest.fixture
async def request_api(hass):
    """The integration loaded, with its cloud calls replaced. Yields the HTTP request mock."""
    entry = MockConfigEntry(domain=DOMAIN, data={"email": "cook@example.com", "password": "password"})
    entry.add_to_hass(hass)
    with (
        patch.object(ThermoMavenAPI, "async_login", AsyncMock(return_value=True)),
        patch.object(ThermoMavenAPI, "async_setup_mqtt", AsyncMock(return_value=True)),
        patch.object(ThermoMavenAPI, "async_wait_for_mqtt_device_list", AsyncMock(return_value=True)),
        patch.object(ThermoMavenAPI, "async_disconnect_mqtt", AsyncMock()),
        patch.object(ThermoMavenAPI, "_async_request", AsyncMock(return_value={"code": "0"})) as request,
        patch.object(ThermoMavenDataUpdateCoordinator, "_async_update_data", AsyncMock(return_value={"devices": [DEVICE]})),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield request


def select_id(hass, suffix: str) -> str:
    return er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{DEVICE['deviceId']}_probe_1_{suffix}")


async def choose(hass, entity_id: str, option: str) -> None:
    await hass.services.async_call("select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True)


async def test_the_selects_exist_beside_the_climate_entity(hass, request_api):
    assert select_id(hass, "meat")
    assert select_id(hass, "doneness")
    climates = hass.states.async_entity_ids("climate")
    assert len(climates) == 1
    assert hass.states.get(climates[0]).state == "heat"


async def test_the_selects_never_read_unknown(hass, request_api):
    assert hass.states.get(select_id(hass, "meat")).state == "Beef"
    assert hass.states.get(select_id(hass, "doneness")).state == "Medium Well"
    request_api.assert_not_awaited()


async def test_starting_up_again_keeps_every_entity(hass, request_api):
    """Setting up doesn't delete and recreate entities, whichever platform loads first."""
    registry = er.async_get(hass)
    entry_id = next(iter(hass.data[DOMAIN]))
    before = {e.entity_id: e.id for e in er.async_entries_for_config_entry(registry, entry_id)}
    assert any(entity_id.startswith("climate.") for entity_id in before)
    assert await hass.config_entries.async_reload(entry_id)
    await hass.async_block_till_done()
    assert {e.entity_id: e.id for e in er.async_entries_for_config_entry(registry, entry_id)} == before


async def test_updates_add_no_more_sensors(hass, request_api):
    coordinator = next(iter(hass.data[DOMAIN].values()))["coordinator"]
    before = len(hass.states.async_entity_ids("sensor"))
    coordinator.async_apply_status_report({**DEVICE["lastStatusCmd"], "deviceId": DEVICE["deviceId"]})
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids("sensor")) == before


async def test_choosing_sets_the_running_cooks_target(hass, request_api):
    await choose(hass, select_id(hass, "meat"), "Beef")
    assert hass.states.get(select_id(hass, "meat")).state == "Beef"
    await choose(hass, select_id(hass, "doneness"), "Medium Well")

    method, path, body = request_api.await_args.args
    assert (method, path) == ("POST", "/app/command/send")
    assert body["cmdData"]["setParams"] == [{"setTemperature": 1500}]
    assert body["cmdData"]["cookUuid"] == "the-cook"


def status_message(tenths: int) -> SimpleNamespace:
    """A status report as the broker delivers it, from the device's topic."""
    probe = {**DEVICE["lastStatusCmd"]["cmdData"]["probes"][0], "curTemperature": tenths}
    payload = {"cmdType": "WT10:status:report", "cmdData": {"globalStatus": "online", "probes": [probe]}}
    return SimpleNamespace(topic=f"device/WT10/{DEVICE['deviceId']}/pub", payload=json.dumps(payload).encode())


async def test_a_status_report_shows_at_once_with_no_refresh(hass, request_api):
    data = hass.data[DOMAIN]
    entry_data = next(iter(data.values()))
    entry_data["api"].coordinator = entry_data["coordinator"]
    climate = hass.states.async_entity_ids("climate")[0]
    hass.config.units = US_CUSTOMARY_SYSTEM
    with patch.object(entry_data["coordinator"], "async_request_refresh", AsyncMock()) as refresh:
        # On the MQTT client's own thread, as a real one arrives
        await hass.async_add_executor_job(entry_data["api"]._on_mqtt_message, None, None, status_message(1000))
        await hass.async_block_till_done()
        assert hass.states.get(climate).attributes["current_temperature"] == 100
        await hass.async_add_executor_job(entry_data["api"]._on_mqtt_message, None, None, status_message(1100))
        await hass.async_block_till_done()
        assert hass.states.get(climate).attributes["current_temperature"] == 110
        refresh.assert_not_awaited()


async def test_a_report_from_an_unknown_device_is_left_to_a_refresh(hass, request_api):
    coordinator = next(iter(hass.data[DOMAIN].values()))["coordinator"]
    with patch.object(coordinator, "async_request_refresh", AsyncMock()) as refresh:
        before = coordinator.data
        coordinator.async_apply_status_report({"deviceId": "another", "cmdData": {}})
        await hass.async_block_till_done()
        refresh.assert_awaited_once()
        assert coordinator.data is before


async def test_the_doneness_options_change_with_the_meat(hass, request_api):
    await choose(hass, select_id(hass, "meat"), "Fish")
    assert hass.states.get(select_id(hass, "doneness")).attributes["options"] == ["Medium", "Well Done"]
