"""Hardware introspection: RAM amount and GPU enumeration."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import List


def total_ram_mb() -> int:
    """Return the system's total physical RAM in MiB."""
    try:
        import psutil  # type: ignore

        return int(psutil.virtual_memory().total / (1024 * 1024))
    except Exception:
        pass
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int((pages * page_size) / (1024 * 1024))
        except (ValueError, OSError):
            pass
    return 4096  # safe fallback


@dataclass
class GPU:
    name: str
    kind: str  # "discrete" | "integrated" | "unknown"


_INTEGRATED_HINTS = (
    "intel", "uhd", "iris", "vega", "radeon graphics", "apu", "integrated",
)
_DISCRETE_HINTS = (
    "nvidia", "geforce", "rtx", "gtx", "quadro", "radeon rx", "radeon pro",
    "arc a", "discrete",
)


def _classify(name: str) -> str:
    n = name.lower()
    for h in _DISCRETE_HINTS:
        if h in n:
            return "discrete"
    for h in _INTEGRATED_HINTS:
        if h in n:
            return "integrated"
    return "unknown"


def list_gpus() -> List[GPU]:
    """Best-effort list of GPUs available on the system."""
    gpus: List[GPU] = []
    if sys.platform.startswith("win"):
        try:
            out = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "Name"],
                capture_output=True, text=True, timeout=5,
            )
            for line in out.stdout.splitlines()[1:]:
                line = line.strip()
                if line:
                    gpus.append(GPU(name=line, kind=_classify(line)))
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=10,
            )
            for line in out.stdout.splitlines():
                line = line.strip()
                if line.startswith("Chipset Model:"):
                    name = line.split(":", 1)[1].strip()
                    gpus.append(GPU(name=name, kind=_classify(name)))
        except Exception:
            pass
    else:
        if shutil.which("lspci"):
            try:
                out = subprocess.run(
                    ["lspci"], capture_output=True, text=True, timeout=5
                )
                for line in out.stdout.splitlines():
                    low = line.lower()
                    if "vga" in low or "3d controller" in low or "display" in low:
                        name = line.split(":", 2)[-1].strip()
                        gpus.append(GPU(name=name, kind=_classify(name)))
            except Exception:
                pass
    if not gpus:
        gpus.append(GPU(name="Неизвестный GPU", kind="unknown"))
    return gpus


def gpu_launch_env(mode: str) -> dict:
    """Return environment overrides to force a specific GPU.

    mode: "auto" | "discrete" | "integrated"
    """
    env: dict = {}
    if mode == "discrete":
        if sys.platform.startswith("linux"):
            # NVIDIA PRIME offload + Mesa DRI prime
            env["__NV_PRIME_RENDER_OFFLOAD"] = "1"
            env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
            env["__VK_LAYER_NV_optimus"] = "NVIDIA_only"
            env["DRI_PRIME"] = "1"
        # Windows hint - drivers honor these in some configs
        env["SHIM_MCCOMPAT"] = "0x800000001"
    elif mode == "integrated":
        if sys.platform.startswith("linux"):
            env["DRI_PRIME"] = "0"
        env["SHIM_MCCOMPAT"] = "0x800000000"
    return env


def gpu_wrapper_command(mode: str) -> str:
    """Return a wrapper command for the GPU mode, if applicable."""
    if mode == "discrete" and sys.platform.startswith("linux"):
        if shutil.which("prime-run"):
            return "prime-run"
    return ""
