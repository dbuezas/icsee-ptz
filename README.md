[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/dbuezas)

# ICSee PTZ control integration for Home Assistant

Home Assistant integration for ICSee/XMEye/DVR-IP/NetSurveillance/Sofia cameras.

- Live video (main and sub stream), played by Home Assistant's built-in go2rtc
- Motion alarm
- PTZ: move, zoom, presets
- Camera settings as entities: infrared / day-night mode, white light, frame rate, resolution, quality, image flip and colors, motion detection and tracking, volume, status LED, privacy mode and more
- Camera speaker as a media player (e.g. for text-to-speech)
- Security: cloud (P2P) access, cloud push, password reset options
- Finds cameras on your network by itself

Each camera only gets the entities it supports. Requires Home Assistant 2025.10 or newer.

# Installation

### Option 1: [HACS](https://hacs.xyz/) Link

1. Click [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dbuezas&repository=icsee-ptz&category=integration)
2. Restart Home Assistant

### Option 2: [HACS](https://hacs.xyz/)

1. Or `HACS` > `Integrations` > `⋮` > `Custom Repositories`
2. `Repository`: paste the url of this repo
3. `Category`: Integration
4. Click `Add`
5. Close `Custom Repositories` modal
6. Click `+ EXPLORE & DOWNLOAD REPOSITORIES`
7. Search for `icsee`
8. Click `Download`
9. Restart _Home Assistant_

### Option 2: Manual copy

1. Copy the `icsee_ptz` folder inside `custom_components` of this repo to `/config/custom_components` in your Home Assistant instance
2. Restart _Home Assistant_

# Configuration

Cameras on your network are found automatically and show up under
`Settings -> Devices & services -> Discovered`. You can also add one by hand.
You only need the camera password (the one set in the ICSee/XMEye app).

The port is usually 34567. Only change it if your camera uses a different one (e.g. behind port forwarding).

[![Open your Home Assistant instance and show an integration.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=icsee_ptz)

<img width="447" alt="image" src="https://github.com/dbuezas/icsee-ptz/assets/777196/1853de8a-85c1-4578-8932-11a0923d4dd8" width="350">

# Usage

This integration creates a device per camera with a motion alarm, camera entities,
PTZ buttons, settings, and the `icsee_ptz.move` action for PTZ. 

## Motion alarm

First make sure to enable and configure motion alarms in the standard camera application (e.g ICSee or XMEye).
Then, you can use the provided entity in your automations.

<img width="350" alt="image" src="https://github.com/dbuezas/icsee-ptz/assets/777196/06ef6fd4-e04c-4c06-83e1-724db6d65b05">

## Pan, tilt, zoom (PTZ)

icsee_ptz.move: move, zoom and set/goto preseets.


Test PTZ control from [![Developer Tools / Services.](https://my.home-assistant.io/badges/developer_services.svg)](https://my.home-assistant.io/redirect/developer_services/).

<img width="350" alt="image" src="https://github.com/dbuezas/icsee-ptz/assets/777196/18941eed-c370-428d-b2fd-31db13a21bc7">

## Example automation

```yaml
alias: Notify camera motion alarm
description: ""
trigger:
  - platform: state
    entity_id:
      - binary_sensor.garden_motion_alarm
    to: "on"
condition: []
action:
  - service: notify.mobile_app_pixel_7
    data:
      message: TTS
      data:
        tts_text: Attention: motion detected in garden
        ttl: 0
        priority: high
mode: single

```

# Usage in [WebRTC card](https://github.com/AlexxIT/WebRTC):

<img src="https://github.com/dbuezas/icsee-ptz/assets/777196/36674140-11bf-438c-ba68-159a9d422158"  width="350">

```yaml
# lovelace card
type: custom:webrtc-camera
url: garden_dvrip
ui: true
shortcuts:
  services:
    - name: Sync
      icon: mdi:clock-check
      service: icsee_ptz.synchronize_clock
      service_data:
        entity_id: binary_sensor.garten_motion_alarm
    - name: Force frame
      icon: mdi:play
      service: icsee_ptz.force_frame
      service_data:
        entity_id: binary_sensor.garten_motion_alarm
ptz:
  service: icsee_ptz.move
  data_home:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: GotoPreset
    preset: 0
  data_long_home:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: SetPreset
    preset: 0
  data_left_start:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: DirectionLeft
  data_left_end:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: Stop
  data_right_start:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: DirectionRight
  data_right_end:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: Stop
  data_down_start:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: DirectionDown
  data_down_end:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: Stop
  data_up_start:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: DirectionUp
  data_up_end:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: Stop

```

# Video

Each camera gets a `camera.*_main_stream` and a `camera.*_sub_stream` entity. Home Assistant
plays them through its built-in go2rtc; you don't need to configure anything.
Snapshots come from the stream too.

If you prefer your own go2rtc, these streams work there as well:

```yaml
# go2rtc.yaml
streams:
  garden_dvrip:
    - dvrip://admin:my_password@192.168.178.104:34567
  garden_dvrip_mini:
    - dvrip://admin:my_password@192.168.178.104:34567?channel=0&subtype=1
  garden: # try this if the video is choppy or audio is out of synch
    - ffmpeg:garden_dvrip#audio=copy#async#video=copy#async
```

# Entities

Entities only appear if the camera supports them. Less common ones are disabled by default;
enable them in the device page.

| Area | Entities |
| --- | --- |
| Alarm | `binary_sensor.*_motion_alarm` |
| Video | `camera.*_main_stream`, `camera.*_sub_stream` |
| PTZ | `button.*_ptz_*`, `button.*_home_*` (options: channel, speed, preset) |
| Lights | `select.*_day_night_mode` (auto / always color = infrared off / always black & white = infrared on / ...), `select.*_white_light_mode`, `switch.*_white_light`, white light brightness, motion sensitivity and duration |
| Video settings | frame rate, resolution, quality, codec, bitrate (main and sub stream) |
| Image | flip, mirror, brightness, contrast, saturation, anti-fog, day/night sensitivity |
| Detection | motion / human / tamper / video loss detection, motion sensitivity, motion tracking |
| Audio | `media_player.*_speaker` (TTS and sounds), speaker volume |
| Other | status LED, voice prompts, privacy mode, sleep schedule, `button.*_restart`, `button.*_synchronize_clock` |
| Security | `switch.*_cloud_access_p2p`, `switch.*_cloud_push_notifications`, password reset indicators, `sensor.*_extra_users` |

The frame rate and resolution are checked against the camera's encoding limit before they are saved.

## Security

- **Cloud access (P2P)**: the XMEye/ICSee cloud connection that lets the apps reach the camera from
  anywhere. Turn it off if you only use the camera at home.
- **Password reset**: the apps can reset the camera password with security questions, a code sent by
  email/phone, or (on some cameras) a code. The indicators show if questions or an email/phone are set.
- **Extra users**: the apps add a hidden account to the camera. This sensor shows how many exist.

## Upgrading from 4.x

- Entity IDs stay the same.
- The "experimental entities" option is gone: all supported entities are created.
- The options of the day/night and white light selects changed names (e.g. `KeepOpen` -> `keep_open`).
  Update automations that use `select.select_option` with the old names.
- The `move`, `synchronize_clock` and `force_frame` actions still target the motion alarm entity.

# Miscelaneous

Frame rate and encoding can now be set from Home Assistant. The Windows app
https://xmeye.org/xmeye-for-pc/ can still change settings this integration does not cover.

## Recommended configuration:

in `device config` / `encode config` select:

- fps: 30 (maximum available)
- Iframe interval: 1 (minimum available)
- Static encode config: high profile
- H264+ enable: disabled

in `device config` / `camera param` select:

- Clear fog: ON
- Level: 100
