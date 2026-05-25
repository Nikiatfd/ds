"""Minecraft version install + launch wrappers around minecraft-launcher-lib."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import Callable, List, Optional

from .paths import MINECRAFT_DIR, ensure_dirs


# Versions that the user explicitly asked us to surface in the UI.
SUPPORTED_VERSIONS: List[str] = ["1.20.1", "1.16.5", "1.12.2"]


def _mll():
    """Import minecraft-launcher-lib lazily so the launcher still imports
    on machines where it's not installed yet."""
    import minecraft_launcher_lib  # type: ignore
    return minecraft_launcher_lib


def list_installed_versions() -> List[str]:
    ensure_dirs()
    try:
        mll = _mll()
        installed = mll.utils.get_installed_versions(str(MINECRAFT_DIR))
        return [v["id"] for v in installed]
    except Exception:
        return []


def list_available_versions() -> List[str]:
    """Combine the user's requested versions with anything already installed."""
    out = list(SUPPORTED_VERSIONS)
    for v in list_installed_versions():
        if v not in out:
            out.append(v)
    return out


def install_version(version_id: str, callback=None) -> None:
    """Download Minecraft `version_id` into the game directory."""
    ensure_dirs()
    mll = _mll()
    cb = callback or {}
    mll.install.install_minecraft_version(version_id, str(MINECRAFT_DIR), callback=cb)


def build_launch_command(
    version_id: str,
    username: str,
    uuid: str,
    token: str,
    java_path: str,
    ram_mb: int,
    width: int,
    height: int,
    extra_jvm: str,
    optimized_jvm: str,
    use_optimized: bool,
) -> List[str]:
    """Compose the java command to launch a given Minecraft version."""
    mll = _mll()
    jvm_args: List[str] = [f"-Xmx{ram_mb}M", f"-Xms{max(512, ram_mb // 2)}M"]
    if use_optimized and optimized_jvm.strip():
        jvm_args += shlex.split(optimized_jvm)
    if extra_jvm.strip():
        jvm_args += shlex.split(extra_jvm)

    options = {
        "username": username,
        "uuid": uuid,
        "token": token,
        "executablePath": java_path,
        "jvmArguments": jvm_args,
        "customResolution": True,
        "resolutionWidth": str(width),
        "resolutionHeight": str(height),
        "launcherName": "xd launcher",
        "launcherVersion": "1.0.0",
        "gameDirectory": str(MINECRAFT_DIR),
    }
    cmd = mll.command.get_minecraft_command(
        version_id, str(MINECRAFT_DIR), options
    )
    return cmd


def launch(
    cmd: List[str],
    wrapper: str = "",
    env_overrides: Optional[dict] = None,
) -> subprocess.Popen:
    """Spawn the Minecraft process detached from the launcher."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    final_cmd = list(cmd)
    if wrapper.strip():
        final_cmd = shlex.split(wrapper) + final_cmd
    creationflags = 0
    if sys.platform.startswith("win"):
        # DETACHED_PROCESS so closing launcher doesn't kill game
        creationflags = 0x00000008
    return subprocess.Popen(
        final_cmd,
        cwd=str(MINECRAFT_DIR),
        env=env,
        creationflags=creationflags,
    )
