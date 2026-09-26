"""Find DVRIP cameras on the local network (UDP broadcast, like go2rtc)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import socket

_LOGGER = logging.getLogger(__name__)

PORT = 34569
PROBE = bytes.fromhex("ff00000000000000000000000000fa0500000000")


@dataclass(frozen=True)
class DiscoveredCamera:
    host: str
    port: int
    serial: str
    name: str
    mac: str | None
    channels: int


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.found: dict[str, DiscoveredCamera] = {}

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) <= 21 or data[0] != 0xFF:
            return
        try:
            msg = json.loads(data[20:].rstrip(b"\x00\x0a").decode(errors="replace"))
            info = msg["NetWork.NetCommon"]
            host = ".".join(
                str(b) for b in int(info["HostIP"], 16).to_bytes(4, "little")
            )
            camera = DiscoveredCamera(
                host=host,
                port=int(info.get("TCPPort") or 34567),
                serial=str(info["SN"]),
                name=str(info.get("HostName") or host),
                mac=info.get("MAC"),
                channels=int(info.get("ChannelNum") or 1),
            )
        except (ValueError, KeyError, TypeError, OverflowError):
            return
        self.found[camera.serial] = camera


def _socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", port))
    sock.setblocking(False)
    return sock


async def async_discover(timeout: float = 2) -> list[DiscoveredCamera]:
    """Broadcast a probe and collect the answers."""
    try:
        sock = _socket(PORT)  # cameras answer to the broadcast port
    except OSError:
        sock = _socket(0)
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(_Protocol, sock=sock)
    try:
        for _ in range(3):  # cameras sometimes miss the first probe
            transport.sendto(PROBE, ("255.255.255.255", PORT))
            await asyncio.sleep(0.1)
        await asyncio.sleep(timeout)
    except OSError as err:
        _LOGGER.debug("Discovery failed: %s", err)
    finally:
        transport.close()
    return list(protocol.found.values())
