"""Filesystem paths used by xd launcher."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _default_root() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "xd-launcher"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "xd-launcher"
    return Path.home() / ".xd-launcher"


ROOT: Path = _default_root()
MINECRAFT_DIR: Path = ROOT / "minecraft"
JAVA_DIR: Path = ROOT / "java"
ACCOUNTS_FILE: Path = ROOT / "accounts.json"
CONFIG_FILE: Path = ROOT / "config.json"
BACKGROUND_FILE: Path = ROOT / "background.png"
MODS_DIR: Path = MINECRAFT_DIR / "mods"
RESOURCEPACKS_DIR: Path = MINECRAFT_DIR / "resourcepacks"
SHADERS_DIR: Path = MINECRAFT_DIR / "shaderpacks"


def ensure_dirs() -> None:
    for d in (ROOT, MINECRAFT_DIR, JAVA_DIR, MODS_DIR, RESOURCEPACKS_DIR, SHADERS_DIR):
        d.mkdir(parents=True, exist_ok=True)
