import time
import threading
from queue import Queue
from typing import Dict

from dvrip import DVRIPCam
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "icsee_ptz"

queues: Dict[str, Queue] = {}


def get_q(
    host: str,
    user: str,
    password: str,
) -> Queue:
    key = f"{user}:{password}@{host}"
    q = queues.get(key)
    if not q:
        q = Queue()
        queues[key] = q

        def runner():
            cam = DVRIPCam(host, user=user, password=password)
            try:
                _LOGGER.warn("logging in")
                cam.login()
                while True:
                    task = q.get(timeout=5)
                    task(cam)
            finally:
                _LOGGER.warn("closing")
                queues.pop(key)
                cam.close()

        q_thread = threading.Thread(target=runner)
        q_thread.start()
    return q


instantaneous_commands = [
    "SetPreset",
    "GotoPreset",
    "ClearPreset",
    "StartTour",
    "StopTour",
]


def setup(hass, config):
    def move(call):
        camera = call.data.get("camera", "")
        conf = config[DOMAIN].get(camera, {})

        cmd = call.data.get("cmd", "")
        host = call.data.get("host", conf.get("host", ""))
        password = call.data.get("password", conf.get("password", ""))
        username = call.data.get("username", conf.get("username", "admin"))

        move_time = call.data.get("move_time", conf.get("move_time", 0.5))
        channel = call.data.get("channel", conf.get("channel", 0))
        step = call.data.get("step", conf.get("step", 2))
        preset = call.data.get("preset", conf.get("preset", 0))

        enqueue = call.data.get("enqueue", conf.get("enqueue", False))

        q = get_q(host, username, password)

        if not enqueue:
            while not q.empty():
                q.get()

        if cmd in instantaneous_commands:
            _LOGGER.warn(f"insta {cmd}")
        else:
            _LOGGER.warn(f"LONG {cmd}")
        if cmd in instantaneous_commands:
            q.put(lambda cam: cam.ptz("DirectionUp", preset=-1))  # stop
            q.put(lambda cam: cam.ptz(cmd, step=step, preset=preset, ch=channel))
        else:
            q.put(lambda cam: cam.ptz(cmd, step=step, preset=preset, ch=channel))
            for i in range(0, int(move_time / 0.1)):
                q.put(lambda cam: time.sleep(0.1))
            q.put(lambda cam: cam.ptz("DirectionUp", preset=-1))  # stop

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

    def force_frame(call):
        camera = call.data.get("camera", "")
        conf = config[DOMAIN].get(camera, {})
        host = call.data.get("host", conf.get("host", ""))
        password = call.data.get("password", conf.get("password", ""))
        username = call.data.get("username", conf.get("username", "admin"))

        cam = DVRIPCam(host, user=username, password=password)
        cam.login()
        cam.start_monitor()
        cam.close()

    hass.services.register(DOMAIN, "move", move)
    hass.services.register(DOMAIN, "synchronize_clock", synchronize_clock)
    hass.services.register(DOMAIN, "force_frame", force_frame)

    return True
