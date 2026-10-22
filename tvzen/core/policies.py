"""净化策略库：真实社区数据 + 启发式可疑度评分 + never-touch 白名单。

设计哲学（与市面脚本的本质区别）：
  1. 已知包名库全部来自真实数据——1140 个包名解析自 227 份真实机型的
     社区净化清单（cleanyourtv 项目），每个包带「设备覆盖数」与清单原文注释，
     可用 tools/build_package_db.py 重新生成，拒绝编造；
  2. 风险分级由数据驱动：被 ≥2 份清单特意保留的包自动降级为 CAUTION
     （社区本身有分歧），命中系统功能模式的包标记禁用后果；
  3. 对策略库未覆盖的新设备/新固件，用「名称特征启发式规则」打分——
     策略库永远追不上固件变化，启发式是长青层；
  4. never-touch 白名单兜底：通用模式 + 从清单 KEEP 注释中提取的
     真实系统关键包（每条都有注释佐证），且经过「零遮蔽」验证——
     白名单模式不会误伤任何被社区禁用的真实包。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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
#
# 两类来源，均经过「零遮蔽」验证（tests/test_policies.py 有回归测试）：
#   a) 通用系统模式——对 1140 个真实可禁用包零命中；
#   b) 真实清单中的 KEEP 陷阱包——社区注释明确其系统职责
#      （如 com.tcl.tvinput: "Live TV tuner + HDMI inputs"）。
#     一律用锚定正则，避免误伤同前缀的真实可禁用包
#      （如 com.tcl.tv 保护 HDMI 输入，但 com.tcl.tv.tclhome_master 必须放行）。
# ---------------------------------------------------------------------------
NEVER_TOUCH_PATTERNS: tuple[str, ...] = (
    # --- a) 通用系统模式（对真实可禁用包零遮蔽） ---
    r"systemui",
    r"\.ime$",
    r"com\.android\.settings$",
    r"com\.android\.systemui$",
    r"com\.android\.tv\.settings$",
    r"com\.android\.vending$",
    r"com\.android\.packageinstaller",
    r"com\.android\.shell",
    r"com\.android\.externalstorage",
    r"com\.android\.networkstack",
    r"com\.android\.wifi",
    r"com\.android\.server\.",
    r"com\.google\.android\.gms",
    r"com\.google\.android\.permissioncontroller",
    r"com\.amazon\.tv\.launcher$",
    r"\.hwui$",
    # --- b) 真实 KEEP 陷阱包（注释来自社区清单原文） ---
    r"com\.tcl\.tv$",                          # HDMI 输入源
    r"com\.tcl\.tvinput$",                     # Live TV tuner + HDMI inputs
    r"com\.tcl\.inputmethod\.international$",  # 键盘
    r"com\.tcl\.autopair$",                    # 蓝牙遥控自动配对
    r"com\.tcl\.tcl_bt_rcu_service$",          # 蓝牙遥控
    r"com\.tcl\.system\.server$",              # 遥控按键管线
    r"com\.tcl\.rc\.ota$",                     # 遥控固件更新
    r"com\.tcl\.keycustomfunctionservice$",    # 遥控按键处理
    r"com\.tcl\.factory\.view$",               # 工程菜单
    r"com\.mediatek\.tvinput$",                # HDMI 输入服务
    r"com\.mediatek\.dtv\.tvinput\.dvbtuner$",
    r"com\.xgimi\.tvinput$",                   # HDMI 1-3 输入
    r"com\.xgimi\.bluetoothservice$",          # 蓝牙遥控
    r"com\.xgimi\.soundermodeservice$",        # 蓝牙音箱模式
    r"com\.xgimi\.misckey$",                   # 遥控按键
    r"com\.android\.location\.fused$",         # 禁用会开机循环（社区实测）
    r"com\.android\.companiondevicemanager$",  # 蓝牙配对
    r"com\.oceanwing\.receiver$",              # 遥控/输入法/屏幕控制
    r"com\.oceanwing\.ota$",                   # 固件更新
    r"com\.sdmc\.bluetoothconnect$",           # 蓝牙遥控配对向导
    r"com\.sdmc\.bluetoothspeaker$",           # 蓝牙音箱
    r"com\.sdmc\.oemprovisionservice$",        # OEM 配置
    r"com\.sdmc\.btservice$",                  # 蓝牙遥控
    r"com\.sdmc\.service$",                    # 画质/USB OTA 管理
    r"com\.nvidia\.shield\.remote\.server$",   # SHIELD 手机遥控
    r"com\.zeasn\.whale\.saas$",               # 原生桌面（虽带广告）
    r"net\.oqee\.launcher$",                   # OQEE 主屏幕
    r"com\.nes\.remoteota\.six$",              # 蓝牙遥控固件
    r"com\.zhixin\.nebulasmart$",              # 遥控事件/无障碍
    r"com\.sony\.dtv\.m2\.seeds\.iot\.remotestart$",
    r"com\.sony\.dtv\.tvx$",                   # Live TV + 全部 HDMI 输入来源
    r"com\.spocky\.projengmenu$",
)

# ---------------------------------------------------------------------------
# 2. 已知包名库
#
# 2a. 真实数据库（tvzen/data/known-packages.json）：
#     1140 个包名，解析自 cleanyourtv 的 227 份真实机型清单。
#     精确匹配（字典查找，不做正则，避免 com.tcl.tv 误中 com.tcl.tvinput）。
#
# 2b. 下方 KNOWN_PACKAGES 为少量「真实存在」的家族正则，
#     覆盖数据库尚未收录的新变体（每条均已在真实清单中验证存在）。
# ---------------------------------------------------------------------------
KNOWN_PACKAGES: tuple[tuple[str, Category, Risk, str], ...] = (
    (r"com\.amazon\.ftvads\.", Category.ADS, Risk.SAFE,
     "Fire TV 广告 SDK"),
    (r"com\.amazon\.media\.recommendations", Category.PROMO, Risk.SAFE,
     "Fire TV 赞助推荐行"),
    (r"com\.google\.android\.adservices", Category.TELEMETRY, Risk.CAUTION,
     "Google Privacy Sandbox 广告服务"),
)

# ---------------------------------------------------------------------------
# 3. FORCE_CAUTION：命中即 CAUTION，并说明禁用后会失去什么。
#    每条模式都对应真实清单注释中记录的系统功能，不是拍脑袋。
# ---------------------------------------------------------------------------
FORCE_CAUTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"com\.apps\.ota$|com\.apps\.authota$|com\.softwinner\.update$"
     r"|com\.coocaa\.os\.upgrade$|com\.mediatek\.tv\.systemupdater$"
     r"|com\.droidlogic\.updater$|com\.realsil\.ota$|com\.hisense\.tv\.ota$"
     r"|com\.hisense\.remoteupgrade$|com\.htc\.htcotaupdate$"
     r"|com\.amazon\.device\.software\.ota|com\.nvidia\.ota$"
     r"|com\.xgimi\.ota\.accessories$|com\.airoha\.ble\.ota$"
     r"|com\.google\.android\.tv\.dfuservice$|com\.tcl\.ttvs$"
     r"|com\.homwee\.dmt\.upgrade$|com\.softwinner\.settingsassist$",
     "固件/配件 OTA 更新，禁用后无法检查更新"),
    (r"tvinput\.|com\.zeasn\.livetv$|com\.amazon\.franktvinput$",
     "直播电视信号源（天线/有线电视）"),
    (r"provision|com\.softwinner\.settingssetup$",
     "设备配置组件，恢复出厂前需先恢复"),
    (r"com\.android\.settings\.intelligence$|com\.zeasn\.whaleos\.settings$",
     "系统设置组件"),
    (r"com\.google\.android\.leanbacklauncher$|com\.tcl\.tv\.tclhome_(master|passive)$"
     r"|com\.htc\.htclauncher|com\.whaletv\.launcher$|com\.verizon\.tv\.launcher$"
     r"|com\.cvte\.tv\.launcher\.highend|com\.xiaomi\.eetv\.litehome$"
     r"|com\.dialog\.tv$|com\.htc\.expandsdk$",
     "桌面/主屏幕组件，需先装好替代桌面"),
    (r"cast\.sink$|miracast|airscreen|aircast|icast$|airkan|miplay|dialservice"
     r"|usbcastserver|toofifi|multiscreenshare|\.scast$|com\.apple\.airplay"
     r"|com\.sony\.dtv\.airplayapp$|com\.realtek\.airplay2$|com\.zeasn\.tv\.cast$"
     r"|dlna",
     "投屏/镜像/DLNA 功能"),
    (r"com\.android\.cellbroadcast",
     "紧急广播警报"),
    (r"inputmethod|keyboard",
     "输入法"),
    (r"matter|smarthome|smartpanel|cloudcontrol|ipcontrol|control4app",
     "智能家居控制"),
    (r"tr069|oemservice|device_remote_config|remotenow"
     r"|remotecontroller\.service|seeds\.iot|quicksetsdk|netflixobserver",
     "遥控器/远程管理相关"),
    (r"com\.apps\.wifihotspot$",
     "Wi-Fi 热点功能"),
)

# 用户偏好应用：被清单收录但属于「用不用因人而异」，禁用即不可逆体验损失
USER_APP_PATTERNS: tuple[str, ...] = (
    r"netflix", r"youtube", r"amazonvideo", r"primevideo", r"play\.games",
    r"com\.google\.android\.videos$", r"disney", r"spotify", r"twitch",
    r"hbonow|\bhbo\b|max\.", r"stan\.", r"appletv", r"crackle",
)

# ---------------------------------------------------------------------------
# 4. 启发式规则：包名包含这些 token 即加分（面向数据库未覆盖的新包）
#    (token, 类别, 权重分)
# ---------------------------------------------------------------------------
HEURISTIC_TOKENS: tuple[tuple[str, Category, int], ...] = (
    ("advert", Category.ADS, 60),
    ("ads", Category.ADS, 60),
    ("adservice", Category.ADS, 60),
    ("doubleclick", Category.ADS, 50),
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

# 冲突判定：被这么多个/份以上清单特意保留 → CAUTION
CONFLICT_KEEP_DEVICES = 2


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DbEntry:
    """真实数据库中的一条包记录。"""
    package: str
    category: Category
    devices: int          # 多少份真实清单禁用了它
    kept_devices: int     # 多少份真实清单特意保留它
    comment: str          # 清单原文注释（可能为空）


def _read_data_file(name: str) -> dict:
    try:  # 已安装形态：包内数据
        from importlib.resources import files
        text = files("tvzen").joinpath(f"data/{name}").read_text(encoding="utf-8")
    except Exception:  # 源码树形态
        text = (Path(__file__).resolve().parent.parent / "data" / name)\
            .read_text(encoding="utf-8")
    return json.loads(text)


def _load_db() -> dict[str, DbEntry]:
    payload = _read_data_file("known-packages.json")
    db: dict[str, DbEntry] = {}
    for item in payload["packages"]:
        db[item["package"]] = DbEntry(
            package=item["package"],
            category=Category(item["category"]),
            devices=item["devices"],
            kept_devices=item["kept_devices"],
            comment=item.get("comment", ""),
        )
    return db


DB: dict[str, DbEntry] = _load_db()


def db_stats() -> dict:
    """数据库统计（README / 报告 / 测试共用，保证口径一致）。"""
    from collections import Counter
    traps = _read_data_file("keep-traps.json")
    return {
        "known_packages": len(DB),
        "keep_traps": traps["count"],
        "source": traps["source"],
        "categories": dict(Counter(e.category.value for e in DB.values())),
        "conflict_packages": sum(1 for e in DB.values()
                                 if e.kept_devices >= CONFLICT_KEEP_DEVICES),
        "heuristic_tokens": len(HEURISTIC_TOKENS),
        "never_touch_patterns": len(NEVER_TOUCH_PATTERNS),
    }


# ---------------------------------------------------------------------------
# 裁决
# ---------------------------------------------------------------------------
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


def _resolve_db_risk(entry: DbEntry) -> tuple[Risk, str]:
    """数据驱动的风险分级：冲突 + 系统功能 + 用户应用 → CAUTION。"""
    risk: Risk = Risk.SAFE
    notes: list[str] = []
    if entry.kept_devices >= CONFLICT_KEEP_DEVICES:
        risk = Risk.CAUTION
        notes.append(f"{entry.kept_devices} 份清单特意保留")
    for pattern, note in FORCE_CAUTION_PATTERNS:
        if re.search(pattern, entry.package):
            risk = Risk.CAUTION
            notes.append(note)
            break
    for pattern in USER_APP_PATTERNS:
        if re.search(pattern, entry.package):
            risk = Risk.CAUTION
            notes.append("流媒体/游戏应用，不用再禁")
            break
    return risk, "；".join(notes)


def _score_db(package: str) -> PackageVerdict | None:
    entry = DB.get(package)
    if entry is None:
        return None
    risk, note = _resolve_db_risk(entry)
    reason = f"真实清单禁用（{entry.devices} 台设备）"
    if entry.comment:
        reason += f": {entry.comment}"
    if note:
        reason += f" ⚠️ {note}"
    return PackageVerdict(package, entry.category, risk, 100, reason, package)


def score_package(package: str,
                  known: Iterable[tuple[str, Category, Risk, str]] | None = None,
                  tokens: Iterable[tuple[str, Category, int]] = HEURISTIC_TOKENS) -> PackageVerdict:
    """对单个包名打分并给出裁决。

    优先级：never-touch 白名单 > 真实已知包名库 > 家族正则 > 启发式规则 > 放过。
    known 参数仅供测试注入自定义规则；默认 None 时走真实数据库。
    """
    if _is_never_touch(package):
        return PackageVerdict(package, Category.UNKNOWN, Risk.CRITICAL, 0,
                              "系统关键组件（白名单保护）")

    if known is None:
        verdict = _score_db(package)
        if verdict is not None:
            return verdict
        known = KNOWN_PACKAGES

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
