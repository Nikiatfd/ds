"""Launcher configuration persistence."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .paths import CONFIG_FILE, ensure_dirs


DEFAULT_OPTIMIZED_ARGS = (
    "-XX:+UnlockExperimentalVMOptions "
    "-XX:+UseG1GC "
    "-XX:G1NewSizePercent=20 "
    "-XX:G1ReservePercent=20 "
    "-XX:MaxGCPauseMillis=50 "
    "-XX:G1HeapRegionSize=32M "
    "-XX:+DisableExplicitGC "
    "-XX:+AlwaysPreTouch "
    "-XX:+ParallelRefProcEnabled"
)


@dataclass
class LauncherConfig:
    selected_version: str = "1.20.1"
    selected_account: str = ""
    ram_mb: int = 2048
    width: int = 925
    height: int = 350
    java_path: str = ""  # empty = auto
    use_bundled_java: bool = True
    extra_jvm_args: str = ""
    optimized_args: str = DEFAULT_OPTIMIZED_ARGS
    use_optimized: bool = True
    wrapper_command: str = ""  # e.g. "prime-run" or "optirun"
    gpu_mode: str = "auto"  # auto | discrete | integrated
    background_path: str = ""
    last_modrinth_dir: str = ""

    @classmethod
    def load(cls) -> "LauncherConfig":
        ensure_dirs()
        if not CONFIG_FILE.exists():
            cfg = cls()
            cfg.save()
            return cfg
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        cfg = cls()
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    def save(self) -> None:
        ensure_dirs()
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
