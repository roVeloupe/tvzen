"""设备发现：USB 设备 + 局域网扫描（Android 11+ 无线调试）。"""

from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .adb import AdbClient, AdbError, Device


@dataclass
class DiscoveryResult:
    usb: list[Device]
    lan: list[str]          # 可达的 ip:port


def _probe(target: str, timeout: float = 0.4) -> bool:
    host, port = target.rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def scan_lan(client: AdbClient, cidr: str, port: int = 5555,
             workers: int = 64) -> list[str]:
    """并发扫描网段 5555 端口，返回可达地址列表。"""
    net = ipaddress.ip_network(cidr, strict=False)
    targets = [f"{ip}:{port}" for ip in net.hosts()]
    reachable: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe, t): t for t in targets}
        for fut in as_completed(futures):
            if fut.result():
                reachable.append(futures[fut])
    return sorted(reachable, key=lambda t: ipaddress.ip_address(t.rsplit(":", 1)[0]))


def discover(client: AdbClient, lan_cidr: str | None = None) -> DiscoveryResult:
    usb = [d for d in client.devices() if d.state == "device"]
    lan: list[str] = []
    if lan_cidr:
        for addr in scan_lan(client, lan_cidr):
            try:
                out = client.connect(addr)
                if "connected" in out or "already" in out:
                    lan.append(addr)
            except AdbError:
                pass
        # 连接后刷新设备列表
        connected = {d.serial for d in client.devices()}
        lan = [a for a in lan if a in connected]
    return DiscoveryResult(usb=usb, lan=lan)


def local_cidr() -> str | None:
    """猜测本机所在网段（/24），用于默认 LAN 扫描。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return str(ipaddress.ip_network(f"{ip}/24", strict=False))
    except OSError:
        return None
