"""A probe's climate entity runs its cook, over HTTP, in the app's format (see PROTOCOL.md)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.thermomaven.climate import ThermoMavenClimate
from custom_components.thermomaven.thermomaven_api import MANUAL_COOK, ThermoMavenAPI

DEVICE = "309302735543533569"
RUNNING = {
    "probeColor": "probe1",
    "cookingState": "cooking",
    "cookingMode": "manual",
    "cookUuid": "the-cook",
    "startClient": "android",
    "curTemperature": 793,
    "setParams": [{"setTemperature": 1900}],
}
IDLE = {"probeColor": "probe1", "cookingState": "standby", "curTemperature": 700}


@pytest.fixture
def api(hass) -> ThermoMavenAPI:
    """The client, with a cloud that accepts every request, and a connection that must not publish."""
    client = ThermoMavenAPI(hass, "cook@example.com", "password", "key", "app")
    client._async_request = AsyncMock(return_value={"code": "0"})
    client.mqtt_client = MagicMock()
    return client


def probe_climate(api, probe: dict, status: str = "online", probe_num: int = 1) -> ThermoMavenClimate:
    """A probe's climate entity, given what its device last reported."""
    device = {
        "deviceId": DEVICE,
        "deviceModel": "WT10",
        "lastStatusCmd": {"cmdData": {"globalStatus": status, "probes": [probe]}},
    }
    coordinator = SimpleNamespace(data={"devices": [device]})
    climate = ThermoMavenClimate(coordinator, api, device, probe_num, "entry")
    climate.async_write_ha_state = MagicMock()
    return climate


def sent(api) -> dict:
    """The one command sent, after checking it went over HTTP alone."""
    api.mqtt_client.publish.assert_not_called()
    api._async_request.assert_awaited_once()
    method, path, body = api._async_request.await_args.args
    assert (method, path) == ("POST", "/app/command/send")
    assert body["cmdType"] == "WT10:cooking:action"
    assert body["deviceId"] == DEVICE
    assert body["deviceType"] == "WT10"
    assert body["cmdId"]
    return body["cmdData"]


async def test_a_running_cook_reads_as_on(api):
    climate = probe_climate(api, RUNNING)
    assert climate.hvac_mode == HVACMode.HEAT
    assert climate.current_temperature == 79.3
    assert climate.target_temperature == 190


@pytest.mark.parametrize("state", ["cooking", "ready", "resting", "remove"])
async def test_a_cook_stays_on_until_ended(api, state):
    assert probe_climate(api, {**RUNNING, "cookingState": state}).hvac_mode == HVACMode.HEAT


@pytest.mark.parametrize("state", ["standby", "charged", "charging", "disconnected", "lost", "error", "overheat"])
async def test_other_states_read_as_off(api, state):
    assert probe_climate(api, {**IDLE, "cookingState": state}).hvac_mode == HVACMode.OFF


async def test_a_target_with_no_cook_only_remembers(api):
    climate = probe_climate(api, IDLE)
    await climate.async_set_temperature(temperature=150)
    assert climate.target_temperature == 150
    api._async_request.assert_not_awaited()


async def test_turning_on_starts_a_cook_at_the_target(api):
    climate = probe_climate(api, IDLE)
    await climate.async_set_temperature(temperature=150)
    await climate.async_turn_on()
    data = sent(api)
    assert data["cookUuid"]
    del data["cookUuid"]
    assert data == {
        "probeColor": "probe1",
        "cookingAction": 1,
        "cookingMode": "manual",
        "startClient": "android",
        "setParams": [{"setTemperature": 1500}],
        "cookingData": MANUAL_COOK,
    }


async def test_turning_on_needs_a_target(api):
    with pytest.raises(HomeAssistantError, match="Set a target"):
        await probe_climate(api, IDLE).async_turn_on()
    api._async_request.assert_not_awaited()


async def test_with_no_target_set_a_cook_starts_at_the_default(api):
    climate = probe_climate(api, IDLE)
    climate.default_target = lambda: 150
    assert climate.target_temperature == 150
    await climate.async_turn_on()
    assert sent(api)["setParams"] == [{"setTemperature": 1500}]


async def test_a_set_target_beats_the_default(api):
    climate = probe_climate(api, IDLE)
    climate.default_target = lambda: 150
    await climate.async_set_temperature(temperature=165)
    assert climate.target_temperature == 165


async def test_turning_on_during_a_cook_starts_nothing(api):
    await probe_climate(api, RUNNING).async_turn_on()
    api._async_request.assert_not_awaited()


@pytest.mark.parametrize("state", ["disconnected", "lost", "error"])
async def test_an_unreachable_probe_doesnt_start(api, state):
    climate = probe_climate(api, {**IDLE, "cookingState": state})
    await climate.async_set_temperature(temperature=150)
    with pytest.raises(HomeAssistantError, match=state):
        await climate.async_turn_on()
    api._async_request.assert_not_awaited()


async def test_changing_the_target_changes_the_running_cook(api):
    climate = probe_climate(api, RUNNING)
    await climate.async_set_temperature(temperature=150)
    assert sent(api) == {
        "probeColor": "probe1",
        "cookingAction": 1,
        "cookingMode": "manual",
        "cookUuid": "the-cook",
        "startClient": "android",
        "setParams": [{"setTemperature": 1500}],
        "cookingData": MANUAL_COOK,
    }


async def test_a_cook_started_on_the_device_has_no_cooking_data(api):
    await probe_climate(api, {**RUNNING, "startClient": "device"}).async_set_temperature(temperature=150)
    assert sent(api)["cookingData"] is None


async def test_an_accepted_target_shows_at_once(api):
    climate = probe_climate(api, RUNNING)
    await climate.async_set_temperature(temperature=150)
    assert climate.target_temperature == 150


async def test_a_refused_target_never_shows(api):
    api._async_request.return_value = {"code": "500"}
    climate = probe_climate(api, RUNNING)
    with pytest.raises(HomeAssistantError):
        await climate.async_set_temperature(temperature=150)
    assert climate.target_temperature == 190


def reports(climate, tenths: int) -> None:
    """The device reports a target."""
    climate._probe()["setParams"] = [{"setTemperature": tenths}]


async def test_the_device_takes_over_once_it_reports_the_target(api):
    climate = probe_climate(api, {**RUNNING})
    await climate.async_set_temperature(temperature=150)
    reports(climate, 1500)
    assert climate.target_temperature == 150
    reports(climate, 1600)
    assert climate.target_temperature == 160


async def test_a_target_the_device_never_reports_goes_back(api):
    climate = probe_climate(api, {**RUNNING})
    with patch("custom_components.thermomaven.climate.time.monotonic", return_value=1000.0):
        await climate.async_set_temperature(temperature=150)
    with patch("custom_components.thermomaven.climate.time.monotonic", return_value=1029.0):
        assert climate.target_temperature == 150
    with patch("custom_components.thermomaven.climate.time.monotonic", return_value=1030.0):
        assert climate.target_temperature == 190
    assert climate.target_temperature == 190


async def test_turning_off_finishes_the_cook(api):
    await probe_climate(api, RUNNING).async_turn_off()
    assert sent(api) == {"probeColor": "probe1", "cookingAction": 5, "cookUuid": "the-cook"}


async def test_turning_off_with_no_cook_sends_nothing(api):
    await probe_climate(api, IDLE).async_turn_off()
    api._async_request.assert_not_awaited()


async def test_a_refusal_is_an_error(api):
    api._async_request.return_value = {"code": "500", "msg": "no"}
    with pytest.raises(HomeAssistantError, match="refused"):
        await probe_climate(api, RUNNING).async_set_temperature(temperature=150)


async def test_an_offline_device_gets_no_command(api):
    with pytest.raises(HomeAssistantError, match="offline"):
        await probe_climate(api, RUNNING, status="offline").async_turn_off()
    api._async_request.assert_not_awaited()


async def test_a_probe_is_found_by_its_name(api):
    """A second probe reads its own part of the status, whatever order the report lists them in."""
    second = {**RUNNING, "probeColor": "probe2", "curTemperature": 1000}
    climate = probe_climate(api, second, probe_num=2)
    assert climate.current_temperature == 100
    assert probe_climate(api, second).current_temperature is None


async def test_status_presets_are_gone(api):
    climate = probe_climate(api, RUNNING)
    assert climate.hvac_modes == [HVACMode.OFF, HVACMode.HEAT]
    assert not climate.supported_features & ClimateEntityFeature.PRESET_MODE
