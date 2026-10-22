"""快照与回滚：每次净化前自动快照，支持一键还原。

快照是 JSON 文件，记录：设备信息、被禁用的包、时间戳、TVZen 版本。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Snapshot:
    version: str
    serial: str
    model: str
    created_at: float
    disabled: list[str] = field(default_factory=list)
    action: str = "disable"      # disable | uninstall

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Snapshot":
        return cls(**json.loads(text))

    def save(self, directory: str | Path) -> Path:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.created_at))
        path = d / f"tvzen-{self.serial}-{ts}.json"
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Snapshot":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def latest_for(cls, directory: str | Path, serial: str) -> "Snapshot | None":
        d = Path(directory)
        if not d.exists():
            return None
        snaps = sorted(d.glob(f"tvzen-{serial}-*.json"))
        if not snaps:
            return None
        return cls.load(snaps[-1])

    def describe(self) -> str:
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.created_at))
        return (f"快照 {when} · 设备 {self.model or self.serial} · "
                f"动作 {self.action} · {len(self.disabled)} 个包")
