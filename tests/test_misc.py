"""Encode budget, diagnostics and DVRIP protocol helpers."""

from __future__ import annotations

import asyncio
import json
import struct

import pytest

from homeassistant.core import HomeAssistant

from custom_components.icsee_ptz import encode
from custom_components.icsee_ptz.asyncio_dvrip import (
    ConfigNotSupported,
    DVRIPCam,
    SomethingIsWrongWithCamera,
)
from custom_components.icsee_ptz.device import ICSeeDevice
from custom_components.icsee_ptz.const import DOMAIN
from custom_components.icsee_ptz.diagnostics import async_get_config_entry_diagnostics

from .conftest import FIXTURES


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def test_garten_budget_is_exact() -> None:
    data = _fixture("garten")
    capability = data["abilities"]["EncodeCapability"]
    enc = data["configs"]["Simplify.Encode"][0]
    # 3M (2048x1536) @ 25 + D1 (704x576) @ 25 == MaxEncodePowerPerChannel
    assert encode.load(enc, ntsc=False) == encode.budget(capability, 0)
    assert encode.fits(capability, enc, 0, ntsc=False)
    enc["ExtraFormat"]["Video"]["FPS"] = 26  # one frame more is too much
    assert not encode.fits(capability, enc, 0, ntsc=False)


def test_resolution_options() -> None:
    garten = _fixture("garten")
    hiseeu = _fixture("hiseeu")
    g_cap, g_enc = (
        garten["abilities"]["EncodeCapability"],
        garten["configs"]["Simplify.Encode"][0],
    )
    h_cap, h_enc = (
        hiseeu["abilities"]["EncodeCapability"],
        hiseeu["configs"]["Simplify.Encode"][0],
    )
    assert encode.resolution_options(g_cap, g_enc, encode.MAIN, 0) == [
        "720P",
        "1080P",
        "3M",
    ]
    assert encode.resolution_options(h_cap, h_enc, encode.MAIN, 0) == ["3M", "4M"]
    assert encode.compression_options(g_cap, g_enc, encode.MAIN) == ["H.264"]
    assert encode.compression_options(h_cap, h_enc, encode.MAIN) == ["H.264", "H.265"]
    # Hiseeu fits 4M@25 with its sub stream at 12 fps
    h_enc["MainFormat"]["Video"]["Resolution"] = "4M"
    assert encode.fits(h_cap, h_enc, 0, ntsc=False)


async def test_diagnostics_redacted(hass: HomeAssistant, setup_integration) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    text = json.dumps(diag)
    assert "secret" not in text
    assert "0123456789abcdef" not in text
    assert "192.0.2.10" not in text
    assert "hiddenpass" not in text
    assert "192.0.2.200" not in text
    assert "daspass" not in text and "dasuser" not in text and "das.example" not in text
    assert "Camera.WhiteLight" in diag["configs"]


class _Writer:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data += data

    def close(self) -> None:
        pass


def _packets(data: bytes) -> list[tuple[int, bytes]]:
    out = []
    while data:
        head = struct.unpack("BB2xII2xHI", data[:20])
        msgid, length = head[4], head[5]
        out.append((msgid, data[20 : 20 + length]))
        data = data[20 + length :]
    return out


async def test_talk_packets(monkeypatch: pytest.MonkeyPatch) -> None:
    cam = DVRIPCam("192.0.2.1")
    cam.socket_writer = _Writer()
    sent = []

    async def fake_send(msg, data=None, wait_response=True):
        sent.append((msg, data))
        return {"Ret": 100} if wait_response else None

    monkeypatch.setattr(cam, "send", fake_send)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    await cam.talk(b"\x01" * 700)
    assert [m for m, _ in sent] == [1434, 1430]
    assert sent[0][1]["OPTalk"]["Action"] == "Claim"
    packets = _packets(bytes(cam.socket_writer.data))
    assert [m for m, _ in packets] == [1432, 1432, 1432]  # 700 bytes -> 3 x 320
    header = packets[0][1][:8]
    assert header == struct.pack(">I", 0x1FA) + bytes([14, 2]) + struct.pack("<H", 320)
    assert packets[-1][1][8:].endswith(b"\xd5")  # padded with A-law silence


async def _no_sleep(*_args) -> None:
    return None


async def test_get_config_not_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    cam = DVRIPCam("192.0.2.1")

    async def fake_send(msg, data=None, wait_response=True):
        name = data["Name"]
        if name == "Missing":
            return {"Name": name, "Ret": 607, name: None}
        if name == "Null":
            return {"Name": name, "Ret": 100, name: [None]}
        return {"Name": name, "Ret": 100, name: {"a": 1}}

    monkeypatch.setattr(cam, "send", fake_send)
    assert await cam.get_config("Ok") == {"a": 1}
    for name in ("Missing", "Null"):
        with pytest.raises(ConfigNotSupported):
            await cam.get_config(name)


def test_stream_max_fps() -> None:
    garten = _fixture("garten")
    g_cap, g_enc = (
        garten["abilities"]["EncodeCapability"],
        garten["configs"]["Simplify.Encode"][0],
    )
    assert encode.stream_max_fps(g_cap, g_enc, encode.MAIN, 0, ntsc=False) == 25
    assert encode.stream_max_fps(g_cap, g_enc, encode.SUB, 0, ntsc=False) == 25
    hiseeu = _fixture("hiseeu")
    h_cap, h_enc = (
        hiseeu["abilities"]["EncodeCapability"],
        hiseeu["configs"]["Simplify.Encode"][0],
    )
    h_enc["MainFormat"]["Video"]["Resolution"] = "4M"
    # 4M@25 leaves room for D1 at only 12 fps on the sub stream
    assert encode.stream_max_fps(h_cap, h_enc, encode.SUB, 0, ntsc=False) == 12
    # budget alone would allow 31 fps at 3M, but PAL caps it at 25
    h_enc["MainFormat"]["Video"]["Resolution"] = "3M"
    assert encode.stream_max_fps(h_cap, h_enc, encode.MAIN, 0, ntsc=False) == 25


def test_parse_playlist() -> None:
    from custom_components.icsee_ptz.media_player import parse_playlist

    m3u = "#EXTM3U\n#EXTINF:-1,hr3\nhttp://dispatcher.example/hr3/stream.mp3\n"
    assert parse_playlist(m3u) == "http://dispatcher.example/hr3/stream.mp3"
    pls = "[playlist]\nNumberOfEntries=1\nFile1=https://radio.example/live\nTitle1=x\n"
    assert parse_playlist(pls) == "https://radio.example/live"
    assert parse_playlist("#EXTM3U\n") is None


async def test_talk_stream_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    cam = DVRIPCam("192.0.2.1")
    cam.socket_writer = _Writer()

    async def fake_send(msg, data=None, wait_response=True):
        return {"Ret": 100} if wait_response else None

    async def chunks():
        for size in (100, 500, 1000, 7):  # odd sizes, 1607 bytes in total
            yield b"\x02" * size

    monkeypatch.setattr(cam, "send", fake_send)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    await cam.talk_stream(chunks())
    packets = _packets(bytes(cam.socket_writer.data))
    assert len(packets) == 6  # ceil(1607 / 320)
    assert all(len(p) == 8 + 320 for _, p in packets)


def test_aes_body_matches_real_capture() -> None:
    """Decrypt the encrypted CMD_1000 captured from a real device (equake MITM)."""
    from custom_components.icsee_ptz.asyncio_dvrip import (
        _aes_decrypt_body,
        _aes_encrypt_body,
    )

    captured = "rfIQlMaR6Ses2pRV7x9RcqLQDOs9GDPH7FuY0jxaWEwOBvxOE2S7iMQgSIJbivkE"
    plain = _aes_decrypt_body(captured.encode())
    assert plain.startswith(b'{"EncryptType":"MD5","LoginType":"DVRIP-Xm030","')
    # re-encrypting the recovered plaintext reproduces the capture byte-for-byte
    assert _aes_encrypt_body(plain)[: len(captured)] == captured.encode()
    # round-trip of an arbitrary body
    body = b'{"Name":"Camera.Param"}\x0a\x00'
    assert _aes_decrypt_body(_aes_encrypt_body(body)).rstrip(b"\x00") == body.rstrip(
        b"\x00"
    )


class _Loopback:
    """A minimal socket_writer/reader pair for one request/response."""

    def __init__(self) -> None:
        self.sent = b""

    def write(self, data: bytes) -> None:
        self.sent += data


async def test_send_encrypts_and_decrypts(monkeypatch: pytest.MonkeyPatch) -> None:
    from custom_components.icsee_ptz.asyncio_dvrip import (
        _aes_decrypt_body,
        _aes_encrypt_body,
    )

    cam = DVRIPCam("192.0.2.1")
    cam.encrypt_on = True
    cam.not_encrypt = {1006}  # keepalive stays plain
    writer = _Loopback()
    cam.socket_writer = writer
    cam.socket_send = writer.write

    # queue an encrypted reply for the request
    reply_json = b'{"Name":"Camera.Param","Ret":100}'
    reply_body = _aes_encrypt_body(reply_json + b"\x0a\x00") + b"\x00"
    queue = [
        struct.pack("<BB2xII2xHI", 255, 1, 7, 0, 1042, len(reply_body)),
        reply_body,
    ]

    async def fake_recv(n):
        return bytearray(queue.pop(0))

    monkeypatch.setattr(cam, "receive_with_timeout", fake_recv)
    out = await cam.send(1042, {"Name": "Camera.Param"})
    assert out == {"Name": "Camera.Param", "Ret": 100}

    # the request went out encrypted: version byte 1, body is base64 + NUL
    assert writer.sent[1] == 1  # version byte
    body = writer.sent[20:]
    assert body.endswith(b"\x00")
    assert _aes_decrypt_body(body.rstrip(b"\x00")).startswith(
        b'{"Name": "Camera.Param"}'
    )


async def test_send_plain_when_encryption_off(monkeypatch: pytest.MonkeyPatch) -> None:
    cam = DVRIPCam("192.0.2.1")
    writer = _Loopback()
    cam.socket_writer = writer
    cam.socket_send = writer.write
    reply = b'{"Ret":100}\x0a\x00'
    queue = [struct.pack("<BB2xII2xHI", 255, 0, 7, 0, 1043, len(reply)), reply]

    async def fake_recv(n):
        return bytearray(queue.pop(0))

    monkeypatch.setattr(cam, "receive_with_timeout", fake_recv)
    out = await cam.send(1042, {"Name": "Camera.Param"})
    assert out == {"Ret": 100}
    assert writer.sent[1] == 0  # version byte 0
    assert writer.sent[20:].endswith(b"\x0a\x00")  # plain body, no base64


@pytest.mark.parametrize(
    ("plain_reply", "negotiates"),
    [({"Ret": 100}, False), ({}, True), (None, False)],
)
async def test_encryption_only_negotiated_on_empty_answer(
    plain_reply, negotiates
) -> None:
    """Only an empty answer means "wants encryption"; no answer means "busy".

    The negotiation claims a video stream, which blocks talking (OPTalk Ret 103).
    """
    cam = DVRIPCam("192.0.2.1")
    cam.socket_writer = object()
    sent = []

    async def send(msg, data={}, wait_response=True, keep_empty=False):
        sent.append(msg)
        if msg == 1000:
            return {"Ret": 100, "SessionID": "0x00000001", "AliveInterval": 20}
        if msg == 1020:
            return plain_reply
        return {"Ret": 100}

    cam.send = send
    cam.keep_alive = lambda loop: None
    assert await cam.login(asyncio.get_running_loop())
    assert (1413 in sent) is negotiates


@pytest.mark.parametrize(
    "login_reply",
    [{"SessionID": "0x00000001"}, {"Ret": 100}, {"Ret": 100, "SessionID": "not-hex"}],
)
async def test_login_without_ret_or_session_fails_cleanly(login_reply) -> None:
    """Some cameras answer the login without "Ret" or "SessionID"."""
    cam = DVRIPCam("192.0.2.1")
    cam.socket_writer = object()

    async def send(msg, data={}, wait_response=True, keep_empty=False):
        return login_reply

    cam.send = send
    cam.keep_alive = lambda loop: None
    assert await cam.login(asyncio.get_running_loop()) is False


class _FakeCam:
    """Minimal stand-in for DVRIPCam for _detect_channels."""

    def __init__(self, motion=None, err=None) -> None:
        self._motion = motion
        self._err = err

    async def get_config(self, name):
        assert name == "Detect.MotionDetect"
        if self._err:
            raise self._err
        return self._motion


async def test_detect_channels_from_motiondetect_length() -> None:
    """A DVR's channel count is the length of the per-channel MotionDetect list."""
    dev = ICSeeDevice("h", 34567, "u", "p")
    cam = _FakeCam(motion=[{} for _ in range(8)])
    # SystemInfo says 1, but the MotionDetect list (8) wins (regression #70)
    assert await dev._detect_channels(cam, {"VideoInChannel": 1}) == 8


async def test_detect_channels_falls_back_to_systeminfo() -> None:
    dev = ICSeeDevice("h", 34567, "u", "p")
    missing = _FakeCam(err=ConfigNotSupported("Detect.MotionDetect"))
    assert (
        await dev._detect_channels(missing, {"VideoInChannel": 4, "DigChannel": 0}) == 4
    )
    broken = _FakeCam(err=SomethingIsWrongWithCamera("x"))
    assert (
        await dev._detect_channels(broken, {"VideoInChannel": 8, "DigChannel": 8}) == 16
    )
    # empty list is not a real answer, and nothing else is known -> at least 1
    assert await dev._detect_channels(_FakeCam(motion=[]), {}) == 1


def test_channel_subdevice_has_no_via_device() -> None:
    """Channel sub-devices must not use via_device (it breaks camera add on newer HA, #70)."""
    from types import SimpleNamespace

    from homeassistant.const import CONF_MAC, CONF_UNIQUE_ID
    from custom_components.icsee_ptz.const import CONF_CHANNEL_COUNT
    from custom_components.icsee_ptz.entity import ICSeeEntity

    entry = SimpleNamespace(
        data={CONF_UNIQUE_ID: "abc", CONF_CHANNEL_COUNT: 4},
        title="Garten",
    )
    coordinator = SimpleNamespace(config_entry=entry, system_info={}, device=object())
    entity = ICSeeEntity(coordinator, "camera_main_1", channel=1)
    assert entity._attr_device_info is not None
    assert "via_device" not in entity._attr_device_info
    # channel 0 stays the main device
    main = ICSeeEntity(coordinator, "camera_main_0", channel=0)
    assert (DOMAIN, "abc") in main._attr_device_info["identifiers"]
