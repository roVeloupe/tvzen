"""引擎测试：用 mock ADB runner 模拟设备，无需真机。"""

import json

import pytest

from tvzen.core.adb import AdbClient, Device
from tvzen.core.engine import Engine, Plan
from tvzen.core.policies import Risk
from tvzen.core.snapshot import Snapshot

FAKE_PACKAGES = [
    "com.google.android.ads.tv",
    "com.google.android.tvrecommendations",
    "com.xiaomi.tv.push",
    "com.vendor.analyticssdk",
    "com.android.systemui",
    "com.google.android.tvlauncher",
    "com.netflix.ninja",
]


def fake_runner(serial_state="device"):
    """构造一个内存版 adb runner。"""
    state = {"disabled": set()}

    def run(args):
        if args[1:3] == ["devices", "-l"] or args[:2] == ["adb", "devices"]:
            if "devices" in args:
                return 0, f"List of devices attached\n{serial_state}\tdevice model:PixelTV\n", ""
        if "shell" in args and "getprop" in args:
            idx = args.index("getprop")
            return 0, {"ro.product.model": "TestTV",
                       "ro.product.brand": "testbrand",
                       "ro.build.version.release": "14",
                       "ro.build.version.sdk": "34"}.get(args[idx + 1], ""), ""
        if "pm" in args and "list" in args and "packages" in args:
            if "-e" in args:
                enabled = [p for p in FAKE_PACKAGES if p not in state["disabled"]]
                return 0, "\n".join(f"package:{p}" for p in enabled), ""
            return 0, "\n".join(f"package:{p}" for p in FAKE_PACKAGES), ""
        if "pm" in args and "disable-user" in args:
            pkg = args[-1]
            state["disabled"].add(pkg)
            return 0, f"Package {pkg} new state: disabled-user", ""
        if "pm" in args and "enable" in args:
            pkg = args[-1]
            state["disabled"].discard(pkg)
            return 0, f"Package {pkg} new state: enabled", ""
        return 0, "", ""

    return run, state


@pytest.fixture
def engine(tmp_path):
    run, state = fake_runner()
    client = AdbClient(runner=run)
    return Engine(client, snapshot_dir=tmp_path / "snaps"), state


class TestScan:
    def test_scan_finds_targets(self, engine):
        eng, _ = engine
        plan, result = eng.scan("serial123")
        pkgs = {v.package for v in plan.targets}
        assert "com.google.android.ads.tv" in pkgs
        assert "com.vendor.analyticssdk" in pkgs
        assert "com.android.systemui" not in pkgs      # 白名单
        assert "com.netflix.ninja" not in pkgs          # 未命中
        assert plan.total_packages == len(FAKE_PACKAGES)

    def test_scan_category_filter(self, engine):
        eng, _ = engine
        plan, _ = eng.scan("serial123", categories={"telemetry"})
        assert all(v.category.value == "telemetry" for v in plan.targets)


class TestApply:
    def test_apply_creates_snapshot(self, engine):
        eng, state = engine
        plan, _ = eng.scan("serial123")
        res = eng.apply("serial123", plan)
        assert len(res.applied) == plan.count
        assert res.snapshot_path
        assert state["disabled"] == set(res.applied)

    def test_apply_dry_run_changes_nothing(self, engine):
        eng, state = engine
        plan, _ = eng.scan("serial123")
        res = eng.apply("serial123", plan, dry_run=True)
        assert len(res.applied) == plan.count
        assert not state["disabled"]
        assert not res.snapshot_path

    def test_snapshot_roundtrip(self, engine, tmp_path):
        eng, _ = engine
        plan, _ = eng.scan("serial123")
        res = eng.apply("serial123", plan)
        snap = Snapshot.load(res.snapshot_path)
        assert snap.serial == "serial123"
        assert snap.disabled == res.applied
        assert json.loads(snap.to_json())["action"] == "disable"


class TestRollback:
    def test_rollback_restores(self, engine):
        eng, state = engine
        plan, _ = eng.scan("serial123")
        res = eng.apply("serial123", plan)
        snap = Snapshot.load(res.snapshot_path)
        back = eng.rollback("serial123", snap)
        assert set(back.applied) == set(res.applied)
        assert not state["disabled"]

    def test_latest_snapshot_lookup(self, engine):
        eng, _ = engine
        plan, _ = eng.scan("serial123")
        eng.apply("serial123", plan)
        snap = Snapshot.latest_for(eng.snapshot_dir, "serial123")
        assert snap is not None and snap.disabled
