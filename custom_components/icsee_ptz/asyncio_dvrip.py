import os
import struct
import json
import hashlib
import asyncio
from datetime import *
from re import compile
import time
import logging


class SomethingIsWrongWithCamera(Exception):
    pass


class ConfigNotSupported(Exception):
    """The camera does not have this config or ability."""

    def __init__(self, name, ret=None):
        super().__init__(f"{name} is not supported (Ret {ret})")
        self.name = name
        self.ret = ret


class CommandFailed(Exception):
    """The camera answered with an error code."""

    def __init__(self, name, ret):
        super().__init__(f"{name} failed with Ret {ret}")
        self.name = name
        self.ret = ret


class DVRIPCam(object):
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    CODES = {
        100: "OK",
        101: "Unknown error",
        102: "Unsupported version",
        103: "Request not permitted",
        104: "User already logged in",
        105: "User is not logged in",
        106: "Username or password is incorrect",
        107: "User does not have necessary permissions",
        203: "Password is incorrect",
        511: "Start of upgrade",
        512: "Upgrade was not started",
        513: "Upgrade data errors",
        514: "Upgrade error",
        515: "Upgrade successful",
    }
    QCODES = {
        "AuthorityList": 1470,
        "Users": 1472,
        "Groups": 1474,
        "AddGroup": 1476,
        "ModifyGroup": 1478,
        "DelGroup": 1480,
        "AddUser": 1482,
        "ModifyUser": 1484,
        "DelUser": 1486,
        "ModifyPassword": 1488,
        "AlarmInfo": 1504,
        "AlarmSet": 1500,
        "ChannelTitle": 1046,
        "EncodeCapability": 1360,
        "General": 1042,
        "KeepAlive": 1006,
        "OPMachine": 1450,
        "OPMailTest": 1636,
        "OPMonitor": 1413,
        "OPNetKeyboard": 1550,
        "OPPTZControl": 1400,
        "OPSNAP": 1560,
        "OPSendFile": 0x5F2,
        "OPSystemUpgrade": 0x5F5,
        "OPTalk": 1434,
        "OPTimeQuery": 1452,
        "OPTimeSetting": 1450,
        "NetWork.NetCommon": 1042,
        "OPNetAlarm": 1506,
        "SystemFunction": 1360,
        "SystemInfo": 1020,
    }
    KEY_CODES = {
        "M": "Menu",
        "I": "Info",
        "E": "Esc",
        "F": "Func",
        "S": "Shift",
        "L": "Left",
        "U": "Up",
        "R": "Right",
        "D": "Down",
    }
    OK_CODES = [100, 515]
    PORTS = {
        "tcp": 34567,
        "udp": 34568,
    }

    def __init__(self, ip, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.ip = ip
        self.user = kwargs.get("user", "admin")
        self.hash_pass = kwargs.get(
            "hash_pass", self.sofia_hash(kwargs.get("password", ""))
        )
        self.proto = kwargs.get("proto", "tcp")
        self.port = kwargs.get("port", self.PORTS.get(self.proto))
        self.socket_reader = None
        self.socket_writer = None
        self.packet_count = 0
        self.session = 0
        self.alive_time = 20
        self.alarm_func = None
        self.timeout = 10
        self.busy = asyncio.Lock()
        self.login_ret = None

    def debug(self, format=None):
        self.logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        if format:
            formatter = logging.Formatter(format)
            ch.setFormatter(formatter)
        self.logger.addHandler(ch)

    async def connect(self, timeout=10):
        try:
            if self.proto == "tcp":
                self.socket_reader, self.socket_writer = await asyncio.wait_for(
                    asyncio.open_connection(self.ip, self.port), timeout=timeout
                )
                self.socket_send = self.tcp_socket_send
                self.socket_recv = self.tcp_socket_recv
            elif self.proto == "udp":
                raise f"Unsupported protocol {self.proto} (yet)"
            else:
                raise f"Unsupported protocol {self.proto}"

            # it's important to extend timeout for upgrade procedure
            self.timeout = timeout
        except OSError:
            raise SomethingIsWrongWithCamera("Cannot connect to camera")

    def close(self):
        try:
            self.socket_writer.close()
        except:
            pass
        self.socket_writer = None

    def tcp_socket_send(self, bytes):
        try:
            return self.socket_writer.write(bytes)
        except:
            return None

    async def tcp_socket_recv(self, bufsize):
        try:
            return await self.socket_reader.read(bufsize)
        except:
            return None

    async def receive_with_timeout(self, length):
        received = 0
        buf = bytearray()
        start_time = time.time()

        while True:
            try:
                data = await asyncio.wait_for(
                    self.socket_recv(length - received), timeout=self.timeout
                )
                if not data:
                    return None
                buf.extend(data)
                received += len(data)
                if length == received:
                    break
                elapsed_time = time.time() - start_time
                if elapsed_time > self.timeout:
                    return None
            except asyncio.TimeoutError:
                return None
        return buf

    async def receive_json(self, length):
        data = await self.receive_with_timeout(length)
        if data is None:
            return {}

        self.packet_count += 1
        self.logger.debug("<= %s", data)
        reply = json.loads(data[:-2])
        return reply

    async def send(self, msg, data={}, wait_response=True):
        if self.socket_writer is None:
            return {"Ret": 101}
        async with self.busy:
            return await self._send_locked(msg, data, wait_response)

    async def _send_locked(self, msg, data, wait_response):
        if hasattr(data, "__iter__"):
            data = bytes(json.dumps(data, ensure_ascii=False), "utf-8")
        pkt = (
            struct.pack(
                "BB2xII2xHI",
                255,
                0,
                self.session,
                self.packet_count,
                msg,
                len(data) + 2,
            )
            + data
            + b"\x0a\x00"
        )
        self.logger.debug("=> %s", pkt)
        self.socket_send(pkt)
        if wait_response:
            data = await self.receive_with_timeout(20)
            if data is None:
                return None
            (
                head,
                version,
                self.session,
                sequence_number,
                msgid,
                len_data,
            ) = struct.unpack("BB2xII2xHI", data)
            reply = await self.receive_json(len_data)
            return reply or None

    def sofia_hash(self, password=""):
        md5 = hashlib.md5(bytes(password, "utf-8")).digest()
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        return "".join([chars[sum(x) % 62] for x in zip(md5[::2], md5[1::2])])

    async def login(self, loop):
        if self.socket_writer is None:
            await self.connect()
        data = await self.send(
            1000,
            {
                "EncryptType": "MD5",
                "LoginType": "DVRIP-Web",
                "PassWord": self.hash_pass,
                "UserName": self.user,
            },
        )
        self.login_ret = None if data is None else data.get("Ret")
        if data is None or data["Ret"] not in self.OK_CODES:
            return False
        self.session = int(data["SessionID"], 16)
        self.alive_time = data["AliveInterval"]
        self.keep_alive(loop)
        return data["Ret"] in self.OK_CODES

    async def getAuthorityList(self):
        data = await self.send(self.QCODES["AuthorityList"])
        if data["Ret"] in self.OK_CODES:
            return data["AuthorityList"]
        else:
            return []

    async def getGroups(self):
        data = await self.send(self.QCODES["Groups"])
        if data["Ret"] in self.OK_CODES:
            return data["Groups"]
        else:
            return []

    async def addGroup(self, name, comment="", auth=None):
        data = await self.set_command(
            "AddGroup",
            {
                "Group": {
                    "AuthorityList": auth or await self.getAuthorityList(),
                    "Memo": comment,
                    "Name": name,
                },
            },
        )
        return data["Ret"] in self.OK_CODES

    async def modifyGroup(self, name, newname=None, comment=None, auth=None):
        g = [x for x in await self.getGroups() if x["Name"] == name]
        if g == []:
            print(f'Group "{name}" not found!')
            return False
        g = g[0]
        data = await self.send(
            self.QCODES["ModifyGroup"],
            {
                "Group": {
                    "AuthorityList": auth or g["AuthorityList"],
                    "Memo": comment or g["Memo"],
                    "Name": newname or g["Name"],
                },
                "GroupName": name,
            },
        )
        return data["Ret"] in self.OK_CODES

    async def delGroup(self, name):
        data = await self.send(
            self.QCODES["DelGroup"],
            {
                "Name": name,
                "SessionID": "0x%08X" % self.session,
            },
        )
        return data["Ret"] in self.OK_CODES

    async def getUsers(self):
        data = await self.send(self.QCODES["Users"])
        if data["Ret"] in self.OK_CODES:
            return data["Users"]
        else:
            return []

    async def addUser(
        self, name, password, comment="", group="user", auth=None, sharable=True
    ):
        g = [x for x in await self.getGroups() if x["Name"] == group]
        if g == []:
            print(f'Group "{group}" not found!')
            return False
        g = g[0]
        data = await self.set_command(
            "AddUser",
            {
                "User": {
                    "AuthorityList": auth or g["AuthorityList"],
                    "Group": g["Name"],
                    "Memo": comment,
                    "Name": name,
                    "Password": self.sofia_hash(password),
                    "Reserved": False,
                    "Sharable": sharable,
                },
            },
        )
        return data["Ret"] in self.OK_CODES

    async def modifyUser(
        self, name, newname=None, comment=None, group=None, auth=None, sharable=None
    ):
        u = [x for x in self.getUsers() if x["Name"] == name]
        if u == []:
            print(f'User "{name}" not found!')
            return False
        u = u[0]
        if group:
            g = [x for x in await self.getGroups() if x["Name"] == group]
            if g == []:
                print(f'Group "{group}" not found!')
                return False
            u["AuthorityList"] = g[0]["AuthorityList"]
        data = await self.send(
            self.QCODES["ModifyUser"],
            {
                "User": {
                    "AuthorityList": auth or u["AuthorityList"],
                    "Group": group or u["Group"],
                    "Memo": comment or u["Memo"],
                    "Name": newname or u["Name"],
                    "Password": "",
                    "Reserved": u["Reserved"],
                    "Sharable": sharable or u["Sharable"],
                },
                "UserName": name,
            },
        )
        return data["Ret"] in self.OK_CODES

    async def delUser(self, name):
        data = await self.send(
            self.QCODES["DelUser"],
            {
                "Name": name,
                "SessionID": "0x%08X" % self.session,
            },
        )
        return data["Ret"] in self.OK_CODES

    async def changePasswd(self, newpass="", oldpass=None, user=None):
        data = await self.send(
            self.QCODES["ModifyPassword"],
            {
                "EncryptType": "MD5",
                "NewPassWord": self.sofia_hash(newpass),
                "PassWord": oldpass or self.password,
                "SessionID": "0x%08X" % self.session,
                "UserName": user or self.user,
            },
        )
        return data["Ret"] in self.OK_CODES

    async def channel_title(self, titles):
        if isinstance(titles, str):
            titles = [titles]
        await self.send(
            self.QCODES["ChannelTitle"],
            {
                "ChannelTitle": titles,
                "Name": "ChannelTitle",
                "SessionID": "0x%08X" % self.session,
            },
        )

    async def channel_bitmap(self, width, height, bitmap):
        header = struct.pack("HH12x", width, height)
        self.socket_send(
            struct.pack(
                "BB2xII2xHI",
                255,
                0,
                self.session,
                self.packet_count,
                0x041A,
                len(bitmap) + 16,
            )
            + header
            + bitmap
        )
        reply, rcvd = await self.recv_json()
        if reply and reply["Ret"] != 100:
            return False
        return True

    async def reboot(self):
        await self.set_command("OPMachine", {"Action": "Reboot"})
        self.close()

    def setAlarm(self, func):
        self.alarm_func = func

    def clearAlarm(self):
        self.alarm_func = None

    async def alarmStart(self, loop):
        loop.create_task(self.alarm_worker())

        return await self.get_command("", self.QCODES["AlarmSet"])

    async def alarm_worker(self):
        while True:
            await self.busy.acquire()
            try:
                (
                    head,
                    version,
                    session,
                    sequence_number,
                    msgid,
                    len_data,
                ) = struct.unpack("BB2xII2xHI", await self.socket_recv(20))
                await asyncio.sleep(0.1)  # Just for receive whole packet
                reply = await self.socket_recv(len_data)
                self.packet_count += 1
                reply = json.loads(reply[:-2])
                if msgid == self.QCODES["AlarmInfo"] and self.session == session:
                    if self.alarm_func is not None:
                        self.alarm_func(reply[reply["Name"]], sequence_number)
            except:
                self.close()
                return

            finally:
                self.busy.release()

    async def set_remote_alarm(self, state):
        await self.set_command(
            "OPNetAlarm",
            {"Event": 0, "State": state},
        )

    async def keep_alive_workner(self):
        while self.socket_writer:

            ret = await self.send(
                self.QCODES["KeepAlive"],
                {"Name": "KeepAlive", "SessionID": "0x%08X" % self.session},
            )
            if ret is None:
                self.close()
                break

            await asyncio.sleep(self.alive_time)

    def keep_alive(self, loop):
        loop.create_task(self.keep_alive_workner())

    async def keyDown(self, key):
        await self.set_command(
            "OPNetKeyboard",
            {"Status": "KeyDown", "Value": key},
        )

    async def keyUp(self, key):
        await self.set_command(
            "OPNetKeyboard",
            {"Status": "KeyUp", "Value": key},
        )

    async def keyPress(self, key):
        await self.keyDown(key)
        await asyncio.sleep(0.3)
        await self.keyUp(key)

    async def keyScript(self, keys):
        for k in keys:
            if k != " " and k.upper() in self.KEY_CODES:
                await self.keyPress(self.KEY_CODES[k.upper()])
            else:
                await asyncio.sleep(1)

    async def ptz(self, cmd, step=5, preset=-1, ch=0):
        CMDS = [
            "DirectionUp",
            "DirectionDown",
            "DirectionLeft",
            "DirectionRight",
            "DirectionLeftUp",
            "DirectionLeftDown",
            "DirectionRightUp",
            "DirectionRightDown",
            "ZoomTile",
            "ZoomWide",
            "FocusNear",
            "FocusFar",
            "IrisSmall",
            "IrisLarge",
            "SetPreset",
            "GotoPreset",
            "ClearPreset",
            "StartTour",
            "StopTour",
        ]
        # ptz_param = { "AUX" : { "Number" : 0, "Status" : "On" }, "Channel" : ch, "MenuOpts" : "Enter", "POINT" : { "bottom" : 0, "left" : 0, "right" : 0, "top" : 0 }, "Pattern" : "SetBegin", "Preset" : -1, "Step" : 5, "Tour" : 0 }
        ptz_param = {
            "AUX": {"Number": 0, "Status": "On"},
            "Channel": ch,
            "MenuOpts": "Enter",
            "Pattern": "Start",
            "Preset": preset,
            "Step": step,
            "Tour": 1 if "Tour" in cmd else 0,
        }
        return await self.set_command(
            "OPPTZControl",
            {"Command": cmd, "Parameter": ptz_param},
        )

    async def set_info(self, command, data):
        return await self.set_command(command, data, 1040)

    async def set_command(self, command, data, code=None):
        if not code:
            code = self.QCODES[command]
        return await self.send(
            code, {"Name": command, "SessionID": "0x%08X" % self.session, command: data}
        )

    async def get_info(self, command):
        return await self.get_command(command, 1042)

    async def get_command(self, command, code=None):
        if not code:
            code = self.QCODES[command]

        data = await self.send(
            code, {"Name": command, "SessionID": "0x%08X" % self.session}
        )
        if data is None:
            raise SomethingIsWrongWithCamera("No reply from camera")
        if data["Ret"] in self.OK_CODES and command in data:
            return data[command]
        else:
            return data

    async def get_time(self):
        return datetime.strptime(
            await self.get_command("OPTimeQuery"), self.DATE_FORMAT
        )

    async def set_time(self, time=None):
        if time is None:
            time = datetime.now()
        return await self.set_command("OPTimeSetting", time.strftime(self.DATE_FORMAT))

    async def get_netcommon(self):
        return await self.get_command("NetWork.NetCommon")

    async def get_system_info(self):
        return await self.get_command("SystemInfo")

    async def get_general_info(self):
        return await self.get_command("General")

    async def get_encode_capabilities(self):
        return await self.get_command("EncodeCapability")

    async def get_system_capabilities(self):
        return await self.get_command("SystemFunction")

    async def get_camera_info(self, default_config=False):
        """Request data for 'Camera' from  the target DVRIP device."""
        if default_config:
            code = 1044
        else:
            code = 1042
        return await self.get_command("Camera", code)

    async def get_encode_info(self, default_config=False):
        """Request data for 'Simplify.Encode' from the target DVRIP device.

        Arguments:
        default_config -- returns the default values for the type if True
        """
        if default_config:
            code = 1044
        else:
            code = 1042
        return await self.get_command("Simplify.Encode", code)

    async def recv_json(self, buf=bytearray()):
        p = compile(b".*({.*})")

        packet = await self.socket_recv(0xFFFF)
        if not packet:
            return None, buf
        buf.extend(packet)
        m = p.search(buf)
        if m is None:
            return None, buf
        buf = buf[m.span(1)[1] :]
        return json.loads(m.group(1)), buf

    async def get_upgrade_info(self):
        return await self.get_command("OPSystemUpgrade")

    async def upgrade(self, filename="", packetsize=0x8000, vprint=None):
        if not vprint:
            vprint = lambda x: print(x)

        data = await self.set_command(
            "OPSystemUpgrade", {"Action": "Start", "Type": "System"}, 0x5F0
        )
        if data["Ret"] not in self.OK_CODES:
            return data

        vprint("Ready to upgrade")
        blocknum = 0
        sentbytes = 0
        fsize = os.stat(filename).st_size
        rcvd = bytearray()
        with open(filename, "rb") as f:
            while True:
                bytes = f.read(packetsize)
                if not bytes:
                    break
                header = struct.pack(
                    "BB2xII2xHI", 255, 0, self.session, blocknum, 0x5F2, len(bytes)
                )
                self.socket_send(header + bytes)
                blocknum += 1
                sentbytes += len(bytes)

                reply, rcvd = await self.recv_json(rcvd)
                if reply and reply["Ret"] != 100:
                    vprint("Upgrade failed")
                    return reply

                progress = sentbytes / fsize * 100
                vprint(f"Uploaded {progress:.2f}%")
        vprint("End of file")

        pkt = struct.pack("BB2xIIxBHI", 255, 0, self.session, blocknum, 1, 0x05F2, 0)
        self.socket_send(pkt)
        vprint("Waiting for upgrade...")
        while True:
            reply, rcvd = await self.recv_json(rcvd)
            print(reply)
            if not reply:
                return
            if reply["Name"] == "" and reply["Ret"] == 100:
                break

        while True:
            data, rcvd = await self.recv_json(rcvd)
            print(reply)
            if data is None:
                vprint("Done")
                return
            if data["Ret"] in [512, 514, 513]:
                vprint("Upgrade failed")
                return data
            if data["Ret"] == 515:
                vprint("Upgrade successful")
                self.close()
                return data
            vprint(f"Upgraded {data['Ret']}%")

    async def reassemble_bin_payload(self, metadata={}):
        def internal_to_type(data_type, value):
            if data_type == 0x1FC or data_type == 0x1FD:
                if value == 1:
                    return "mpeg4"
                elif value == 2:
                    return "h264"
                elif value == 3:
                    return "h265"
            elif data_type == 0x1F9:
                if value == 1 or value == 6:
                    return "info"
            elif data_type == 0x1FA:
                if value == 0xE:
                    return "g711a"
            elif data_type == 0x1FE and value == 0:
                return "jpeg"
            return None

        def internal_to_datetime(value):
            second = value & 0x3F
            minute = (value & 0xFC0) >> 6
            hour = (value & 0x1F000) >> 12
            day = (value & 0x3E0000) >> 17
            month = (value & 0x3C00000) >> 22
            year = ((value & 0xFC000000) >> 26) + 2000
            return datetime(year, month, day, hour, minute, second)

        length = 0
        buf = bytearray()
        start_time = time.time()

        while True:
            data = await self.receive_with_timeout(20)
            (
                head,
                version,
                session,
                sequence_number,
                total,
                cur,
                msgid,
                len_data,
            ) = struct.unpack("BB2xIIBBHI", data)
            packet = await self.receive_with_timeout(len_data)
            frame_len = 0
            if length == 0:
                media = None
                frame_len = 8
                (data_type,) = struct.unpack(">I", packet[:4])
                if data_type == 0x1FC or data_type == 0x1FE:
                    frame_len = 16
                    (
                        media,
                        metadata["fps"],
                        w,
                        h,
                        dt,
                        length,
                    ) = struct.unpack("BBBBII", packet[4:frame_len])
                    metadata["width"] = w * 8
                    metadata["height"] = h * 8
                    metadata["datetime"] = internal_to_datetime(dt)
                    if data_type == 0x1FC:
                        metadata["frame"] = "I"
                elif data_type == 0x1FD:
                    (length,) = struct.unpack("I", packet[4:frame_len])
                    metadata["frame"] = "P"
                elif data_type == 0x1FA:
                    media, samp_rate, length = struct.unpack("BBH", packet[4:frame_len])
                elif data_type == 0x1F9:
                    media, n, length = struct.unpack("BBH", packet[4:frame_len])
                # special case of JPEG shapshots
                elif data_type == 0xFFD8FFE0:
                    return packet
                else:
                    raise ValueError(data_type)
                if media is not None:
                    metadata["type"] = internal_to_type(data_type, media)
            buf.extend(packet[frame_len:])
            length -= len(packet) - frame_len
            if length == 0:
                return buf
            elapsed_time = time.time() - start_time
            if elapsed_time > self.timeout:
                return None

    async def snapshot(self, channel=0):
        command = "OPSNAP"
        await self.send(
            self.QCODES[command],
            {
                "Name": command,
                "SessionID": "0x%08X" % self.session,
                command: {"Channel": channel},
            },
            wait_response=False,
        )
        packet = await self.reassemble_bin_payload()
        return packet

    async def start_monitor(self, frame_callback, user={}, stream="Main"):
        params = {
            "Channel": 0,
            "CombinMode": "NONE",
            "StreamType": stream,
            "TransMode": "TCP",
        }
        data = await self.set_command(
            "OPMonitor", {"Action": "Claim", "Parameter": params}
        )
        if data["Ret"] not in self.OK_CODES:
            return data

        await self.send(
            1410,
            {
                "Name": "OPMonitor",
                "SessionID": "0x%08X" % self.session,
                "OPMonitor": {"Action": "Start", "Parameter": params},
            },
            wait_response=False,
        )
        self.monitoring = True
        while self.monitoring:
            meta = {}
            frame = await self.reassemble_bin_payload(meta)
            frame_callback(frame, meta, user)

    def stop_monitor(self):
        self.monitoring = False

    # ---- Helpers used by the Home Assistant integration ----

    async def get_config(self, name):
        """Read a config (cmd 1042). Raise ConfigNotSupported if the camera lacks it."""
        return self._config_value(name, await self._request(1042, name))

    async def get_value(self, name, code):
        """Read a value with another command, e.g. 1020 (status) or 1472 (users)."""
        return self._config_value(name, await self._request(code, name))

    async def get_ability(self, name):
        """Read an ability (cmd 1360). Raise ConfigNotSupported if the camera lacks it."""
        return self._config_value(name, await self._request(1360, name))

    async def set_config(self, name, value):
        """Write a whole config (cmd 1040). Return the DVRIP return code."""
        reply = await self.send(
            1040, {"Name": name, "SessionID": "0x%08X" % self.session, name: value}
        )
        if reply is None:
            raise SomethingIsWrongWithCamera("No reply from camera")
        ret = reply.get("Ret")
        if ret not in self.OK_CODES and ret != 603:
            raise CommandFailed(name, ret)
        return ret

    async def remote_ctrl(self, ctrl_type, msg):
        """OPRemoteCtrl (cmd 4000), e.g. the manual siren."""
        reply = await self.send(
            4000,
            {
                "Name": "OPRemoteCtrl",
                "SessionID": "0x%08X" % self.session,
                "OPRemoteCtrl": {
                    "Type": ctrl_type,
                    "msg": msg,
                    "P1": "0x00000000",
                    "P2": "0x00000000",
                },
            },
        )
        if reply is None:
            raise SomethingIsWrongWithCamera("No reply from camera")
        if reply.get("Ret") not in self.OK_CODES:
            raise CommandFailed("OPRemoteCtrl", reply.get("Ret"))

    async def talk(self, alaw: bytes, packet_size=320):
        """Play 8 kHz mono G.711 A-law audio on the camera speaker.

        Protocol as in go2rtc (pkg/dvrip): OPTalk Claim (1434), Start (1430),
        then OPTalkData (1432) packets with an 8 byte media header.
        Use a dedicated connection: the camera keeps it busy while talking.
        """
        talk = {"Action": "Claim", "AudioFormat": {"EncodeType": "G711_ALAW"}}
        reply = await self.send(
            1434,
            {"Name": "OPTalk", "SessionID": "0x%08X" % self.session, "OPTalk": talk},
        )
        if reply is None:
            raise SomethingIsWrongWithCamera("No reply from camera")
        if reply.get("Ret") not in self.OK_CODES:
            raise CommandFailed("OPTalk", reply.get("Ret"))
        talk = {**talk, "Action": "Start"}
        await self.send(
            1430,
            {"Name": "OPTalk", "SessionID": "0x%08X" % self.session, "OPTalk": talk},
            wait_response=False,
        )
        header = (
            struct.pack(">I", 0x1FA) + bytes([14, 2]) + struct.pack("<H", packet_size)
        )
        loop = asyncio.get_running_loop()
        start = loop.time()
        for i, pos in enumerate(range(0, len(alaw), packet_size)):
            chunk = alaw[pos : pos + packet_size].ljust(
                packet_size, b"\xd5"
            )  # A-law silence
            self._write_raw(1432, header + chunk)
            # pace in real time, staying up to 4 packets (160 ms) ahead
            delay = start + (i - 4) * packet_size / 8000 - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
        await asyncio.sleep(max(0, start + len(alaw) / 8000 - loop.time()))

    async def _request(self, code, name):
        reply = await self.send(
            code, {"Name": name, "SessionID": "0x%08X" % self.session}
        )
        if reply is None:
            raise SomethingIsWrongWithCamera("No reply from camera")
        return reply

    def _config_value(self, name, reply):
        ret = reply.get("Ret")
        if ret in (103, 607):
            raise ConfigNotSupported(name, ret)
        if ret not in self.OK_CODES:
            raise CommandFailed(name, ret)
        value = reply.get(name)
        if value is None or value == [None]:
            raise ConfigNotSupported(name, ret)
        return value

    def _write_raw(self, msg, payload: bytes):
        if self.socket_writer is None:
            raise SomethingIsWrongWithCamera("Not connected")
        self.socket_writer.write(
            struct.pack(
                "BB2xII2xHI", 255, 0, self.session, self.packet_count, msg, len(payload)
            )
            + payload
        )
        self.packet_count += 1
