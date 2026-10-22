#!/usr/bin/env python3
"""从真实机型清单生成文档示例（scan-example.txt / report-example.html）。

模拟设备的包列表来自 cleanyourtv 真实清单 sony-bravia-4k-gb.txt：
  - 24 个该清单实际禁用的包（逐行提取）
  - 同清单 KEEP 注释中保留的功能包（Chromecast/媒体播放器/DLNA 等）
  - 通用系统关键包（never-touch 白名单）
输出不是编造数据，而是真实引擎跑在真实包集合上的结果。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tvzen.core.engine import Plan                      # noqa: E402
from tvzen.core.policies import Category, Risk, scan_packages  # noqa: E402
from tvzen.core.report import render_plan, to_html      # noqa: E402

# sony-bravia-4k-gb.txt 中实际禁用的 24 个包（原样提取）
SONY_DISABLED = [
    "tv.samba.ssm", "com.sony.dtv.sonyselect", "com.sony.dtv.promos",
    "com.sony.dtv.discovery", "com.sony.dtv.bivlinfo",
    "com.sony.dtv.tvlaunchercustomizer", "com.google.android.tvrecommendations",
    "android.autoinstalls.config.sony.bravia", "com.sony.dtv.demomode",
    "com.sony.dtv.demosupport", "com.sony.dtv.multiscreendemo",
    "com.sony.dtv.da.service", "com.qterics.da.product",
    "com.sony.dtv.sonybugreportsys", "com.google.android.tv.bugreportsender",
    "com.google.android.feedback", "com.sony.dtv.b2b.vendorprotocol",
    "com.sony.dtv.customersupport", "com.sony.dtv.smarthelp",
    "com.sony.dtv.imanual", "com.google.android.youtube.tvmusic",
    "com.google.android.videos", "com.google.android.play.games",
    "com.google.android.backdrop",
]

# 同清单注释中「特意保留」的功能包 + 原生桌面
SONY_KEPT = [
    "com.google.android.apps.mediashell",      # Chromecast built-in
    "com.sony.dtv.smartmediaapp",              # USB 媒体播放器
    "com.sony.dtv.osat.music",                 # USB 音乐播放
    "screnmirroring.com",                      # Miracast
    "com.sony.dtv.networkapp.wifidirect",
    "com.sony.huey.dlna.module",               # DLNA renderer
    "com.google.android.tvlauncher",           # 原生桌面
    "com.sony.dtv.tvx",                        # Live TV + HDMI 输入
]

# 系统关键包（never-touch）
SYSTEM = [
    "com.android.systemui", "com.android.settings", "com.android.vending",
    "com.google.android.gms", "com.android.location.fused",
    "com.android.packageinstaller", "com.android.shell",
]


def main() -> int:
    packages = SONY_DISABLED + SONY_KEPT + SYSTEM
    result = scan_packages(packages)

    targets = [
        v for v in result.removable
        if v.package in set(packages) and v.risk is not Risk.CRITICAL
    ]
    plan = Plan(device="simulated", model="Sony BRAVIA 4K GB（模拟）",
                targets=targets, total_packages=len(packages))

    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    (out / "scan-example.txt").write_text(render_plan(plan), encoding="utf-8")
    (out / "report-example.html").write_text(to_html(plan), encoding="utf-8")

    print(render_plan(plan))
    print(f"\n✅ docs/scan-example.txt  docs/report-example.html 已生成"
          f"（{len(packages)} 个真实包）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
