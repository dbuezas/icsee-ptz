import time
from dvrip import DVRIPCam

DOMAIN = "icsee_ptz"


def setup(hass, config):

    def move(call):
        cmd = call.data.get("cmd", "")
        host = call.data.get("host", "")
        password = call.data.get("password", "")
        move_time = int(call.data.get("move_time", 0.3))
        username = call.data.get("username", "admin")
        channel = int(call.data.get("channel", 0))
        step = int(call.data.get("step", 2))
        preset = int(call.data.get("preset", 0))

        cam = DVRIPCam(host, user=username, password=password)
        cam.login()
        cam.ptz(cmd, step=step, preset=preset, ch=channel)
        time.sleep(move_time)
        cam.ptz(cmd)  # stops it
        cam.close()

    def synchronize_clock(call):
        host = call.data.get("host", "")
        password = call.data.get("password", "")
        username = call.data.get("username", "admin")

        cam = DVRIPCam(host, user=username, password=password)
        cam.login()
        cam.set_time()
        cam.close()

    hass.services.register(DOMAIN, "move", move)
    hass.services.register(
        DOMAIN, "synchronize_clock", synchronize_clock)

    return True
