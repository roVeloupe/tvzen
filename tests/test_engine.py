"""引擎测试：用 mock ADB runner 模拟设备，无需真机。"""

import json

import pytest

from tvzen.core.adb import AdbClient, Device
from tvzen.core.engine import Engine, Plan
from tvzen.core.policies import Category, Risk
from tvzen.core.snapshot import Snapshot

# 模拟一台 Google TV 的包列表：全部使用真实包名（来自 227 份社区清单数据库），
# 未知包 com.vendor.analyticssdk / com.example.updater 用于验证启发式与放过路径。
FAKE_PACKAGES = [
    "com.google.android.tvrecommendations",   # 已知 PROMO / SAFE（89 台设备）
    "com.google.android.feedback",            # 已知 TELEMETRY / SAFE（167 台设备）
    "tv.samba.ssm",                           # 已知 TELEMETRY / SAFE（ACR 观看追踪）
    "com.tcl.esticker",                       # 已知 BLOAT / SAFE（49 台设备）
    "com.google.android.katniss",             # 社区冲突 → CAUTION
    "com.google.android.youtube.tv",          # 用户应用 → CAUTION
    "com.google.android.tvlauncher",          # 原生气桌面 → CAUTION
    "com.netflix.ninja",                      # 用户应用 → CAUTION
    "com.vendor.analyticssdk",                # 启发式命中 TELEMETRY
    "com.example.updater",                    # 未命中，放过
    # never-touch 白名单
    "com.android.systemui",
    "com.android.settings",
    "com.android.vending",
    "com.google.android.gms",
    "com.android.location.fused",
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
        assert "com.google.android.tvrecommendations" in pkgs
        assert "tv.samba.ssm" in pkgs
        assert "com.vendor.analyticssdk" in pkgs
        assert "com.android.systemui" not in pkgs      # 白名单
        assert "com.example.updater" not in pkgs       # 未命中规则
        assert "com.netflix.ninja" in pkgs             # 用户应用 → CAUTION 仍入计划
        assert plan.total_packages == len(FAKE_PACKAGES)

    def test_scan_safe_only_excludes_caution(self, engine):
        eng, _ = engine
        plan, _ = eng.scan("serial123", include_caution=False)
        pkgs = {v.package for v in plan.targets}
        assert "com.netflix.ninja" not in pkgs         # CAUTION 被排除
        assert "com.google.android.katniss" not in pkgs
        assert "com.google.android.tvrecommendations" in pkgs

    def test_scan_category_filter(self, engine):
        eng, _ = engine
        plan, _ = eng.scan("serial123", categories={Category.TELEMETRY})
        assert plan.targets, "telemetry 类别不应为空"
        assert all(v.category is Category.TELEMETRY for v in plan.targets)


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
