"""The integration set up for real, on a fake account: the selects find their climate entity and drive the cook."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
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


async def test_choosing_sets_the_running_cooks_target(hass, request_api):
    await choose(hass, select_id(hass, "meat"), "Beef")
    assert hass.states.get(select_id(hass, "meat")).state == "Beef"
    await choose(hass, select_id(hass, "doneness"), "Medium Well")

    method, path, body = request_api.await_args.args
    assert (method, path) == ("POST", "/app/command/send")
    assert body["cmdData"]["setParams"] == [{"setTemperature": 1500}]
    assert body["cmdData"]["cookUuid"] == "the-cook"


async def test_the_doneness_options_change_with_the_meat(hass, request_api):
    await choose(hass, select_id(hass, "meat"), "Fish")
    assert hass.states.get(select_id(hass, "doneness")).attributes["options"] == ["Medium", "Well Done"]
