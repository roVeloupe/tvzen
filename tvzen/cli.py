"""TVZen 命令行入口。

子命令:
  tvzen discover [--lan CIDR]          发现设备（USB + 局域网）
  tvzen scan [-d 序列号]               扫描并输出净化计划
  tvzen clean [-d 序列号] [--yes]      执行净化（默认禁用，可回滚）
  tvzen rollback [-d 序列号] [--latest | --snapshot 文件]
  tvzen report [-d 序列号] [-o 文件]   生成 HTML/JSON 报告
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __prog__, __version__
from .core.adb import AdbClient, AdbError
from .core.discover import discover, local_cidr
from .core.engine import Engine
from .core.policies import Category
from .core.report import render_plan, render_result, save_report, to_json
from .core.snapshot import Snapshot


def _resolve_device(client: AdbClient, serial: str | None) -> str:
    if serial:
        return serial
    devices = client.devices()
    ready = [d for d in devices if d.state == "device"]
    if not ready:
        print("❌ 未发现可用设备。请用数据线连接电视（开启 USB 调试），"
              "或用 `tvzen discover --lan 192.168.1.0/24` 扫描局域网。", file=sys.stderr)
        sys.exit(2)
    if len(ready) > 1:
        print("发现多台设备，请用 -d 指定：")
        for d in ready:
            print(f"  -d {d.serial}  ({d.model or '未知型号'})")
        sys.exit(2)
    return ready[0].serial


def cmd_discover(args) -> int:
    client = AdbClient()
    cidr = args.lan or (local_cidr() if not args.usb_only else None)
    result = discover(client, cidr)
    print("🧘 TVZen 设备发现")
    if result.usb:
        print("\n[USB]")
        for d in result.usb:
            print(f"  {d.serial}  {d.model or ''}  {d.brand or ''}")
    if result.lan:
        print("\n[局域网]")
        for addr in result.lan:
            print(f"  {addr}")
    if not result.usb and not result.lan:
        print("未发现设备。提示：Android 11+ 电视可在 设置→关于→版本号连按 5 次开启开发者选项，"
              "然后在 开发者选项→无线调试 中配对（tvzen 暂支持手动 adb connect）。")
    return 0


def cmd_scan(args) -> int:
    client = AdbClient()
    serial = _resolve_device(client, args.device)
    cats = {Category(c) for c in args.categories.split(",")} if args.categories else None
    engine = Engine(client)
    plan, _ = engine.scan(serial, cats, include_caution=not args.safe_only)
    print(render_plan(plan))
    if args.json:
        print()
        print(to_json(plan))
    return 0


def cmd_clean(args) -> int:
    client = AdbClient()
    serial = _resolve_device(client, args.device)
    cats = {Category(c) for c in args.categories.split(",")} if args.categories else None
    engine = Engine(client)
    plan, _ = engine.scan(serial, cats, include_caution=not args.safe_only)
    print(render_plan(plan))
    if not plan.targets:
        return 0
    if not args.yes:
        ans = input(f"\n确认禁用以上 {plan.count} 个包？（默认禁用，可回滚）[y/N] ")
        if ans.strip().lower() not in ("y", "yes"):
            print("已取消。")
            return 1
    res = engine.apply(serial, plan, action="uninstall" if args.uninstall else "disable")
    print()
    print(render_result(plan, res))
    return 0 if not res.failed else 1


def cmd_rollback(args) -> int:
    client = AdbClient()
    serial = _resolve_device(client, args.device)
    engine = Engine(client)
    if args.snapshot:
        snap = Snapshot.load(args.snapshot)
    else:
        snap = Snapshot.latest_for(engine.snapshot_dir, serial)
        if not snap:
            print(f"未找到设备 {serial} 的快照。", file=sys.stderr)
            return 2
    print(f"↩️  {snap.describe()}")
    res = engine.rollback(serial, snap)
    print(f"✅ 已恢复 {len(res.applied)} 个包" +
          (f"；失败 {len(res.failed)} 个" if res.failed else ""))
    return 0


def cmd_report(args) -> int:
    client = AdbClient()
    serial = _resolve_device(client, args.device)
    engine = Engine(client)
    plan, _ = engine.scan(serial, include_caution=not args.safe_only)
    path = save_report(plan, args.output, fmt=args.format)
    print(f"📄 报告已生成: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=__prog__,
        description="🧘 TVZen — Your TV, finally yours. "
                    "一键净化 Android TV / Google TV / Fire TV：去广告、去预装、可回滚。")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="发现设备（USB + 局域网扫描）")
    d.add_argument("--lan", help="局域网网段，如 192.168.1.0/24")
    d.add_argument("--usb-only", action="store_true", help="只列 USB 设备")
    d.set_defaults(func=cmd_discover)

    s = sub.add_parser("scan", help="扫描并输出净化计划（不改动设备）")
    s.add_argument("-d", "--device", help="设备序列号（单设备时可省略）")
    s.add_argument("--categories", help="只扫描指定类别，如 ads,bloat")
    s.add_argument("--safe-only", action="store_true", help="只保留安全级目标")
    s.add_argument("--json", action="store_true", help="同时输出 JSON")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("clean", help="执行净化（默认禁用，自动快照可回滚）")
    c.add_argument("-d", "--device")
    c.add_argument("--categories")
    c.add_argument("--safe-only", action="store_true")
    c.add_argument("--yes", "-y", action="store_true", help="跳过确认")
    c.add_argument("--uninstall", action="store_true",
                   help="用户级卸载（更彻底，但恢复需重装；谨慎使用）")
    c.set_defaults(func=cmd_clean)

    r = sub.add_parser("rollback", help="按快照恢复被禁用的包")
    r.add_argument("-d", "--device")
    r.add_argument("--snapshot", help="指定快照文件（默认用该设备最新快照）")
    r.set_defaults(func=cmd_rollback)

    rep = sub.add_parser("report", help="生成净化报告（html/json）")
    rep.add_argument("-d", "--device")
    rep.add_argument("-o", "--output", default="tvzen-report.html")
    rep.add_argument("-f", "--format", choices=["html", "json"], default="html")
    rep.add_argument("--safe-only", action="store_true")
    rep.set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except AdbError as e:
        print(f"❌ ADB 错误: {e}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
