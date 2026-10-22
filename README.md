<div align="center">

# 🧘 TVZen

### Your TV, finally yours.

**One command to strip ads, bloatware and telemetry from Android TV / Google TV / Fire TV — with smart scoring, one-click rollback, and reports you can actually read.**

*一条命令，把广告、预装垃圾和遥测请出你的电视。智能识别、随时回滚、报告可读。*

[![CI](https://github.com/roVeloupe/tvzen/actions/workflows/ci.yml/badge.svg)](https://github.com/roVeloupe/tvzen/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-50%20passed-brightgreen)](#)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.9-blue?logo=python&logoColor=white)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#license)

</div>

---

## Why this exists · 为什么做这个

Your TV boots up. A full-screen ad appears. You open the home screen — half of it is a shopping mall. A push notification pops up for an app you never installed. **This is normal**, and everyone accepts it as normal.

电视一开机是全屏广告，首页一半是商城，动不动弹推送——人人都默认"电视就是这样"，但它本不该是这样。

Community scripts fix this by hardcoding package lists. **TVZen is built on a different bet**: a *suspicion-scoring engine* that combines a real-data package database with name-pattern heuristics — so it keeps working on firmware it has never seen, instead of silently missing everything new.

市面上的方案大多是"写死的包名清单"。TVZen 的赌注不同：**真实数据包名库 + 启发式可疑度评分**——面对从未见过的新固件，它照样能识别。

## The database is real · 数据是真的

Every package in TVZen's database is parsed from **227 real per-device debloat lists** maintained by the community ([cleanyourtv](https://github.com/Gathin23/cleanyourtv), 15K+ stars) — Sony BRAVIA, TCL/FFalcon, Xiaomi, Hisense/VIDAA, Skyworth/Coocaa, Philips, NVIDIA Shield, Amazon Fire TV, projectors and more. Each entry carries:

数据库里的每个包都解析自社区维护的 **227 份真实机型净化清单**（[cleanyourtv](https://github.com/Gathin23/cleanyourtv)），每条记录带三项可验证证据：

| 字段 | 含义 |
|---|---|
| `devices` | 多少份真实清单禁用了它（如 `com.google.android.feedback`：167 台） |
| `kept_devices` | 多少份清单**特意保留**它——社区有分歧的包自动降级为 CAUTION |
| `comment` | 清单原文注释（如 `com.tcl.tvinput`: "Live TV tuner + HDMI inputs"） |

Rebuild the database yourself: `python tools/build_package_db.py <dir-with-lists>`.
No invented package names — if it's in the DB, a real device list disabled it.

包名库可用 `tools/build_package_db.py` 从真实清单重新生成。**没有编造的包名**——库里的每个包都有真实清单佐证。

## Why not just another script · 为什么不是又一个脚本

| | 常见脚本 | **TVZen** |
|---|---|---|
| 识别方式 | 写死的包名清单 | 真实数据库（1140 包，带设备覆盖数）+ 启发式评分引擎 |
| 新固件/新品牌 | 静默漏掉 | 按包名特征自动打分 |
| 误伤风险 | 无保护，可能禁掉启动器 | never-touch 白名单（零遮蔽验证）+ 数据驱动风险分级 |
| 分歧包处理 | 一刀切 | 被多份清单保留的包自动 CAUTION，说明禁用后果 |
| 出问题怎么办 | 手动救砖 | 每次净化自动快照，一键回滚 |
| 结果 | 一串终端输出 | 终端表格 / JSON / HTML 报告 |
| 多台电视 | 一台台插线 | USB + 局域网自动发现 |

## Features · 特性

- 🧠 **Suspicion-scoring engine** — real-data database (1,140 packages) **plus** name-pattern heuristics (`ads`, `promo`, `push`, `analytics`, `vmall`…). Multi-token hits score higher. Unknown firmware is not a blind spot.
- ⚖️ **Data-driven risk grading** — a package kept by ≥2 real device lists is automatically downgraded to `caution`, with the trade-off spelled out (`OTA 更新`, `直播信号源`, `桌面`, `投屏`, `输入法`…).
- 🛡️ **Never-touch whitelist** — 48 patterns, each verified to cast zero shadow over the 1,140 real removable packages (regression-tested). Real KEEP-trap packages like `com.tcl.tvinput` ("Live TV tuner + HDMI inputs") are protected by anchored patterns.
- 💾 **Snapshot & one-click rollback** — every clean operation writes a timestamped JSON snapshot. `tvzen rollback` puts everything back.
- 📡 **Device discovery** — USB devices and LAN scanning (`:5555`), with concurrent probing.
- 📊 **Human-readable reports** — terminal tables, JSON for automation, and a shareable dark-theme HTML report.
- 🧪 **50 tests, CI on 4 Python versions** — the engine is unit-tested with a mock ADB runner; no TV required.

## Quick start · 快速开始

```bash
# 1. 安装（Python ≥ 3.9，无第三方依赖）
pip install tvzen

# 2. 发现你的电视（数据线连接并开启 USB 调试；或局域网无线调试）
tvzen discover

# 3. 扫描 → 查看净化计划 → 确认执行
tvzen scan
tvzen clean
```

That's it. Your TV boots to a clean home screen. Run `tvzen rollback` at any time to go back.

就这样。开机即是干净的首页。任何时候 `tvzen rollback` 一键还原。

## What a scan looks like · 扫描长什么样

Real engine output on the real package set of a Sony BRAVIA 4K GB (from the community list; see [`docs/scan-example.txt`](./docs/scan-example.txt) and a [live HTML report](./docs/report-example.html)):

```
🧘 TVZen 净化计划 · Sony BRAVIA 4K GB（模拟）
   设备共 39 个包，命中 31 个可净化目标

   包名                                   类别           风险     分数
   ----------------------------------------------------------------------
   tv.samba.ssm                            📡 遥测统计       安全     100
   com.sony.dtv.sonyselect                 📺 广告组件       安全     100
   com.sony.dtv.promos                     📺 广告组件       安全     100
   com.sony.dtv.demomode                   🗑️ 预装推广      安全     100
   com.google.android.feedback             📡 遥测统计       安全     100
   com.google.android.tvrecommendations    🛍️ 推广服务      安全     100
   com.google.android.apps.mediashell      🗑️ 预装推广      谨慎     100
   com.google.android.play.games           🗑️ 预装推广      谨慎     100
   com.google.android.tvlauncher           📺 广告组件       谨慎     100
   com.google.android.videos               🗑️ 预装推广      谨慎     100
   ...
```

Note how the packages the community deliberately keeps (Chromecast, Play Games, the stock launcher) come out as **caution**, not safe — that grading comes from the data, not from vibes.

注意看：社区特意保留的包（Chromecast、Play Games、原生桌面）全部被判为**谨慎**——这个分级来自数据，不是拍脑袋。

## Command reference · 命令参考

| 命令 | 作用 |
|---|---|
| `tvzen discover [--lan 192.168.1.0/24]` | 发现设备（USB + 局域网） |
| `tvzen scan [-d 序列号] [--json]` | 扫描并输出净化计划（**只读，不改设备**） |
| `tvzen clean [-d 序列号] [--safe-only] [-y]` | 执行净化（默认禁用，自动快照） |
| `tvzen rollback [--snapshot 文件]` | 按快照恢复被禁用的包 |
| `tvzen report -o report.html` | 生成可分享的 HTML 净化报告 |

Useful flags: `--categories ads,telemetry` to scope a clean · `--uninstall` for user-level uninstall (harder to reverse — read the warning first).

## How it works · 工作原理

```
tvzen scan
   │
   ├─ adb shell pm list packages ──► 全量包列表
   │
   ├─ never-touch whitelist ──────► 关键组件 → CRITICAL（结构性保护，零遮蔽）
   │
   ├─ real package database ─────► 命中 → 100 分 + 设备覆盖数佐证
   │                                 └─ kept ≥2 台 / 系统功能 / 用户应用 → CAUTION
   │
   └─ heuristic token scoring ───► 未命中库 → 按名称特征打分 ≥40 才纳入
                                        （多 token 命中加权）
   ▼
   净化计划（分类 / 风险 / 分数 / 原因）→ clean（默认禁用 + 快照）
```

Disable-by-default (`pm disable-user --user 0`) is deliberately chosen over uninstall: it fully removes ads from the UI **and** keeps every package recoverable. Uninstall is opt-in for those who want it.

默认用"禁用"而不是"卸载"是刻意设计：广告同样彻底消失，但每个包都可恢复。卸载需要显式 `--uninstall`。

## Safety · 安全设计

- **Whitelist first, with zero shadowing**: critical components are protected before any other rule runs — and a regression test asserts no whitelist pattern ever marks one of the 1,140 real removable packages as CRITICAL.
- **Conflict-aware grading**: packages the community disagrees about are never silently removed; they surface as `caution` with the reason.
- **Snapshot before every clean**: `~/.tvzen/snapshots/tvzen-<serial>-<timestamp>.json`.
- **Scan is read-only**: `tvzen scan` never touches the device. Run it first, always.
- **Open process**: every verdict carries its reason and matched rule — nothing is silently removed.

## Roadmap · 路线图

- [x] Core engine: real-data DB + heuristics + whitelist
- [x] Snapshot / rollback
- [x] Terminal / JSON / HTML reports
- [x] CI (4 Python versions, 50 tests)
- [ ] Desktop GUI (Tauri) with device discovery UI
- [ ] Community package-database contributions via PR
- [ ] Fire TV & Sony/Philips/TCL firmware coverage expansion

## Contributing · 贡献

Package-database PRs are the most valuable contributions: if your TV model has bloat TVZen misses (or flags something it shouldn't), open an issue or PR with the package name and what it does. Run `pytest` before submitting.

## Disclaimer · 免责声明

TVZen modifies package states on **your own devices**. `--uninstall` may affect system functionality; prefer the default disable mode and keep snapshots. The authors are not responsible for devices bricked by misuse. Use at your own risk.

TVZen 只修改**你自己的设备**。`--uninstall` 可能影响系统功能，请默认使用禁用模式并保留快照。因误用导致的问题作者不承担责任。

---

<div align="center">

**If your TV feels like an advertising billboard, give it a moment of zen.** 🧘

<sub>Built by <a href="https://github.com/roVeloupe">@roVeloupe</a> — Your TV, finally yours.</sub>

</div>
