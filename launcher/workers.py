"""QThread workers for long-running tasks (install version, download Java)."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import minecraft, java_manager


class InstallWorker(QThread):
    progress = pyqtSignal(int, int, str)  # current, total, message
    finished_ok = pyqtSignal()
    finished_err = pyqtSignal(str)

    def __init__(self, version_id: str, prefer_bundled: bool, manual_java: str):
        super().__init__()
        self.version_id = version_id
        self.prefer_bundled = prefer_bundled
        self.manual_java = manual_java
        self._total = 1
        self._status = ""

    def _set_status(self, text: str) -> None:
        self._status = text
        self.progress.emit(0, self._total, text)

    def _set_progress(self, value: int) -> None:
        self.progress.emit(int(value), int(self._total), self._status)

    def _set_max(self, value: int) -> None:
        self._total = max(1, int(value))
        self.progress.emit(0, self._total, self._status)

    def run(self) -> None:
        try:
            # Step 1 — Java
            def java_progress(rec, tot, msg):
                self.progress.emit(int(rec), int(max(tot, 1)), msg)

            java_manager.resolve_java_for(
                self.version_id,
                self.prefer_bundled,
                self.manual_java,
                progress=java_progress,
            )

            # Step 2 — Minecraft files
            cb = {
                "setStatus": self._set_status,
                "setProgress": self._set_progress,
                "setMax": self._set_max,
            }
            minecraft.install_version(self.version_id, callback=cb)
            self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))


class JavaDownloadWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(str)
    finished_err = pyqtSignal(str)

    def __init__(self, major: int):
        super().__init__()
        self.major = major

    def run(self) -> None:
        try:
            path = java_manager.download_java(
                self.major,
                progress=lambda r, t, m: self.progress.emit(int(r), int(max(t, 1)), m),
            )
            self.finished_ok.emit(path)
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))
