"""ADB 客户端封装：设备发现、连接、包管理。

只依赖 adb 可执行文件与标准库；所有外部命令都经过统一错误处理，
便于测试注入（adb_runner 参数）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

Runner = Callable[[list[str]], tuple[int, str, str]]


class AdbError(RuntimeError):
    pass


def default_runner(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


@dataclass
class Device:
    serial: str
    state: str                       # device / offline / unauthorized
    model: str = ""
    brand: str = ""
    android_version: str = ""
    sdk: str = ""

    @property
    def label(self) -> str:
        name = self.model or self.serial
        return f"{name} ({self.serial})"


class AdbClient:
    """对 adb 命令的最小封装。"""

    def __init__(self, adb_path: Optional[str] = None, runner: Runner = default_runner):
        self.adb = adb_path or shutil.which("adb") or "adb"
        self._run = runner

    # -- 基础 -------------------------------------------------------------
    def _cmd(self, serial: Optional[str], *args: str) -> str:
        base = [self.adb]
        if serial:
            base += ["-s", serial]
        code, out, err = self._run(base + list(args))
        if code != 0:
            raise AdbError(f"adb {' '.join(args)} failed ({code}): {err.strip() or out.strip()}")
        return out

    # -- 设备 -------------------------------------------------------------
    def devices(self) -> list[Device]:
        out = self._cmd(None, "devices", "-l")
        devices: list[Device] = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            serial, state = parts[0], parts[1]
            model = brand = ""
            for kv in parts[2:]:
                if kv.startswith("model:"):
                    model = kv.split(":", 1)[1]
                elif kv.startswith("device:") and not brand:
                    brand = kv.split(":", 1)[1]
            devices.append(Device(serial=serial, state=state, model=model, brand=brand))
        return devices

    def device_info(self, serial: str) -> Device:
        dev = Device(serial=serial, state="device")
        for prop, attr in (("ro.product.model", "model"),
                           ("ro.product.brand", "brand"),
                           ("ro.build.version.release", "android_version"),
                           ("ro.build.version.sdk", "sdk")):
            try:
                val = self._cmd(serial, "shell", "getprop", prop).strip()
                setattr(dev, attr, val)
            except AdbError:
                pass
        return dev

    def connect(self, host: str, port: int = 5555) -> str:
        return self._cmd(None, "connect", f"{host}:{port}").strip()

    def pair(self, host: str, port: int, code: str) -> str:
        return self._cmd(None, "pair", f"{host}:{port}", code).strip()

    # -- 包管理 -----------------------------------------------------------
    def list_packages(self, serial: str) -> list[str]:
        out = self._cmd(serial, "shell", "pm", "list", "packages")
        pkgs = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                pkgs.append(line[len("package:"):].strip())
        return pkgs

    def list_enabled(self, serial: str) -> set[str]:
        out = self._cmd(serial, "shell", "pm", "list", "packages", "-e")
        return {l.strip()[len("package:"):]
                for l in out.splitlines() if l.strip().startswith("package:")}

    def disable(self, serial: str, package: str) -> str:
        """禁用（用户级，可恢复 —— TVZen 默认动作）。"""
        return self._cmd(serial, "shell", "pm", "disable-user",
                         "--user", "0", package).strip()

    def enable(self, serial: str, package: str) -> str:
        return self._cmd(serial, "shell", "pm", "enable",
                         "--user", "0", package).strip()

    def uninstall_user(self, serial: str, package: str) -> str:
        """用户级卸载（更彻底，但恢复需重装 —— 仅显式 --uninstall 时用）。"""
        return self._cmd(serial, "shell", "pm", "uninstall",
                         "-k", "--user", "0", package).strip()

    def clear(self, serial: str, package: str) -> str:
        return self._cmd(serial, "shell", "pm", "clear", package).strip()
