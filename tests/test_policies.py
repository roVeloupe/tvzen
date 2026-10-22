"""策略引擎测试：已知包名、启发式评分、白名单保护。"""

import pytest

from tvzen.core.policies import Category, Risk, scan_packages, score_package


class TestKnownPackages:
    def test_google_tv_ads_is_safe(self):
        v = score_package("com.google.android.ads.tv")
        assert v.category is Category.ADS
        assert v.risk is Risk.SAFE
        assert v.score == 100

    def test_fire_tv_ahs(self):
        v = score_package("com.amazon.ahs")
        assert v.category is Category.PROMO
        assert v.risk is Risk.SAFE

    def test_xiaomi_push_telemetry(self):
        v = score_package("com.xiaomi.tv.push")
        assert v.category is Category.TELEMETRY


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


class TestNeverTouch:
    @pytest.mark.parametrize("pkg", [
        "com.google.android.tvlauncher",
        "com.android.systemui",
        "com.android.settings",
        "com.android.vending",
        "com.google.android.gms",
    ])
    def test_critical_packages_protected(self, pkg):
        v = score_package(pkg)
        assert v.risk is Risk.CRITICAL

    def test_never_touch_overrides_known_rule(self):
        # 即使名字像推广，launcher 永不被动
        v = score_package("com.vendor.adslauncher")
        assert v.risk is Risk.CRITICAL


class TestScan:
    def test_scan_summary(self):
        result = scan_packages([
            "com.google.android.ads.tv",
            "com.xiaomi.tv.push",
            "com.vendor.analyticssdk",
            "com.android.systemui",
            "com.netflix.ninja",   # 用户可能需要，不命中规则
            "com.example.updater",
        ])
        removable = result.removable
        assert len(removable) == 3
        cats = {v.category for v in removable}
        assert cats == {Category.ADS, Category.TELEMETRY}

    def test_scan_is_deduplicated(self):
        result = scan_packages(["com.a.ads", "com.a.ads"])
        assert len(result.verdicts) == 1
