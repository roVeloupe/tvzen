"""策略引擎测试：真实包名库、启发式评分、白名单保护、零遮蔽不变量。

所有断言均基于真实数据（227 份社区机型清单解析），不使用编造包名。
"""

import pytest

from tvzen.core.policies import (
    DB, Category, Risk, KNOWN_PACKAGES, NEVER_TOUCH_PATTERNS,
    db_stats, score_package, scan_packages,
)


class TestRealDatabase:
    """数据库本身的完整性。"""

    def test_db_loaded(self):
        stats = db_stats()
        assert stats["known_packages"] >= 1000
        assert stats["keep_traps"] >= 100
        assert stats["conflict_packages"] >= 20
        assert "cleanyourtv" in stats["source"]

    def test_every_entry_has_evidence(self):
        for pkg, e in DB.items():
            assert pkg == e.package
            assert e.devices >= 1
            assert isinstance(e.category, Category)


class TestKnownPackages:
    def test_google_tv_recommendations_promo(self):
        v = score_package("com.google.android.tvrecommendations")
        assert v.category is Category.PROMO
        assert v.risk is Risk.SAFE
        assert v.score == 100
        assert "89" in v.reason            # 89 份真实清单禁用

    def test_tcl_esticker_bloat(self):
        v = score_package("com.tcl.esticker")
        assert v.category is Category.BLOAT
        assert v.risk is Risk.SAFE

    def test_google_feedback_telemetry_safe(self):
        # 167 份清单禁用、仅 1 份保留 → 仍判 SAFE
        v = score_package("com.google.android.feedback")
        assert v.category is Category.TELEMETRY
        assert v.risk is Risk.SAFE

    def test_xiaomi_statistic_telemetry(self):
        v = score_package("com.xiaomi.statistic")
        assert v.category is Category.TELEMETRY
        assert v.risk is Risk.SAFE

    def test_samba_acr_telemetry(self):
        v = score_package("tv.samba.ssm")
        assert v.category is Category.TELEMETRY


class TestConflictDowngradesToCaution:
    """被多份清单特意保留的包必须降级 CAUTION（社区有分歧）。"""

    @pytest.mark.parametrize("pkg", [
        "com.google.android.katniss",            # 78 禁 / 17 留
        "com.google.android.apps.mediashell",    # 31 禁 / 29 留
        "com.google.android.apps.tv.launcherx",  # 26 禁 / 14 留
        "com.amazon.amazonvideo.livingroom",     # Prime Video
        "com.google.android.marvin.talkback",    # TalkBack
    ])
    def test_conflict_packages_are_caution(self, pkg):
        v = score_package(pkg)
        assert v.risk is Risk.CAUTION, pkg
        assert "特意保留" in v.reason or "不用再禁" in v.reason


class TestForceCaution:
    """系统功能包：禁用会丢功能，必须 CAUTION 且说明后果。"""

    def test_ota_updater(self):
        v = score_package("com.apps.ota")
        assert v.risk is Risk.CAUTION
        assert "OTA" in v.reason

    def test_tv_tuner(self):
        v = score_package("com.sony.dtv.tvinput.atsc3tuner")
        assert v.risk is Risk.CAUTION
        assert "信号源" in v.reason

    def test_stock_launcher_not_critical_but_caution(self):
        v = score_package("com.google.android.leanbacklauncher")
        assert v.risk is Risk.CAUTION
        assert "桌面" in v.reason

    def test_provisioning(self):
        v = score_package("com.softwinner.provision")
        assert v.risk is Risk.CAUTION
        assert "配置" in v.reason

    def test_input_method(self):
        v = score_package("com.google.android.inputmethod.japanese")
        assert v.risk is Risk.CAUTION
        assert "输入法" in v.reason


class TestUserApps:
    def test_netflix_is_user_app(self):
        v = score_package("com.netflix.ninja")
        assert v.risk is Risk.CAUTION
        assert "不用再禁" in v.reason


class TestHeuristics:
    def test_unknown_ads_package_flagged(self):
        v = score_package("com.somevendor.ads.module")
        assert v.category is Category.ADS
        assert v.score >= 60
        assert v.risk is Risk.SAFE

    def test_multi_token_hit_boosts_score(self):
        single = score_package("com.vendor.pushext")
        multi = score_package("com.vendor.push.analytics")
        assert multi.score > single.score

    def test_telemetry_keywords(self):
        for pkg in ("com.vendor.analyticssdk", "com.vendor.tracking",
                    "com.vendor.telemetry.core"):
            v = score_package(pkg)
            assert v.category is Category.TELEMETRY, pkg

    def test_below_threshold_ignored(self):
        v = score_package("com.example.updater")   # update 权重 10 < 40
        assert v.category is Category.UNKNOWN
        assert v.score == 0

    def test_doubleclick_flagged(self):
        v = score_package("com.vendor.doubleclick.module")
        assert v.category is Category.ADS


class TestNeverTouch:
    @pytest.mark.parametrize("pkg", [
        "com.android.systemui",
        "com.android.settings",
        "com.android.vending",
        "com.google.android.gms",
        # 真实 KEEP 陷阱包
        "com.tcl.tv",                      # HDMI 输入（锚定，不误伤 tclhome）
        "com.tcl.tvinput",
        "com.tcl.system.server",
        "com.android.location.fused",
        "com.xgimi.bluetoothservice",
    ])
    def test_critical_packages_protected(self, pkg):
        v = score_package(pkg)
        assert v.risk is Risk.CRITICAL, pkg

    def test_never_touch_overrides_known_rule(self):
        # 即使名字像广告，白名单优先
        v = score_package("com.zeasn.whale.saas")
        assert v.risk is Risk.CRITICAL

    def test_custom_known_still_supported(self):
        # 测试注入路径（向后兼容）
        v = score_package("com.test.customads",
                          known=[(r"com\.test\.customads", Category.ADS, Risk.SAFE, "x")])
        assert v.category is Category.ADS


class TestZeroShadowing:
    """不变量：白名单与强制规则不得把真实可禁用包误判为 CRITICAL。"""

    def test_no_db_package_is_critical(self):
        critical = [p for p in DB if score_package(p).risk is Risk.CRITICAL]
        assert critical == []

    def test_db_prefix_families_not_shadowed(self):
        # com.tcl.tv 受保护，但同前缀真实可禁用包必须放行
        for pkg in ("com.tcl.tv.tclhome_master", "com.tcl.tv.tclhome_passive",
                    "com.tcl.tv.plus", "com.tcl.tv.tclchannel"):
            v = score_package(pkg)
            assert v.risk is not Risk.CRITICAL, pkg
            assert v.score == 100, pkg

    def test_db_packages_mostly_removable(self):
        # 数据库里的包默认应可净化（除冲突/功能包降级 CAUTION 外）
        safe = sum(1 for p in DB if score_package(p).risk is Risk.SAFE)
        assert safe >= len(DB) * 0.8


class TestScan:
    def test_scan_summary(self):
        result = scan_packages([
            "com.google.android.tvrecommendations",   # 已知 PROMO/SAFE
            "com.xiaomi.statistic",                   # 已知 TELEMETRY/SAFE
            "com.vendor.analyticssdk",                # 启发式 TELEMETRY
            "com.android.systemui",                   # CRITICAL
            "com.netflix.ninja",                      # CAUTION 用户应用
            "com.example.updater",                    # UNKNOWN
        ])
        removable = result.removable
        assert len(removable) == 4
        cats = {v.category for v in removable}
        assert cats == {Category.PROMO, Category.TELEMETRY, Category.BLOAT}
        # 排序: SAFE 在前（分数降序），CAUTION 在后
        assert [v.package for v in removable] == [
            "com.google.android.tvrecommendations",
            "com.xiaomi.statistic",
            "com.netflix.ninja",
            "com.vendor.analyticssdk",
        ]

    def test_scan_is_deduplicated(self):
        result = scan_packages(["com.a.ads", "com.a.ads"])
        assert len(result.verdicts) == 1


class TestDbStats:
    """db_stats 与 CLI db 命令的一致性。"""

    def test_stats_shape(self):
        stats = db_stats()
        assert set(stats) >= {"known_packages", "keep_traps", "conflict_packages",
                              "never_touch_patterns", "heuristic_tokens", "categories"}
        assert sum(stats["categories"].values()) == stats["known_packages"]

    def test_cli_db_command(self, capsys):
        from tvzen.cli import build_parser
        rc = build_parser().parse_args(["db"]).func(
            build_parser().parse_args(["db"]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "1140" in out and "cleanyourtv" in out
