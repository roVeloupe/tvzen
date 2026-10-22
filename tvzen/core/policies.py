"""净化策略库：高置信度已知包名 + 启发式可疑度评分。

设计哲学（与市面脚本的本质区别）：
  1. 内置一份「高置信度」已知包名库（只收录社区广泛验证的真实包名）；
  2. 对未知包，用「名称特征启发式规则」打分——这让 TVZen 即使面对
     策略库未覆盖的新设备/新固件也能工作，且策略库永远追不上固件变化；
  3. never-touch 白名单兜底，任何情况下不碰系统关键组件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class Category(str, Enum):
    ADS = "ads"                # 广告 SDK / 广告位 / 广告服务
    BLOAT = "bloat"            # 厂商预装推广 / 购物 / 无用 App
    TELEMETRY = "telemetry"    # 遥测 / 数据收集 / 行为统计
    PROMO = "promo"            # 开机广告 / 屏保推广 / 推荐服务
    UNKNOWN = "unknown"


class Risk(str, Enum):
    SAFE = "safe"          # 禁用几乎无副作用（独立广告/推广组件）
    CAUTION = "caution"    # 可能影响其他功能（需用户确认）
    CRITICAL = "critical"  # 系统关键，永不自动禁用


# ---------------------------------------------------------------------------
# 1. never-touch 白名单：命中即 CRITICAL，任何模式不得覆盖
# ---------------------------------------------------------------------------
NEVER_TOUCH_PATTERNS: tuple[str, ...] = (
    r"launcher", r"tvinput", r"systemui", r"settings$", r"setupwizard",
    r"inputmethod", r"\.ime$", r"keyboard", r"provision",
    r"com\.android\.systemui", r"com\.android\.settings",
    r"com\.google\.android\.tvlauncher", r"com\.google\.android\.leanbacklauncher",
    r"com\.amazon\.tv\.launcher", r"com\.android\.vending",
    r"com\.google\.android\.gms", r"com\.google\.android\.permissioncontroller",
    r"com\.android\.packageinstaller", r"com\.android\.shell",
    r"com\.android\.externalstorage", r"com\.android\.networkstack",
    r"com\.android\.bluetooth", r"com\.android\.wifi",
    r"\.hwui$", r"com\.android\.server\.",
)

# ---------------------------------------------------------------------------
# 2. 高置信度已知包名库（社区广泛验证；只收真实存在的）
#    条目: (包名或正则, 类别, 风险, 说明)
# ---------------------------------------------------------------------------
KNOWN_PACKAGES: tuple[tuple[str, Category, Risk, str], ...] = (
    # --- Google TV / Android TV 官方广告与推荐 ---
    (r"com\.google\.android\.ads\.tv", Category.ADS, Risk.SAFE,
     "Google TV 广告服务（开屏/插屏广告）"),
    (r"com\.google\.android\.tvrecommendations", Category.PROMO, Risk.SAFE,
     "Google TV 首页推荐行（含推广内容）"),
    (r"com\.google\.android\.tv\.recommendation", Category.PROMO, Risk.SAFE,
     "Google TV 推荐服务"),
    (r"com\.google\.android\.assistant", Category.PROMO, Risk.CAUTION,
     "Google 语音助手（按住首页键唤醒；不需要可禁）"),
    # --- Amazon Fire TV ---
    (r"com\.amazon\.tv\.ads", Category.ADS, Risk.SAFE,
     "Fire TV 广告 SDK"),
    (r"com\.amazon\.ahs", Category.PROMO, Risk.SAFE,
     "Fire TV 主屏推广服务"),
    (r"com\.amazon\.avs", Category.PROMO, Risk.CAUTION,
     "Alexa 语音服务（不用 Alexa 可禁）"),
    (r"com\.amazon\.device\.controllermanager", Category.BLOAT, Risk.CAUTION,
     "Fire TV 设备管控组件"),
    # --- 小米 / 红米 TV ---
    (r"com\.xiaomi\.tv\.push", Category.TELEMETRY, Risk.SAFE,
     "小米电视推送服务"),
    (r"com\.xiaomi\.mitv\.push", Category.TELEMETRY, Risk.SAFE,
     "小米电视推送服务（旧包名）"),
    (r"com\.xiaomi\.tv\.player\.ad", Category.ADS, Risk.SAFE,
     "小米电视播放器广告组件"),
    (r"com\.miui\.tv\.push", Category.TELEMETRY, Risk.SAFE, "MIUI TV 推送"),
    (r"com\.xiaomi\.mitv\.advertise", Category.ADS, Risk.SAFE, "小米电视广告服务"),
    (r"com\.xiaomi\.mitv\.payment", Category.BLOAT, Risk.CAUTION,
     "小米电视支付组件（无付费需求可禁）"),
    # --- 雷鸟 / TCL / FFalcon ---
    (r"com\.tcl\.tv\.push", Category.TELEMETRY, Risk.SAFE, "TCL 推送"),
    (r"com\.ffalconx\.tv\.push", Category.TELEMETRY, Risk.SAFE, "雷鸟推送"),
    (r"com\.tcl\.browser", Category.BLOAT, Risk.SAFE, "TCL 预装浏览器"),
    (r"com\.tcl\.marketplace", Category.BLOAT, Risk.SAFE, "TCL 应用商店推广"),
    # --- 海信 / Hisense / VIDAA ---
    (r"com\.hisense\.tv\.push", Category.TELEMETRY, Risk.SAFE, "海信推送"),
    (r"com\.vidaa\.push", Category.TELEMETRY, Risk.SAFE, "VIDAA 推送"),
    (r"com\.hisense\.service\.ad", Category.ADS, Risk.SAFE, "海信广告服务"),
    # --- 创维 / Skyworth / 酷开 ---
    (r"com\.skyworth\.push", Category.TELEMETRY, Risk.SAFE, "创维推送"),
    (r"com\.coocaa\.push", Category.TELEMETRY, Risk.SAFE, "酷开推送"),
    (r"com\.skyworth\.ad", Category.ADS, Risk.SAFE, "创维广告"),
    # --- 长虹 / Changhong ---
    (r"com\.changhong\.tv\.push", Category.TELEMETRY, Risk.SAFE, "长虹推送"),
    (r"com\.changhong\.ad", Category.ADS, Risk.SAFE, "长虹广告"),
    # --- 索尼 / Sony ---
    (r"com\.sony\.dtv\.advertise", Category.ADS, Risk.SAFE, "索尼电视广告服务"),
    (r"com\.sony\.dtv\.browser", Category.BLOAT, Risk.CAUTION,
     "索尼预装浏览器"),
    # --- 飞利浦 / Philips ---
    (r"com\.philips\.tv\.push", Category.TELEMETRY, Risk.SAFE, "飞利浦推送"),
    # --- 康佳 / Konka ---
    (r"com\.konka\.push", Category.TELEMETRY, Risk.SAFE, "康佳推送"),
    # --- 常见通用广告/统计 SDK ---
    (r"com\.umeng", Category.TELEMETRY, Risk.CAUTION, "友盟统计 SDK"),
    (r"com\.google\.firebase\.analytics", Category.TELEMETRY, Risk.CAUTION,
     "Firebase 分析"),
    (r"com\.qihoo\.util", Category.TELEMETRY, Risk.CAUTION, "360 SDK 组件"),
    (r"cn\.shuzilm\.main", Category.ADS, Risk.SAFE, "数字联盟设备指纹 SDK"),
    (r"com\.zhiguang\.union", Category.ADS, Risk.SAFE, "聚合广告 SDK"),
)

# ---------------------------------------------------------------------------
# 3. 启发式规则：包名包含这些 token 即加分
#    (token, 类别, 权重分)
# ---------------------------------------------------------------------------
HEURISTIC_TOKENS: tuple[tuple[str, Category, int], ...] = (
    ("advert", Category.ADS, 60),
    ("ads", Category.ADS, 60),
    ("adservice", Category.ADS, 60),
    ("banner", Category.ADS, 45),
    ("promo", Category.PROMO, 50),
    ("recommend", Category.PROMO, 35),
    ("suggest", Category.PROMO, 25),
    ("push", Category.TELEMETRY, 45),
    ("statistic", Category.TELEMETRY, 40),
    ("analytics", Category.TELEMETRY, 40),
    ("tracking", Category.TELEMETRY, 40),
    ("telemetry", Category.TELEMETRY, 50),
    ("report", Category.TELEMETRY, 15),
    ("uploadlog", Category.TELEMETRY, 40),
    ("marketplace", Category.BLOAT, 40),
    ("appstore", Category.BLOAT, 30),
    ("vmall", Category.BLOAT, 45),
    ("hiwallpaper", Category.BLOAT, 30),
    ("themeservice", Category.BLOAT, 25),
    ("gamecenter", Category.BLOAT, 25),
    ("videochat", Category.BLOAT, 20),
    ("shopping", Category.BLOAT, 30),
    ("update", Category.BLOAT, 10),     # 权重低：系统升级组件常含 update
    ("assistant", Category.PROMO, 20),
)

# 可疑度阈值：>= 该分数才进入净化计划（启发式命中）
HEURISTIC_THRESHOLD = 40


@dataclass(frozen=True)
class PackageVerdict:
    """单个包的净化裁决。"""
    package: str
    category: Category
    risk: Risk
    score: int
    reason: str
    matched: str = ""      # 命中的规则（包名或 token）


@dataclass
class ScanResult:
    verdicts: list[PackageVerdict] = field(default_factory=list)

    @property
    def removable(self) -> list[PackageVerdict]:
        """可净化（safe + caution 且分数达标），按风险与分数排序。"""
        return sorted(
            (v for v in self.verdicts if v.risk is not Risk.CRITICAL
             and v.category is not Category.UNKNOWN),
            key=lambda v: (v.risk is Risk.CAUTION, -v.score),
        )

    def by_category(self) -> dict[Category, list[PackageVerdict]]:
        out: dict[Category, list[PackageVerdict]] = {}
        for v in self.removable:
            out.setdefault(v.category, []).append(v)
        return out


def _is_never_touch(package: str) -> bool:
    return any(re.search(p, package) for p in NEVER_TOUCH_PATTERNS)


def score_package(package: str,
                  known: Iterable[tuple[str, Category, Risk, str]] = KNOWN_PACKAGES,
                  tokens: Iterable[tuple[str, Category, int]] = HEURISTIC_TOKENS) -> PackageVerdict:
    """对单个包名打分并给出裁决。

    优先级：never-touch 白名单 > 已知包名库 > 启发式规则 > 放过。
    """
    if _is_never_touch(package):
        return PackageVerdict(package, Category.UNKNOWN, Risk.CRITICAL, 0,
                              "系统关键组件（白名单保护）")

    for pattern, cat, risk, reason in known:
        if re.search(pattern, package):
            return PackageVerdict(package, cat, risk, 100,
                                  f"已知包名库: {reason}", pattern)

    # 启发式：累加命中 token 分数（取最高分类）
    hits: list[tuple[str, Category, int]] = []
    for token, cat, weight in tokens:
        if token in package:
            hits.append((token, cat, weight))
    if hits:
        best_cat = max(hits, key=lambda h: h[2])[1]
        score = min(100, sum(h[2] for h in hits))
        # 多 token 命中视为更高置信度
        if len(hits) > 1:
            score = min(100, score + 15)
        if score >= HEURISTIC_THRESHOLD:
            risk = Risk.SAFE if score >= 60 else Risk.CAUTION
            reason = "启发式命中: " + ", ".join(h[0] for h in hits)
            return PackageVerdict(package, best_cat, risk, score, reason,
                                  hits[0][0])

    return PackageVerdict(package, Category.UNKNOWN, Risk.SAFE, 0, "未命中任何规则")


def scan_packages(packages: Iterable[str]) -> ScanResult:
    """扫描包列表，返回全部裁决（含被放过的，便于报告展示）。"""
    result = ScanResult()
    for pkg in sorted(set(packages)):
        result.verdicts.append(score_package(pkg))
    return result
