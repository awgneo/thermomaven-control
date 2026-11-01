"""Each probe's area and ambient sensors read that probe, and the first keeps its IDs."""

from types import SimpleNamespace

from custom_components.thermomaven.sensor import (
    ThermoMavenAmbientTemperatureSensor,
    ThermoMavenAreaTemperatureSensor,
)

DEVICE = {
    "deviceId": "1",
    "deviceModel": "WT07",
    "lastStatusCmd": {
        "cmdData": {
            "globalStatus": "online",
            "probes": [
                {"areaTemperature": [320], "curAmbientTemperature": 320},
                {"areaTemperature": [2120], "curAmbientTemperature": 2120},
            ],
        }
    },
}


def coordinator():
    return SimpleNamespace(data={"devices": [DEVICE]})


async def test_the_first_probe_keeps_its_ids():
    assert ThermoMavenAreaTemperatureSensor(coordinator(), DEVICE, 1, "entry").unique_id == "1_area_1"
    assert ThermoMavenAmbientTemperatureSensor(coordinator(), DEVICE, "entry").unique_id == "1_ambient_temp"


async def test_a_second_probe_has_its_own():
    area = ThermoMavenAreaTemperatureSensor(coordinator(), DEVICE, 1, "entry", 2)
    ambient = ThermoMavenAmbientTemperatureSensor(coordinator(), DEVICE, "entry", 2)
    assert area.unique_id == "1_probe_2_area_1"
    assert ambient.unique_id == "1_probe_2_ambient_temp"
    assert area.native_value == 100
    assert ambient.native_value == 100


async def test_the_first_probe_reads_its_own():
    assert ThermoMavenAreaTemperatureSensor(coordinator(), DEVICE, 1, "entry").native_value == 0
    assert ThermoMavenAmbientTemperatureSensor(coordinator(), DEVICE, "entry").native_value == 0
