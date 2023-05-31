import time
from dvrip import DVRIPCam

DOMAIN = "icsee_ptz"


def setup(hass, config):
    def move(call):
        camera = call.data.get("camera", "")
        conf = config[DOMAIN].get(camera, {})

        cmd = call.data.get("cmd", "")
        host = call.data.get("host", conf.get("host", ""))
        password = call.data.get("password", conf.get("password", ""))
        username = call.data.get("username", conf.get("username", "admin"))

        move_time = call.data.get("move_time", conf.get("move_time", 0.3))
        channel = call.data.get("channel", conf.get("channel", 0))
        step = call.data.get("step", conf.get("step", 2))
        preset = call.data.get("preset", conf.get("preset", 0))

        cam = DVRIPCam(host, user=username, password=password)
        cam.login()
        cam.ptz(cmd, step=step, preset=preset, ch=channel)
        time.sleep(move_time)
        cam.ptz(cmd)  # stops it
        cam.close()

    def synchronize_clock(call):
        camera = call.data.get("camera", "")
        conf = config[DOMAIN].get(camera, {})
        host = call.data.get("host", conf.get("host", ""))
        password = call.data.get("password", conf.get("password", ""))
        username = call.data.get("username", conf.get("username", "admin"))

        cam = DVRIPCam(host, user=username, password=password)
        cam.login()
        cam.set_time()
        cam.close()

    hass.services.register(DOMAIN, "move", move)
    hass.services.register(DOMAIN, "synchronize_clock", synchronize_clock)

    return True
