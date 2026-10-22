"""净化引擎：scan → plan → apply → rollback 全流程。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from tvzen import __version__
from .adb import AdbClient
from .policies import Category, PackageVerdict, Risk, ScanResult, scan_packages
from .snapshot import Snapshot


@dataclass
class Plan:
    """一次净化的执行计划。"""
    device: str
    model: str
    targets: list[PackageVerdict] = field(default_factory=list)
    total_packages: int = 0

    @property
    def count(self) -> int:
        return len(self.targets)

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.targets:
            out[v.category.value] = out.get(v.category.value, 0) + 1
        return out


@dataclass
class ApplyResult:
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    snapshot_path: str = ""


class Engine:
    def __init__(self, client: AdbClient, snapshot_dir: str | Path = "~/.tvzen/snapshots"):
        self.client = client
        self.snapshot_dir = Path(snapshot_dir).expanduser()

    # -- scan -------------------------------------------------------------
    def scan(self, serial: str,
             categories: set[Category] | None = None,
             include_caution: bool = True) -> tuple[Plan, ScanResult]:
        info = self.client.device_info(serial)
        packages = self.client.list_packages(serial)
        enabled = self.client.list_enabled(serial)
        result = scan_packages(packages)

        targets = [
            v for v in result.removable
            if v.package in enabled                       # 只处理仍启用的
            and (categories is None or v.category in categories)
            and (include_caution or v.risk is not Risk.CAUTION)
        ]
        plan = Plan(device=serial, model=info.model or info.brand, targets=targets,
                    total_packages=len(packages))
        return plan, result

    # -- apply ------------------------------------------------------------
    def apply(self, serial: str, plan: Plan,
              action: str = "disable",
              make_snapshot: bool = True,
              dry_run: bool = False) -> ApplyResult:
        res = ApplyResult()
        snap = Snapshot(version=__version__, serial=serial, model=plan.model,
                        created_at=time.time(), action=action)
        for v in plan.targets:
            if dry_run:
                res.applied.append(v.package)
                continue
            try:
                if action == "uninstall":
                    out = self.client.uninstall_user(serial, v.package)
                else:
                    out = self.client.disable(serial, v.package)
                if "Success" in out or "new state" in out:
                    res.applied.append(v.package)
                    snap.disabled.append(v.package)
                else:
                    res.failed.append(v.package)
            except Exception:
                res.failed.append(v.package)
        if make_snapshot and snap.disabled and not dry_run:
            path = snap.save(self.snapshot_dir)
            res.snapshot_path = str(path)
        return res

    # -- rollback ---------------------------------------------------------
    def rollback(self, serial: str, snapshot: Snapshot) -> ApplyResult:
        res = ApplyResult()
        for pkg in snapshot.disabled:
            try:
                out = self.client.enable(serial, pkg)
                if "Success" in out or "new state" in out:
                    res.applied.append(pkg)
                else:
                    res.failed.append(pkg)
            except Exception:
                res.failed.append(pkg)
        return res
