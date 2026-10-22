"""报告生成测试。"""

from tvzen.core.engine import Plan
from tvzen.core.policies import Category, PackageVerdict, Risk
from tvzen.core.report import render_plan, to_html, to_json


def _plan() -> Plan:
    return Plan(
        device="SERIAL123", model="TestTV", total_packages=57,
        targets=[
            PackageVerdict("com.google.android.ads.tv", Category.ADS, Risk.SAFE, 100,
                           "已知包名库: Google TV 广告服务"),
            PackageVerdict("com.vendor.analyticssdk", Category.TELEMETRY, Risk.CAUTION, 55,
                           "启发式命中: analytics"),
        ])


def test_render_plan_contains_all_rows():
    text = render_plan(_plan())
    assert "TestTV" in text
    assert "com.google.android.ads.tv" in text
    assert "com.vendor.analyticssdk" in text


def test_json_report_valid():
    import json
    data = json.loads(to_json(_plan()))
    assert data["tool"] == "tvzen"
    assert len(data["targets"]) == 2
    assert data["targets"][0]["category"] == "ads"


def test_html_report_escapes_and_renders():
    html = to_html(_plan())
    assert html.startswith("<!DOCTYPE html>")
    assert "com.google.android.ads.tv" in html
    assert "广告组件" in html
    assert "TVZen" in html
