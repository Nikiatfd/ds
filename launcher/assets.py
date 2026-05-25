"""Asset routing: drop a mod / pack file into the right folder."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal, Optional, Tuple

from .paths import MODS_DIR, RESOURCEPACKS_DIR, SHADERS_DIR, ensure_dirs

AssetKind = Literal["mod", "resourcepack", "shader", "unknown"]


def classify(path: Path) -> AssetKind:
    """Best-effort: identify a downloaded file as mod / pack / shader.

    Resource packs and shaders are both `.zip`; we look for hints in the
    filename. Shaders almost always include "shader", "iris" or known names
    like BSL/SEUS/Sildurs/Complementary.
    """
    name = path.name.lower()
    if name.endswith(".jar"):
        return "mod"
    if name.endswith(".zip"):
        shader_hints = (
            "shader", "iris", "bsl", "seus", "sildur", "complementary",
            "chocapic", "skylec", "kuda", "rethinking",
        )
        if any(h in name for h in shader_hints):
            return "shader"
        rp_hints = ("resourcepack", "resource_pack", "texture", "pack")
        if any(h in name for h in rp_hints):
            return "resourcepack"
        return "resourcepack"
    return "unknown"


def install_asset(src: Path) -> Tuple[AssetKind, Optional[Path]]:
    """Copy a downloaded file into its proper folder. Returns kind + dest."""
    ensure_dirs()
    kind = classify(src)
    dest_dir = {
        "mod": MODS_DIR,
        "resourcepack": RESOURCEPACKS_DIR,
        "shader": SHADERS_DIR,
    }.get(kind)
    if not dest_dir:
        return kind, None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return kind, dest
