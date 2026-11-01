"""Commands reach a device on the topic its device list named, whatever messages came since."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.thermomaven.thermomaven_api import ThermoMavenAPI

DEVICE = "309302735543533569"
PROBE = {"device_id": DEVICE, "device_type": "WT10", "probe_color": "bright", "target_temperature": 1500}


def message(cmd_type: str, topic: str = "app/user/sub", **data) -> SimpleNamespace:
    """An MQTT message as the broker delivers it."""
    return SimpleNamespace(topic=topic, payload=json.dumps({"cmdType": cmd_type, "cmdData": data}).encode())


@pytest.fixture
def api(hass) -> ThermoMavenAPI:
    """The client, connected to a broker that takes every publish."""
    client = ThermoMavenAPI(hass, "cook@example.com", "password", "key", "app")
    client.mqtt_client = MagicMock()
    client.mqtt_client.publish.return_value = SimpleNamespace(rc=0)
    return client


def published_topics(api: ThermoMavenAPI) -> list[str]:
    return [call.args[0] for call in api.mqtt_client.publish.call_args_list]


def device_list(**device) -> SimpleNamespace:
    return message("user:device:list", devices=[{"deviceId": DEVICE, "deviceModel": "WT10", **device}])


async def test_command_survives_later_messages(api):
    """A status report after the device list doesn't lose the device's topic."""
    api._on_mqtt_message(None, None, device_list(subTopics=[f"app/WT10/{DEVICE}/sub"]))
    api._on_mqtt_message(None, None, message("WT:device:status:report", topic=f"device/WT10/{DEVICE}/pub"))

    assert await api.async_set_probe_temperature(**PROBE)
    assert published_topics(api) == [f"app/WT10/{DEVICE}/pub"]


async def test_named_publish_topic_wins(api):
    api._on_mqtt_message(
        None, None, device_list(pubTopics=["custom/topic/pub"], subTopics=[f"app/WT10/{DEVICE}/sub"])
    )

    assert await api.async_set_probe_temperature(**PROBE)
    assert published_topics(api) == ["custom/topic/pub"]


async def test_topic_from_the_model_when_none_is_listed(api):
    api._on_mqtt_message(None, None, device_list())

    assert await api.async_set_probe_temperature(**PROBE)
    assert published_topics(api) == [f"app/WT10/{DEVICE}/pub"]


async def test_never_guesses_a_topic(api):
    """Before any device list, nothing is published: a wrong topic gets the client dropped."""
    api._on_mqtt_message(None, None, message("WT:device:status:report", topic=f"device/WT10/{DEVICE}/pub"))

    assert not await api.async_set_probe_temperature(**PROBE)
    assert not await api.async_stop_cooking(DEVICE, "WT10", "bright")
    api.mqtt_client.publish.assert_not_called()


async def test_a_new_device_list_replaces_the_topic(api):
    api._on_mqtt_message(None, None, device_list(pubTopics=["old/pub"]))
    api._on_mqtt_message(None, None, device_list(pubTopics=["new/pub"]))

    assert await api.async_set_probe_temperature(**PROBE)
    assert published_topics(api) == ["new/pub"]
