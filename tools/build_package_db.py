#!/usr/bin/env python3
"""从 cleanyourtv 的 227 份真实机型 debloat 清单解析结构化包名库。

输入: /tmp/debloat-lists/*.txt
输出:
  data/known-packages.json  — 可禁用的真实包名库（含分类、设备覆盖数、冲突数、代表注释）
  data/keep-traps.json      — KEEP 陷阱包（像垃圾实为命脉，进 never-touch 白名单）

数据质量控制:
  - 过滤散文行（包名后带逗号/句号/继续小写文字的，不是包条目）
  - 记录每个包「被禁用的设备数」与「被保留的设备数」——冲突数驱动风险分级
  - 保留原始 section 名称，保证可追溯、可验证
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

LISTS_DIR = Path("/tmp/debloat-lists")
OUT_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

PKG_RE = re.compile(r"^([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)$")
# 分类标题: "# Words Words"（允许少量点，如 "com." 不出现在标题）
SECTION_RE = re.compile(r"^#\s+([A-Z][A-Za-z0-9 ,/()'&+-]{2,60})\s*$")


def map_category(raw: str) -> str:
    """真实清单 section 标题 → 引擎 Category。优先级: 遥测 > 演示 > 广告 > 预装。"""
    r = raw.lower()
    if any(k in r for k in ("acr", "tracker", "telemetry", "feedback",
                            "statistic", "background service", "data collect",
                            "usage data", "crash")):
        return "telemetry"
    if "demo" in r or "retail" in r:
        return "bloat"
    if " ad" in f" {r}" or "ads" in r or "promo" in r:
        return "ads"
    return "bloat"


# Uncategorized 条目（清单里没带分类标题）按包名/注释特征推断
NAME_CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    (r"advert|ads|adservice|banner|doubleclick|promo|splashad", "ads"),
    (r"recommend|suggest|discover|partnercustomizer|oemtab", "promo"),
    (r"statistic|telemetry|tracking|feedback|bugreport|report|uploadlog"
     r"|acr|samba|analytic|usage|collect", "telemetry"),
)


def infer_category(package: str, comment: str) -> str:
    text = f"{package} {comment}".lower()
    for pattern, cat in NAME_CATEGORY_RULES:
        if re.search(pattern, text):
            return cat
    return "bloat"


def is_prose_package(token: str) -> bool:
    """包名条目判定：单个 token，无尾随标点。"""
    if not PKG_RE.match(token):
        return True
    return False


def parse_file(path: Path):
    """返回 (active: [(pkg, section, comment)], keep: [(pkg, comment)])"""
    active, keep = [], []
    section = "Uncategorized"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or not s.startswith("#") and not s:
            pass
        # 分类标题行
        m = SECTION_RE.match(s)
        if m:
            cand = m.group(1).strip()
            # 标题不含典型包名结构（连续两个点分层级）
            if ".." not in cand and not re.search(r"\w\.\w+\.\w+", cand):
                section = cand
                continue
        if s.startswith("#"):
            inner = s.lstrip("#").strip()
            # 注释包的行: "pkg" 或 "pkg   # comment"
            pkg_part = inner.split("#", 1)[0].strip()
            comment = inner.split("#", 1)[1].strip() if "#" in inner else ""
            if pkg_part and not is_prose_package(pkg_part):
                keep.append((pkg_part, comment))
            continue
        # 激活包: "pkg" 或 "pkg  # comment"
        pkg_part = s.split("#", 1)[0].strip()
        comment = s.split("#", 1)[1].strip() if "#" in s else ""
        if pkg_part and not is_prose_package(pkg_part):
            active.append((pkg_part, section, comment))
    return active, keep


def main():
    disabled = defaultdict(lambda: {"devices": set(), "sections": defaultdict(int),
                                    "comments": []})
    kept = defaultdict(lambda: {"devices": set(), "comments": []})

    files = sorted(LISTS_DIR.glob("*.txt"))
    if not files:
        sys.exit("no lists found")

    for f in files:
        device = f.stem
        active, keep = parse_file(f)
        for pkg, section, comment in active:
            e = disabled[pkg]
            e["devices"].add(device)
            e["sections"][section] += 1
            if comment:
                e["comments"].append(comment)
        for pkg, comment in keep:
            e = kept[pkg]
            e["devices"].add(device)
            if comment:
                e["comments"].append(comment)

    known = []
    for pkg, e in sorted(disabled.items(), key=lambda kv: -len(kv[1]["devices"])):
        section = max(e["sections"].items(), key=lambda kv: kv[1])[0]
        if section == "Uncategorized":
            comments = [c for c in e["comments"] if c]
            category = infer_category(pkg, comments[0] if comments else "")
        else:
            category = map_category(section)
        comments = [c for c in e["comments"] if c]
        rep = min(comments, key=len) if comments else ""
        kept_n = len(kept.get(pkg, {}).get("devices", ()))
        known.append({
            "package": pkg,
            "category": category,
            "section": section,
            "devices": len(e["devices"]),
            "kept_devices": kept_n,
            "comment": rep,
        })

    traps = [{"package": p, "devices": len(e["devices"]),
              "comment": min([c for c in e["comments"] if c], key=len, default="")}
             for p, e in sorted(kept.items(), key=lambda kv: -len(kv[1]["devices"]))]

    out = OUT_DIR / "data"
    out.mkdir(parents=True, exist_ok=True)
    (out / "known-packages.json").write_text(
        json.dumps({"source": "Gathin23/cleanyourtv — 227 real device debloat lists",
                    "count": len(known), "packages": known},
                   ensure_ascii=False, indent=1))
    (out / "keep-traps.json").write_text(
        json.dumps({"source": "Gathin23/cleanyourtv — KEEP annotations",
                    "count": len(traps), "packages": traps},
                   ensure_ascii=False, indent=1))

    print(f"known packages : {len(known)}")
    print(f"keep traps     : {len(traps)}")
    print(f"device lists   : {len(files)}")
    conflicts = [k for k in known if k["kept_devices"] >= 2]
    print(f"conflict pkgs  : {len(conflicts)} (kept on >=2 devices)")
    print("\nTOP 15 known:")
    for k in known[:15]:
        print(f"  {k['devices']:>3}dev kept:{k['kept_devices']:<2} {k['category']:<10} {k['package']}")
    print("\nTOP 15 conflicts (CAUTION):")
    for k in conflicts[:15]:
        print(f"  dis:{k['devices']:>3} keep:{k['kept_devices']:<2} {k['package']}  {k['comment'][:60]}")
    print("\nTOP 15 keep traps:")
    for t in traps[:15]:
        print(f"  {t['devices']:>3}dev  {t['package']}  {t['comment'][:50]}")


if __name__ == "__main__":
    main()
