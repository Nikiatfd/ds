"""Java detection and Adoptium auto-download.

Different Minecraft versions require different Java majors:
- <= 1.16.5  -> Java 8
- 1.17 / 1.18 / 1.19 / 1.20 -> Java 17
- 1.20.5+  -> Java 21
"""
from __future__ import annotations

import io
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable, Optional

from .paths import JAVA_DIR


def required_java_major(version_id: str) -> int:
    """Return required Java major version for a given Minecraft version id."""
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", version_id)
    if not m:
        return 17
    major = int(m.group(2))
    patch = int(m.group(3) or 0)
    if major <= 16:
        return 8
    if major < 20:
        return 17
    if major == 20 and patch < 5:
        return 17
    return 21


def _platform_tag() -> tuple[str, str, str]:
    """Return (os, arch, ext) for Adoptium API."""
    os_name = sys.platform
    if os_name.startswith("win"):
        os_tag = "windows"
        ext = "zip"
    elif os_name == "darwin":
        os_tag = "mac"
        ext = "tar.gz"
    else:
        os_tag = "linux"
        ext = "tar.gz"

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "aarch64"
    elif machine.startswith("arm"):
        arch = "arm"
    elif machine in ("i386", "i686", "x86"):
        arch = "x86"
    else:
        arch = "x64"
    return os_tag, arch, ext


def _java_executable_path(install_dir: Path) -> Optional[Path]:
    """Locate `java`/`java.exe` inside an Adoptium extraction."""
    exe = "java.exe" if sys.platform.startswith("win") else "java"
    candidates = list(install_dir.rglob(exe))
    # Prefer paths under bin/
    bin_candidates = [c for c in candidates if c.parent.name == "bin"]
    if bin_candidates:
        return bin_candidates[0]
    if candidates:
        return candidates[0]
    return None


def find_system_java(major: int) -> Optional[str]:
    """Look for a system-wide Java binary with the right major version."""
    exe = "java.exe" if sys.platform.startswith("win") else "java"
    path = shutil.which(exe)
    if not path:
        return None
    try:
        out = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=10
        )
        text = (out.stderr or "") + (out.stdout or "")
        m = re.search(r'version "(\d+)(?:\.(\d+))?', text)
        if not m:
            return None
        ver_major = int(m.group(1))
        if ver_major == 1:
            ver_major = int(m.group(2) or 0)
        if ver_major == major:
            return path
    except Exception:
        return None
    return None


def find_local_java(major: int) -> Optional[str]:
    """Find a previously downloaded Java install for the given major."""
    install_dir = JAVA_DIR / f"jdk{major}"
    if not install_dir.exists():
        return None
    exe = _java_executable_path(install_dir)
    return str(exe) if exe else None


def adoptium_download_url(major: int) -> str:
    os_tag, arch, _ = _platform_tag()
    return (
        f"https://api.adoptium.net/v3/binary/latest/{major}/ga/"
        f"{os_tag}/{arch}/jre/hotspot/normal/eclipse"
    )


def download_java(major: int, progress=None) -> str:
    """Download and extract Adoptium JRE for the given Java major.

    `progress` is optional callable(received_bytes, total_bytes, message).
    Returns the absolute path to the java executable.
    """
    install_dir = JAVA_DIR / f"jdk{major}"
    install_dir.mkdir(parents=True, exist_ok=True)
    existing = _java_executable_path(install_dir)
    if existing:
        return str(existing)

    url = adoptium_download_url(major)
    if progress:
        progress(0, 0, f"Скачиваю Java {major}...")

    req = urllib.request.Request(url, headers={"User-Agent": "xd-launcher"})
    with urllib.request.urlopen(req) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        received = 0
        chunk = 1024 * 64
        while True:
            data = resp.read(chunk)
            if not data:
                break
            buf.write(data)
            received += len(data)
            if progress:
                progress(received, total, f"Скачиваю Java {major}...")
        buf.seek(0)

    _, _, ext = _platform_tag()
    if progress:
        progress(received, total, f"Распаковываю Java {major}...")
    if ext == "zip":
        with zipfile.ZipFile(buf) as zf:
            zf.extractall(install_dir)
    else:
        with tarfile.open(fileobj=buf, mode="r:gz") as tf:
            tf.extractall(install_dir)

    exe = _java_executable_path(install_dir)
    if not exe:
        raise RuntimeError("Не удалось найти java после распаковки")
    return str(exe)


def resolve_java_for(version_id: str, prefer_bundled: bool, manual_path: str,
                     progress=None) -> str:
    """Resolve which java executable to use for a Minecraft version."""
    if manual_path and not prefer_bundled:
        p = Path(manual_path)
        if p.exists():
            return str(p)
    major = required_java_major(version_id)
    local = find_local_java(major)
    if local:
        return local
    if not prefer_bundled:
        sys_java = find_system_java(major)
        if sys_java:
            return sys_java
    return download_java(major, progress=progress)
