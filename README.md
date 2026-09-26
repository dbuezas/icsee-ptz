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

Entities only appear if the camera supports them.

| Entity | Type | What it does |
| --- | --- | --- |
| **Alarm and video** | | |
| Motion alarm | binary_sensor | On while the camera reports an alarm (motion, human, ...). Enable alarms in the ICSee/XMEye app first. Also the target of the `icsee_ptz.move` action. |
| Main stream / Sub stream | camera | Live video in high / low quality. Played by Home Assistant's go2rtc; snapshots come from the stream. |
| **PTZ** | | |
| PTZ up / down / left / right / stop | button | Move the camera. Speed = the Step option. |
| PTZ diagonal moves, zoom in / out | button | Only useful on cameras that support them. |
| Home go to / Home set current position | button | Go to / save the preset from the options (default 0). |
| Home clear | button | Delete that preset. |
| **Lights and night vision** | | |
| Day/night mode | select | When the camera uses infrared (IR). **Auto**: IR at night. **Always color**: IR never turns on (dark at night). **Always black & white**: IR always on. Cameras with a white light also offer *white light on motion* and *full color at night*. |
| White light | switch | Turn the white light on / off by hand (sets the white light mode to *Always on* / *Off*). |
| White light mode | select | *Off*, *Always on*, *Auto* (at night), *Schedule*, *On motion*. On IR + white light cameras this is also the night vision mode: *Auto* = full color, *Off* = infrared. |
| White light brightness / motion duration / motion sensitivity | number/select | Brightness, and how long and how easily the light turns on in *On motion* mode. |
| Day/night switch sensitivity | number | 0-10. How early the camera switches to night mode. |
| Day/night switch | select | Newer cameras only: force day or night, or use a schedule. |
| Night vision, night vision enhancement, low light fill, light sensor threshold | switch/number | Newer cameras only. |
| Starlight mode | switch | Low light boost. |
| IR cut filter reversed | switch | Only for cameras whose day/night filter works the wrong way round. |
| **Video settings (main and sub stream)** | | |
| Resolution | select | Only sizes the camera offers. |
| Frame rate | number | The maximum follows the camera's encoding limit and the video standard (25 PAL / 30 NTSC). |
| Quality | select | *Bad* ... *Best*. Higher = better picture, more data. |
| Codec | select | H.264 / H.265 (if the camera has both). H.265 uses less data but not every player supports it. |
| Bitrate, bitrate control, key frame interval | number/select | Advanced. The official apps don't change these. |
| Sub stream, main / sub stream audio | switch | Turn the sub stream or the audio in a stream off. |
| **Image** | | |
| Flip image / Mirror image | switch | For cameras mounted upside down or reversed. |
| Image brightness / contrast / saturation | number | Picture colors. |
| Image hue, image style, anti-fog, wide dynamic range, prevent overexposure | number/select/switch | Fine tuning. |
| **Detection** | | |
| Motion detection / Human detection | switch | Turn the camera's detection on / off (this is what triggers the motion alarm). |
| Motion sensitivity | number | 1 (low) - 6 (high). |
| Motion tracking, tracking sensitivity, tracking return time | switch/select/number | PTZ cameras that follow people, and when they return to the start position. |
| Tamper detection / Video loss detection | switch | Alarm when the camera is covered / loses video. |
| **Audio** | | |
| Speaker | media_player | Play text-to-speech or sounds on the camera speaker. |
| Speaker volume / Microphone volume | number |  |
| **Other** | | |
| Status LED / Voice prompts | switch | The LED and the spoken messages of the camera ("device connected", ...). |
| Privacy mode | switch | Blacks out the video. |
| Sleep schedule | switch | The camera's own sleep schedule (set times in the app). |
| Restart / Synchronize clock | button | Restart the camera / set its clock to the Home Assistant time. |
| Siren | siren | Only on cameras with a built-in alarm siren. |
| **Security** | | |
| Cloud access (P2P) | switch | The XMEye/ICSee cloud connection that lets the apps reach the camera from anywhere. Turn it off if you only use it at home. |
| Cloud push notifications | switch | Alarm messages to the phone app. |
| Password reset by security questions / email or phone set | binary_sensor | On if someone can reset the camera password with security answers / a code sent by email or phone. |
| Password reset by code | switch | Only on cameras that have it. |
| Extra users | sensor | Hidden accounts the apps create on the camera. The names are in the `users` attribute. |

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
