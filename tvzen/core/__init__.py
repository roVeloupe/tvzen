"""TVZen core 包。"""

from .policies import Category, PackageVerdict, Risk, ScanResult, scan_packages, score_package
from .adb import AdbClient, AdbError, Device
from .engine import ApplyResult, Engine, Plan
from .snapshot import Snapshot
from .report import render_plan, render_result, save_report, to_html, to_json

__all__ = [
    "Category", "PackageVerdict", "Risk", "ScanResult", "scan_packages", "score_package",
    "AdbClient", "AdbError", "Device",
    "ApplyResult", "Engine", "Plan",
    "Snapshot",
    "render_plan", "render_result", "save_report", "to_html", "to_json",
]
