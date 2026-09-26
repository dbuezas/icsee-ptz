"""Encode budget, diagnostics and DVRIP protocol helpers."""

from __future__ import annotations

import asyncio
import json
import struct

import pytest

from homeassistant.core import HomeAssistant

from custom_components.icsee_ptz import encode
from custom_components.icsee_ptz.asyncio_dvrip import ConfigNotSupported, DVRIPCam
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
