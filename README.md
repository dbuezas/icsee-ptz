[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/dbuezas)

# ICSee PTZ control integration for Home Assistant

Home Assistant integration to send ptz commands to ICSee/DVR-IP/NetSurveillance/Sofia cameras.

It can also set presets and recall them and synchronize the camera clock.

# Installation

~~Method 1. HACS > Integrations > Plus > WebRTC > Install~~ (**not yet possible**)

Method 2. Manually copy icsee-ptz folder from latest release to /config/custom_components folder.

# Configuration

Add this to your `configuration.yaml`

```yaml
icsee_ptz:
  my_cam_1:
    host: 192.168.178.27
    password: my_cam_password
    move_time: 1
    step: 10
```

# Usage

This integration exposes two new services. Test them from the [![Developer Tools / Services.](https://my.home-assistant.io/badges/developer_services.svg)](https://my.home-assistant.io/redirect/developer_services/).

## icsee_ptz.move: move, zoom and set/goto preseets.

<img src="https://github.com/dbuezas/icsee-ptz/assets/777196/14ec2cb6-ef39-4249-aa63-e7044a2d6221"  width="350">

## icsee_ptz.synchronize_clock: updates the camera's clock.

<img src="https://github.com/dbuezas/icsee-ptz/assets/777196/ec114a00-8b78-4a3c-82cb-27807266be49"  width="350">

# Usage in [WebRTC card](https://github.com/AlexxIT/WebRTC):

<img src="https://github.com/dbuezas/icsee-ptz/assets/777196/36674140-11bf-438c-ba68-159a9d422158"  width="350">

```yaml
type: custom:webrtc-camera
url: camarablanca
shortcuts:
  services:
    - name: Record
      icon: mdi:clock-check
      service: icsee_ptz.synchronize_clock
      service_data:
        camera: my_cam_1
    - name: Record
      icon: mdi:floppy
      service: icsee_ptz.move
      service_data:
        camera: my_cam_1
        cmd: SetPreset
        preset: 2
    - name: Record
      icon: mdi:backup-restore
      service: icsee_ptz.move
      service_data:
        camera: my_cam_1
        cmd: GotoPreset
        preset: 2
ptz:
  service: icsee_ptz.move
  data_home:
    camera: my_cam_1
    cmd: GotoPreset
    preset: 1
  data_zoom_in:
    camera: my_cam_1
    cmd: ZoomTile
  data_zoom_out:
    camera: my_cam_1
    cmd: ZoomFar
  data_left:
    camera: my_cam_1
    cmd: DirectionRight
  data_right:
    camera: my_cam_1
    cmd: DirectionLeft
  data_up:
    camera: my_cam_1
    cmd: DirectionUp
  data_down:
    camera: my_cam_1
    step: 5 # this overrides the default in the configuration.yaml
    cmd: DirectionDown
```

# Video stream from [go2rtc](https://github.com/AlexxIT/go2rtc)

```yaml
# go2rtc.yaml
streams:
  camara:
    - dvrip://admin:my_cam_password@192.168.178.27:34567
  if_you_dont_get_video_or_audio:
    - dvrip://admin:my_cam_password@192.168.178.27:34567
    - ffmpeg:antena#video=h264#hardware#audio=copy
```

# Miscelaneous

From a windows computer and that old software, you can configure the fps and encoding params of ICSee cameras. I suggest you increase the fps from 12 to 30 and change the color profile from 2 to 1, they feel like better cameras. 
Here's a video that shows the software involved: https://www.youtube.com/watch?v=KFX47EUpP24
