[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/dbuezas)

# ICSee PTZ control integration for Home Assistant

Home Assistant integration to send ptz commands to ICSee/XMEye/DVR-IP/NetSurveillance/Sofia cameras.

It can also set presets and recall them and synchronize the camera clock.

# Installation

~~Method 1. HACS > Integrations > Plus > ICSee-PTZ > Install~~ (**not yet possible**)

Method 2. Manually copy icsee-ptz folder from latest release to /config/custom_components folder.

# Configuration

Add this to your `configuration.yaml`

```yaml
# configuration.yaml
icsee_ptz:
  my_dvrip_camera:
    host: 192.168.178.27
    password: my_cam_password
    step: 10 # speed
    move_time: 10
```

Requires:

- WebRTC integration v3.2.0 - 2023-07-11

# Usage

This integration exposes two new services. Test them from the [![Developer Tools / Services.](https://my.home-assistant.io/badges/developer_services.svg)](https://my.home-assistant.io/redirect/developer_services/).

## icsee_ptz.move: move, zoom and set/goto preseets.

<img src="https://github.com/dbuezas/icsee-ptz/assets/777196/14ec2cb6-ef39-4249-aa63-e7044a2d6221"  width="350">

## icsee_ptz.synchronize_clock: updates the camera's clock.

<img src="https://github.com/dbuezas/icsee-ptz/assets/777196/ec114a00-8b78-4a3c-82cb-27807266be49"  width="350">

# Usage in [WebRTC card](https://github.com/AlexxIT/WebRTC):

<img src="https://github.com/dbuezas/icsee-ptz/assets/777196/36674140-11bf-438c-ba68-159a9d422158"  width="350">

```yaml
# lovelace card
type: custom:webrtc-camera
url: my_dvrip_camera
muted: false
intersection: 0
ui: true
digital_ptz: null
shortcuts:
  services:
    - name: Sync
      icon: mdi:clock-check
      service: icsee_ptz.synchronize_clock
      service_data:
        camera: my_dvrip_camera
    - name: Force frame # force keyframe
      icon: mdi:play
      service: icsee_ptz.force_frame
      service_data:
        camera: my_dvrip_camera
ptz:
  service: icsee_ptz.move
  data_home:
    camera: my_dvrip_camera
    cmd: GotoPreset
    preset: 0
  data_long_home:
    camera: my_dvrip_camera
    cmd: SetPreset
    preset: 0
  data_start_left:
    camera: my_dvrip_camera
    cmd: DirectionLeft
  data_end_left:
    camera: my_dvrip_camera
    cmd: DirectionLeft
    move_time: 0
  data_start_right:
    camera: my_dvrip_camera
    cmd: DirectionRight
  data_end_right:
    camera: my_dvrip_camera
    cmd: DirectionRight
    move_time: 0
  data_start_up:
    camera: my_dvrip_camera
    cmd: DirectionUp
  data_end_up:
    camera: my_dvrip_camera
    cmd: DirectionUp
    move_time: 0
  data_start_down:
    camera: my_dvrip_camera
    cmd: DirectionDown
  data_end_down:
    camera: my_dvrip_camera
    cmd: DirectionDown
    move_time: 0
```

# Video stream from [go2rtc](https://github.com/AlexxIT/go2rtc)

```yaml
# go2rtc.yaml
streams:
  my_dvrip_camera: dvrip://admin:my_cam_password@192.168.178.27:34567
```

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
