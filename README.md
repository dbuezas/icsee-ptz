[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/dbuezas)

# ICSee PTZ control integration for Home Assistant

Home Assistant integration to send ptz commands to ICSee/XMEye/DVR-IP/NetSurveillance/Sofia cameras.

It can also set presets and recall them and synchronize the camera clock.

# Installation

### Option 1: [HACS](https://hacs.xyz/) Link

1. Click [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=David+Buezas+&repository=https%3A%2F%2Fgithub.com%2Fdbuezas%2Ficsee-ptz&category=Integration)
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

Go to the integration and add an entry for each of your cameras

[![Open your Home Assistant instance and show an integration.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=icsee_ptz)

<img width="447" alt="image" src="https://github.com/dbuezas/icsee-ptz/assets/777196/1853de8a-85c1-4578-8932-11a0923d4dd8" width="350">

# Usage

This integration exposes services for PTZ and a motion alarm entity. 

## Motion alarm

First make sure to enable and configure motion alarms in the standard camera application (e.g ICSee or XMEye).
Then, you can use the provided entity in your automations.

<img width="350" alt="image" src="https://github.com/dbuezas/icsee-ptz/assets/777196/06ef6fd4-e04c-4c06-83e1-724db6d65b05">

## Pan, tilt, zoom (PTZ)

icsee_ptz.move: move, zoom and set/goto preseets.

Requires:

- WebRTC integration v3.2.0 - 2023-07-11


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
  data_start_left:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: DirectionLeft
  data_end_left:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: Stop
  data_start_right:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: DirectionRight
  data_end_right:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: Stop
  data_start_down:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: DirectionDown
  data_end_down:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: Stop
  data_start_up:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: DirectionUp
  data_end_up:
    entity_id: binary_sensor.garten_motion_alarm
    cmd: Stop

```

# Video stream from [go2rtc](https://github.com/AlexxIT/go2rtc)

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

> [!NOTE]  
> There are some disabled entities, But you can enable them on 
>
> `Settings -> Devices & Services -> ICSee -> Configure -> Enable experimental entities`

| Entity                                    | Description                                                              | Enabled by default |
| ----------------------------------------- | ------------------------------------------------------------------------ | ------------------ |
| `switch.*_blinddetect_enabled`            |                                                                          | No                 |
| `select.*_whith_light`                    | You can control camera's lights.                                         | No                 |
| `switch.*_humandetection_enabled`         |                                                                          | No                 |
| `switch.*_lossdetect_enabled`             |                                                                          | No                 |
| `binary_sensor.*_varanda_motion_alarm`    | It will be trigged when someone pass on front of camera.                 | Yes                |
| `switch.*_motiondetect_enabled`           |                                                                          | No                 |

# Miscelaneous

With https://xmeye.org/xmeye-for-pc/ you can configure the fps and encoding params of ICSee cameras.

## Recommended configuration:

in `device config` / `encode config` select:

- fps: 30 (maximum available)
- Iframe interval: 1 (minimum available)
- Static encode config: high profile
- H264+ enable: disabled

in `device config` / `camera param` select:

- Clear fog: ON
- Level: 100
