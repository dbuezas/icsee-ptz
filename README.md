[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/dbuezas)

# ICSee PTZ control integration for Home Assistant

Home Assistant integration to send ptz commands to ICSee/DVR-IP/NetSurveillance/Sofia cameras.

# Installation

~~Method 1. HACS > Integrations > Plus > WebRTC > Install~~ (**not yet possible**)

Method 2. Manually copy icsee-ptz folder from latest release to /config/custom_components folder.

# Configuration

Add this to your `configuration.yaml`

```yaml
icsee_ptz:
```

# Usage

This integration exposes two new services. Test them from the [![Developer Tools / Services.](https://my.home-assistant.io/badges/developer_services.svg)](https://my.home-assistant.io/redirect/developer_services/).

- icsee_ptz.move: move, zoom and set/goto preseets.
- icsee_ptz.synchronize_clock: updates the camera's clock.

# Usage in [WebRTC card](https://github.com/AlexxIT/WebRTC):

![image](https://github.com/dbuezas/icsee-ptz/assets/777196/36674140-11bf-438c-ba68-159a9d422158)

```yaml
type: custom:webrtc-camera
url: camarablanca
shortcuts:
  services:
    - name: Record
      icon: mdi:clock-check
      service: icsee_ptz.synchronize_clock
      service_data:
        host: 192.168.178.27
        password: camarablanca3
    - name: Record
      icon: mdi:floppy
      service: icsee_ptz.move
      service_data:
        host: 192.168.178.27
        cmd: SetPreset
        preset: 2
        password: camarablanca3
    - name: Record
      icon: mdi:backup-restore
      service: icsee_ptz.move
      service_data:
        host: 192.168.178.27
        cmd: GotoPreset
        preset: 2
        password: camarablanca3
ptz:
  service: icsee_ptz.move
  data_home:
    host: 192.168.178.27
    cmd: GotoPreset
    preset: 1
    password: camarablanca3
  data_zoom_in:
    host: 192.168.178.27
    password: camarablanca3
    move_time: 1
    step: 10
    cmd: ZoomTile
  data_zoom_out:
    host: 192.168.178.27
    password: camarablanca3
    move_time: 1
    step: 10
    cmd: ZoomFar
  data_left:
    host: 192.168.178.27
    password: camarablanca3
    move_time: 1
    step: 10
    cmd: DirectionRight
  data_right:
    host: 192.168.178.27
    password: camarablanca3
    move_time: 1
    step: 10
    cmd: DirectionLeft
  data_up:
    host: 192.168.178.27
    password: camarablanca3
    move_time: 1
    step: 10
    cmd: DirectionUp
  data_down:
    host: 192.168.178.27
    password: camarablanca3
    move_time: 1
    step: 10
    cmd: DirectionDown
```

# Video stream from [go2rtc](https://github.com/AlexxIT/go2rtc)

```yaml
# go2rtc.yaml
streams:
  camara:
    - dvrip://admin:camarablanca3@192.168.178.27:34567?channel=0&subtype=0
  if_you_dont_get_video_or_audio:
    - dvrip://admin:camarablanca3@192.168.178.27:34567?channel=0&subtype=0
    - ffmpeg:antena#video=h264#hardware#audio=copy
```