# ThermoMaven's protocol

As the ThermoMaven Android app speaks it, read from the app at 1.9.10 (`flow build` unpacks it into `.apks/`). The places below are in its bundled web app (`.apks/web/`) and decompiled native code (`.apks/source/sources/`).

## Reading: MQTT

The broker is AWS IoT, reached with the certificate from `/app/mqtt/cert/apply`. The client subscribes to the topics it's given:

- `app/user/<id>/sub`: `user:device:list`, the devices.
- `device/<model>/<deviceId>/pub`, each device's `subTopics`: `<model>:status:report`, with a device's probes.

These are for listening. Publishing to them gets the client disconnected by the broker, and upstream's QoS 1 commands were sent again on every reconnect.

## Commanding: HTTP

`POST /app/command/send`, signed like every other request, answering `{"code": "0"}` on success (`sendCmdCommonMethod` in `chunk-common`, `Y5/Q0.java`). The native app tries Bluetooth first and falls back on this.

```json
{
  "cmdId": "<a new id>",
  "cmdType": "<model>:cooking:action",
  "deviceId": "<device>",
  "deviceType": "<model>",
  "cmdData": {}
}
```

`cmdId` and `deviceType` come from what the native bridge requires of a command (`DevicesH5RealFragment.java`). The body it builds for HTTP didn't decompile.

### Cook actions

`cookingAction` is `1` start, `2` stop, `4` change resting and `5` finish. The web app builds no stop (2): it ends a cook with finish.

**Start** (`select_device_list`): a new `cookUuid`, and `startClient` is `android` or `ios`. `setTemperature` is in tenths of a degree F.

```json
{
  "probeColor": "probe1",
  "cookingAction": 1,
  "cookingMode": "manual",
  "cookUuid": "<new>",
  "startClient": "android",
  "setParams": [{ "setTemperature": 1500 }],
  "cookingData": { "dataType": "manual", "dataId": "", "dataName": "Manual cook", "dataImgUrl": "" }
}
```

**Change the target** (`probe_detail`): start again, with `probeColor`, `cookingMode`, `cookUuid` and `startClient` as the probe reports them. `cookingData` is `null` when `startClient` is `device`.

**Finish** (`probe_detail`):

```json
{ "probeColor": "probe1", "cookingAction": 5, "cookUuid": "<as reported>" }
```

## States

A probe's `cookingState` is one of `disconnected`, `standby`, `cooking`, `ready`, `remove`, `resting`, `searching`, `charged`, `charging`, `error`, `lost` and `overheat`. Probes are named `probe1` and `probe2` (the enum calls them Dark and Bright). A device's `globalStatus` is `offline`, `online`, `error` or `upgrading`.
