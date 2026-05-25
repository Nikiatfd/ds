"""
XD Launcher — Python Minecraft launcher вдохновлённый Prizm Launcher.

Возможности:
  * Запуск Vanilla версий 1.12.2 / 1.16.5 / 1.20.1 (и любой другой добавленной)
  * Автоматическое определение RAM (psutil) и выбор объёма для игры
  * Кнопка «Открыть папку игры»
  * Авто-установка нужной Java для версии (через minecraft-launcher-lib runtime)
  * Кнопка «Перезагрузить список версий»
  * Поле произвольных Java-аргументов
  * Установка разрешения окна Minecraft (по умолчанию 925x350)
  * Готовый набор «оптимизированных» аргументов (G1GC и пр.)
  * Команда-обёртка (например `prime-run`, `optirun`, `gamemoderun ...`)
  * Выбор: своя Java или автоскачка
  * Кастомный фон главного окна
  * Выбор дискретной / встроенной видеокарты (NVIDIA / AMD env-vars)
  * Кнопка «Открыть Modrinth» + автосортировка скачанных файлов
        (.jar -> mods, ресурспаки -> resourcepacks, шейдеры -> shaders)
  * Управление аккаунтами (никами) — оффлайн режим
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import traceback
import uuid
import webbrowser
from pathlib import Path

try:
    import psutil
except Exception:  # pragma: no cover - psutil может отсутствовать в окружении
    psutil = None

try:
    import minecraft_launcher_lib as mll
except Exception:  # pragma: no cover - библиотека ставится из requirements
    mll = None

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QPixmap, QIcon, QPalette, QBrush, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "XD Launcher"
APP_DIR = Path.home() / ".xd_launcher"
GAME_DIR = APP_DIR / "minecraft"
JAVA_DIR = APP_DIR / "runtime"
CONFIG_FILE = APP_DIR / "config.json"
BG_FILE = APP_DIR / "background.png"

DEFAULT_VERSIONS = ["1.12.2", "1.16.5", "1.20.1"]
DEFAULT_RES_W, DEFAULT_RES_H = 925, 350

OPTIMIZED_JVM_ARGS = (
    "-XX:+UnlockExperimentalVMOptions -XX:+UseG1GC -XX:G1NewSizePercent=20 "
    "-XX:G1ReservePercent=20 -XX:MaxGCPauseMillis=50 -XX:G1HeapRegionSize=32M "
    "-XX:-UseAdaptiveSizePolicy -XX:-OmitStackTraceInFastThrow"
)


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
def _default_config() -> dict:
    return {
        "ram_mb": 2048,
        "java_path": "",          # пусто = авто-скачка
        "auto_java": True,
        "jvm_args": "",
        "extra_optimized": False,
        "wrapper_cmd": "",
        "res_w": DEFAULT_RES_W,
        "res_h": DEFAULT_RES_H,
        "gpu": "default",         # default / nvidia / amd / integrated
        "background": "",
        "accounts": [],
        "current_account": "",
        "selected_version": "1.20.1",
        "extra_versions": [],     # добавленные пользователем
    }


def load_config() -> dict:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    GAME_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            base = _default_config()
            base.update(data)
            return base
        except Exception:
            pass
    return _default_config()


def save_config(cfg: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Фоновые задачи (установка версии / Java / запуск)
# ---------------------------------------------------------------------------
class InstallThread(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, version: str, install_java: bool):
        super().__init__()
        self.version = version
        self.install_java = install_java

    def _sanitize_version_dir(self) -> None:
        """Удаляет пустые/битые version-файлы, оставшиеся от прерванных закачек.

        Если в `versions/<id>/<id>.json` лежит пустой или невалидный JSON,
        `minecraft-launcher-lib` падает на `json.load`. Чистим — она перекачает.
        """
        vdir = GAME_DIR / "versions" / self.version
        if not vdir.exists():
            return
        json_path = vdir / f"{self.version}.json"
        jar_path = vdir / f"{self.version}.jar"
        bad = False
        if json_path.exists():
            try:
                text = json_path.read_text(encoding="utf-8").strip()
                if not text:
                    bad = True
                else:
                    json.loads(text)
            except Exception:
                bad = True
        else:
            bad = True
        if bad:
            self.progress.emit(
                f"Обнаружен битый/пустой {json_path.name} — очищаю и перекачиваю..."
            )
            for p in (json_path, jar_path):
                try:
                    if p.exists():
                        p.unlink()
                except Exception as exc:
                    self.progress.emit(f"Не смог удалить {p}: {exc}")

    def run(self):
        if mll is None:
            self.failed.emit("minecraft-launcher-lib не установлен. pip install -r requirements.txt")
            return
        try:
            callback = {
                "setStatus": lambda s: self.progress.emit(str(s)),
                "setProgress": lambda v: None,
                "setMax": lambda v: None,
            }
            self._sanitize_version_dir()
            self.progress.emit(f"Устанавливаю Minecraft {self.version}...")
            try:
                mll.install.install_minecraft_version(
                    self.version, str(GAME_DIR), callback=callback
                )
            except json.JSONDecodeError:
                # Кто-то всё-таки оставил битый JSON — чистим ещё раз и повторяем.
                self.progress.emit("JSON версии повреждён, чищу и пробую снова...")
                self._sanitize_version_dir()
                mll.install.install_minecraft_version(
                    self.version, str(GAME_DIR), callback=callback
                )

            if self.install_java:
                try:
                    runtime = mll.runtime.get_executable_path("java-runtime-gamma", str(JAVA_DIR))
                    if not runtime:
                        self.progress.emit("Скачиваю Java runtime...")
                        mll.runtime.install_jvm_runtime(
                            "java-runtime-gamma", str(JAVA_DIR), callback=callback
                        )
                except Exception as exc:
                    self.progress.emit(f"Java runtime: {exc}")
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(f"{exc}\n{traceback.format_exc()}")


class LaunchThread(QThread):
    log = pyqtSignal(str)
    failed = pyqtSignal(str)
    finished_ok = pyqtSignal()

    def __init__(self, command: list[str], env: dict):
        super().__init__()
        self.command = command
        self.env = env

    def run(self):
        try:
            self.log.emit("$ " + " ".join(self.command))
            proc = subprocess.Popen(
                self.command,
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(GAME_DIR),
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                self.log.emit(line.rstrip())
            proc.wait()
            self.log.emit(f"[Процесс завершён, код {proc.returncode}]")
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# Диалог менеджера аккаунтов
# ---------------------------------------------------------------------------
class AccountDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Аккаунты")
        self.resize(380, 320)

        self.list = QListWidget()
        for nick in cfg.get("accounts", []):
            self.list.addItem(nick)

        add_btn = QPushButton("Добавить ник")
        del_btn = QPushButton("Удалить")
        set_btn = QPushButton("Сделать активным")
        close_btn = QPushButton("Закрыть")

        add_btn.clicked.connect(self.add)
        del_btn.clicked.connect(self.remove)
        set_btn.clicked.connect(self.set_active)
        close_btn.clicked.connect(self.accept)

        btns = QHBoxLayout()
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        btns.addWidget(set_btn)
        btns.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Оффлайн-аккаунты (никнеймы):"))
        layout.addWidget(self.list)
        layout.addLayout(btns)

    def add(self):
        nick, ok = QInputDialog.getText(self, "Новый ник", "Введите никнейм:")
        nick = nick.strip()
        if ok and nick:
            if nick not in self.cfg["accounts"]:
                self.cfg["accounts"].append(nick)
                self.list.addItem(nick)
                if not self.cfg.get("current_account"):
                    self.cfg["current_account"] = nick

    def remove(self):
        row = self.list.currentRow()
        if row < 0:
            return
        nick = self.list.item(row).text()
        self.cfg["accounts"].remove(nick)
        self.list.takeItem(row)
        if self.cfg.get("current_account") == nick:
            self.cfg["current_account"] = (
                self.cfg["accounts"][0] if self.cfg["accounts"] else ""
            )

    def set_active(self):
        row = self.list.currentRow()
        if row < 0:
            return
        nick = self.list.item(row).text()
        self.cfg["current_account"] = nick
        QMessageBox.information(self, "Активный аккаунт", f"Теперь играем за: {nick}")


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class XDLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.install_thread: InstallThread | None = None
        self.launch_thread: LaunchThread | None = None

        self.setWindowTitle(APP_NAME)
        self.resize(900, 600)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tab_play = QWidget()
        self.tab_settings = QWidget()
        self.tab_mods = QWidget()
        self.tab_log = QWidget()

        self.tabs.addTab(self.tab_play, "Играть")
        self.tabs.addTab(self.tab_settings, "Настройки")
        self.tabs.addTab(self.tab_mods, "Моды")
        self.tabs.addTab(self.tab_log, "Лог")

        self._build_play_tab()
        self._build_settings_tab()
        self._build_mods_tab()
        self._build_log_tab()

        self._apply_background()
        self._refresh_versions()

    # ------------------------ helpers ----------------------------
    def _apply_background(self) -> None:
        path = self.cfg.get("background") or ""
        if path and Path(path).exists():
            pix = QPixmap(path).scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(pix))
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._apply_background()

    # ------------------------ play tab ---------------------------
    def _build_play_tab(self) -> None:
        layout = QVBoxLayout(self.tab_play)

        title = QLabel(APP_NAME)
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Версия:"))
        self.version_combo = QComboBox()
        row1.addWidget(self.version_combo, 1)

        self.reload_btn = QPushButton("⟳ Перезагрузить")
        self.reload_btn.clicked.connect(self._refresh_versions)
        row1.addWidget(self.reload_btn)

        add_ver_btn = QPushButton("+ Добавить версию")
        add_ver_btn.clicked.connect(self._add_version)
        row1.addWidget(add_ver_btn)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Аккаунт:"))
        self.account_combo = QComboBox()
        self._refresh_accounts()
        self.account_combo.currentTextChanged.connect(self._on_account_changed)
        row2.addWidget(self.account_combo, 1)
        acc_btn = QPushButton("Аккаунты…")
        acc_btn.clicked.connect(self._open_accounts)
        row2.addWidget(acc_btn)
        layout.addLayout(row2)

        # Большая кнопка PLAY
        self.play_btn = QPushButton("▶  ИГРАТЬ")
        self.play_btn.setMinimumHeight(64)
        self.play_btn.setStyleSheet(
            "QPushButton{font-size:22px;font-weight:bold;"
            "background:#2ecc71;color:white;border-radius:12px;}"
            "QPushButton:hover{background:#27ae60;}"
            "QPushButton:disabled{background:#7f8c8d;}"
        )
        self.play_btn.clicked.connect(self._on_play)
        layout.addWidget(self.play_btn)

        row3 = QHBoxLayout()
        self.open_dir_btn = QPushButton("📁 Открыть папку игры")
        self.open_dir_btn.clicked.connect(self._open_game_dir)
        row3.addWidget(self.open_dir_btn)

        self.modrinth_btn = QPushButton("🌐 Modrinth")
        self.modrinth_btn.clicked.connect(lambda: webbrowser.open("https://modrinth.com"))
        row3.addWidget(self.modrinth_btn)
        layout.addLayout(row3)

        self.status = QLabel("Готов.")
        layout.addWidget(self.status)
        layout.addStretch(1)

    def _refresh_versions(self) -> None:
        self.version_combo.clear()
        seen: list[str] = []
        for v in DEFAULT_VERSIONS + list(self.cfg.get("extra_versions", [])):
            if v not in seen:
                seen.append(v)
        installed_dir = GAME_DIR / "versions"
        if installed_dir.exists():
            for sub in sorted(installed_dir.iterdir()):
                if sub.is_dir() and sub.name not in seen:
                    seen.append(sub.name)
        for v in seen:
            self.version_combo.addItem(v)
        sel = self.cfg.get("selected_version")
        if sel and sel in seen:
            self.version_combo.setCurrentText(sel)

    def _add_version(self) -> None:
        v, ok = QInputDialog.getText(self, "Версия", "ID версии (например 1.19.4):")
        v = v.strip()
        if ok and v:
            self.cfg.setdefault("extra_versions", []).append(v)
            save_config(self.cfg)
            self._refresh_versions()

    def _refresh_accounts(self) -> None:
        self.account_combo.clear()
        for nick in self.cfg.get("accounts", []):
            self.account_combo.addItem(nick)
        current = self.cfg.get("current_account")
        if current:
            self.account_combo.setCurrentText(current)

    def _on_account_changed(self, nick: str) -> None:
        if nick:
            self.cfg["current_account"] = nick
            save_config(self.cfg)

    def _open_accounts(self) -> None:
        dlg = AccountDialog(self.cfg, self)
        dlg.exec()
        save_config(self.cfg)
        self._refresh_accounts()

    def _open_game_dir(self) -> None:
        GAME_DIR.mkdir(parents=True, exist_ok=True)
        path = str(GAME_DIR)
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    # ------------------------ settings tab -----------------------
    def _build_settings_tab(self) -> None:
        layout = QVBoxLayout(self.tab_settings)

        # --- RAM ---
        ram_box = QGroupBox("Память (RAM)")
        ram_lay = QVBoxLayout(ram_box)
        total_mb = self._total_ram_mb()
        self.ram_label = QLabel()
        self.ram_slider = QSlider(Qt.Orientation.Horizontal)
        self.ram_slider.setMinimum(512)
        self.ram_slider.setMaximum(max(2048, total_mb))
        self.ram_slider.setSingleStep(256)
        self.ram_slider.setPageStep(512)
        self.ram_slider.setValue(min(self.cfg.get("ram_mb", 2048), self.ram_slider.maximum()))
        self.ram_slider.valueChanged.connect(self._on_ram_changed)
        ram_lay.addWidget(QLabel(f"Доступно ОЗУ: {total_mb} МБ"))
        ram_lay.addWidget(self.ram_slider)
        ram_lay.addWidget(self.ram_label)
        self._on_ram_changed(self.ram_slider.value())
        layout.addWidget(ram_box)

        # --- Java ---
        java_box = QGroupBox("Java")
        java_lay = QFormLayout(java_box)
        self.auto_java_chk = QCheckBox("Скачивать Java автоматически")
        self.auto_java_chk.setChecked(self.cfg.get("auto_java", True))
        self.auto_java_chk.stateChanged.connect(self._save_settings)
        self.java_path_edit = QLineEdit(self.cfg.get("java_path", ""))
        self.java_path_edit.editingFinished.connect(self._save_settings)
        browse_java = QPushButton("Обзор…")
        browse_java.clicked.connect(self._browse_java)
        java_row = QHBoxLayout()
        java_row.addWidget(self.java_path_edit, 1)
        java_row.addWidget(browse_java)
        java_lay.addRow(self.auto_java_chk)
        java_lay.addRow("Своя Java (путь):", _wrap(java_row))

        self.jvm_args_edit = QLineEdit(self.cfg.get("jvm_args", ""))
        self.jvm_args_edit.editingFinished.connect(self._save_settings)
        java_lay.addRow("Java-аргументы:", self.jvm_args_edit)

        self.opt_chk = QCheckBox("Использовать оптимизированные аргументы (G1GC)")
        self.opt_chk.setChecked(self.cfg.get("extra_optimized", False))
        self.opt_chk.stateChanged.connect(self._save_settings)
        java_lay.addRow(self.opt_chk)
        layout.addWidget(java_box)

        # --- Game ---
        game_box = QGroupBox("Игра")
        game_lay = QFormLayout(game_box)
        self.res_w_spin = QSpinBox()
        self.res_w_spin.setRange(320, 7680)
        self.res_w_spin.setValue(self.cfg.get("res_w", DEFAULT_RES_W))
        self.res_w_spin.valueChanged.connect(self._save_settings)
        self.res_h_spin = QSpinBox()
        self.res_h_spin.setRange(240, 4320)
        self.res_h_spin.setValue(self.cfg.get("res_h", DEFAULT_RES_H))
        self.res_h_spin.valueChanged.connect(self._save_settings)
        res_row = QHBoxLayout()
        res_row.addWidget(self.res_w_spin)
        res_row.addWidget(QLabel("x"))
        res_row.addWidget(self.res_h_spin)
        game_lay.addRow("Разрешение окна:", _wrap(res_row))

        self.wrapper_edit = QLineEdit(self.cfg.get("wrapper_cmd", ""))
        self.wrapper_edit.setPlaceholderText("например: gamemoderun")
        self.wrapper_edit.editingFinished.connect(self._save_settings)
        game_lay.addRow("Команда-обёртка:", self.wrapper_edit)

        self.gpu_combo = QComboBox()
        self.gpu_combo.addItems(
            ["default", "nvidia (дискретная)", "amd (дискретная)", "integrated (встроенная)"]
        )
        gpu = self.cfg.get("gpu", "default")
        index = {"default": 0, "nvidia": 1, "amd": 2, "integrated": 3}.get(gpu, 0)
        self.gpu_combo.setCurrentIndex(index)
        self.gpu_combo.currentIndexChanged.connect(self._save_settings)
        game_lay.addRow("Видеокарта:", self.gpu_combo)
        layout.addWidget(game_box)

        # --- Внешний вид ---
        bg_box = QGroupBox("Внешний вид")
        bg_lay = QHBoxLayout(bg_box)
        self.bg_path_edit = QLineEdit(self.cfg.get("background", ""))
        bg_lay.addWidget(self.bg_path_edit, 1)
        choose_bg = QPushButton("Выбрать фон…")
        choose_bg.clicked.connect(self._choose_background)
        bg_lay.addWidget(choose_bg)
        clear_bg = QPushButton("Сбросить")
        clear_bg.clicked.connect(self._clear_background)
        bg_lay.addWidget(clear_bg)
        layout.addWidget(bg_box)

        layout.addStretch(1)

    def _total_ram_mb(self) -> int:
        if psutil is not None:
            try:
                return int(psutil.virtual_memory().total / (1024 * 1024))
            except Exception:
                pass
        return 8192

    def _on_ram_changed(self, value: int) -> None:
        gb = value / 1024
        self.ram_label.setText(f"Выделено: {value} МБ ({gb:.1f} ГБ)")
        self.cfg["ram_mb"] = value
        save_config(self.cfg)

    def _browse_java(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выбери java")
        if path:
            self.java_path_edit.setText(path)
            self._save_settings()

    def _choose_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Фон", filter="Изображения (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self.bg_path_edit.setText(path)
            self.cfg["background"] = path
            save_config(self.cfg)
            self._apply_background()

    def _clear_background(self) -> None:
        self.bg_path_edit.setText("")
        self.cfg["background"] = ""
        save_config(self.cfg)
        self.setPalette(QApplication.palette())
        self.setAutoFillBackground(False)

    def _save_settings(self) -> None:
        self.cfg["java_path"] = self.java_path_edit.text().strip()
        self.cfg["auto_java"] = self.auto_java_chk.isChecked()
        self.cfg["jvm_args"] = self.jvm_args_edit.text()
        self.cfg["extra_optimized"] = self.opt_chk.isChecked()
        self.cfg["res_w"] = self.res_w_spin.value()
        self.cfg["res_h"] = self.res_h_spin.value()
        self.cfg["wrapper_cmd"] = self.wrapper_edit.text().strip()
        gpu_map = {0: "default", 1: "nvidia", 2: "amd", 3: "integrated"}
        self.cfg["gpu"] = gpu_map.get(self.gpu_combo.currentIndex(), "default")
        self.cfg["background"] = self.bg_path_edit.text().strip()
        save_config(self.cfg)

    # ------------------------ mods tab ---------------------------
    def _build_mods_tab(self) -> None:
        layout = QVBoxLayout(self.tab_mods)
        info = QLabel(
            "Сортировщик скачанных файлов: укажи папку Downloads — кнопка "
            "разложит .jar в mods, .zip ресурспаков в resourcepacks, "
            "а файлы шейдеров в shaders."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        row = QHBoxLayout()
        modrinth_btn = QPushButton("🌐 Открыть Modrinth")
        modrinth_btn.clicked.connect(lambda: webbrowser.open("https://modrinth.com"))
        row.addWidget(modrinth_btn)

        sort_btn = QPushButton("📦 Разложить скачанные файлы")
        sort_btn.clicked.connect(self._sort_downloads)
        row.addWidget(sort_btn)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        open_mods = QPushButton("Открыть mods/")
        open_mods.clicked.connect(lambda: self._open_subdir("mods"))
        row2.addWidget(open_mods)
        open_rp = QPushButton("Открыть resourcepacks/")
        open_rp.clicked.connect(lambda: self._open_subdir("resourcepacks"))
        row2.addWidget(open_rp)
        open_sh = QPushButton("Открыть shaders/")
        open_sh.clicked.connect(lambda: self._open_subdir("shaders"))
        row2.addWidget(open_sh)
        layout.addLayout(row2)
        layout.addStretch(1)

    def _open_subdir(self, name: str) -> None:
        target = GAME_DIR / name
        target.mkdir(parents=True, exist_ok=True)
        self._open_path(target)

    def _open_path(self, path: Path) -> None:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _sort_downloads(self) -> None:
        src = QFileDialog.getExistingDirectory(
            self, "Папка с загрузками", str(Path.home() / "Downloads")
        )
        if not src:
            return
        src_path = Path(src)
        moved = 0
        for f in src_path.iterdir():
            if not f.is_file():
                continue
            name = f.name.lower()
            target: Path | None = None
            if name.endswith(".jar"):
                target = GAME_DIR / "mods" / f.name
            elif "shader" in name and (name.endswith(".zip") or name.endswith(".jar")):
                target = GAME_DIR / "shaders" / f.name
            elif name.endswith(".zip") and ("resource" in name or "pack" in name or "rp_" in name):
                target = GAME_DIR / "resourcepacks" / f.name
            elif name.endswith(".zip"):
                target = GAME_DIR / "resourcepacks" / f.name
            if target:
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(f), str(target))
                    moved += 1
                except Exception as exc:
                    self._log(f"Не смог переместить {f}: {exc}")
        QMessageBox.information(self, "Готово", f"Перемещено файлов: {moved}")

    # ------------------------ log tab ----------------------------
    def _build_log_tab(self) -> None:
        layout = QVBoxLayout(self.tab_log)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: Consolas, monospace;")
        layout.addWidget(self.log_view)

    def _log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    # ------------------------ launch -----------------------------
    def _on_play(self) -> None:
        if mll is None:
            QMessageBox.critical(
                self,
                "Нет minecraft-launcher-lib",
                "Установи зависимости: pip install -r requirements.txt",
            )
            return
        version = self.version_combo.currentText().strip()
        if not version:
            QMessageBox.warning(self, "Версия", "Не выбрана версия Minecraft.")
            return
        if not self.cfg.get("current_account"):
            QMessageBox.warning(
                self, "Аккаунт", "Сначала добавь аккаунт во вкладке «Играть» → «Аккаунты…»."
            )
            return

        self.cfg["selected_version"] = version
        save_config(self.cfg)

        self.play_btn.setEnabled(False)
        self.status.setText(f"Подготовка {version}…")
        self.tabs.setCurrentWidget(self.tab_log)

        self.install_thread = InstallThread(version, self.cfg.get("auto_java", True))
        self.install_thread.progress.connect(self._log)
        self.install_thread.failed.connect(self._on_install_failed)
        self.install_thread.finished_ok.connect(lambda v=version: self._launch(v))
        self.install_thread.start()

    def _on_install_failed(self, msg: str) -> None:
        self._log("[ОШИБКА УСТАНОВКИ] " + msg)
        self.status.setText("Ошибка установки.")
        self.play_btn.setEnabled(True)

    def _build_java_path(self) -> str:
        if not self.cfg.get("auto_java", True) and self.cfg.get("java_path"):
            return self.cfg["java_path"]
        if mll is not None:
            try:
                p = mll.runtime.get_executable_path("java-runtime-gamma", str(JAVA_DIR))
                if p:
                    return p
            except Exception:
                pass
        return self.cfg.get("java_path") or "java"

    def _gpu_env(self) -> dict:
        env = os.environ.copy()
        gpu = self.cfg.get("gpu", "default")
        if gpu == "nvidia":
            env["__NV_PRIME_RENDER_OFFLOAD"] = "1"
            env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
            env["__VK_LAYER_NV_optimus"] = "NVIDIA_only"
        elif gpu == "amd":
            env["DRI_PRIME"] = "1"
        elif gpu == "integrated":
            env["DRI_PRIME"] = "0"
            env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
        return env

    def _launch(self, version: str) -> None:
        if mll is None:
            return
        nick = self.cfg.get("current_account") or "Player"
        ram_mb = int(self.cfg.get("ram_mb", 2048))

        jvm_args: list[str] = [f"-Xmx{ram_mb}M", f"-Xms{min(ram_mb, 512)}M"]
        if self.cfg.get("extra_optimized"):
            jvm_args.extend(OPTIMIZED_JVM_ARGS.split())
        extra = (self.cfg.get("jvm_args") or "").strip()
        if extra:
            jvm_args.extend(extra.split())

        options = {
            "username": nick,
            "uuid": str(uuid.uuid3(uuid.NAMESPACE_DNS, nick)),
            "token": "0",
            "jvmArguments": jvm_args,
            "launcherName": APP_NAME,
            "launcherVersion": "1.0",
            "executablePath": self._build_java_path(),
            "customResolution": True,
            "resolutionWidth": str(self.cfg.get("res_w", DEFAULT_RES_W)),
            "resolutionHeight": str(self.cfg.get("res_h", DEFAULT_RES_H)),
            "gameDirectory": str(GAME_DIR),
        }

        try:
            command = mll.command.get_minecraft_command(version, str(GAME_DIR), options)
        except Exception as exc:
            self._log(f"[ОШИБКА КОМАНДЫ] {exc}")
            self.play_btn.setEnabled(True)
            return

        wrapper = (self.cfg.get("wrapper_cmd") or "").strip()
        if wrapper:
            command = wrapper.split() + command

        env = self._gpu_env()
        self.status.setText(f"Запускаю {version}…")
        self.launch_thread = LaunchThread(command, env)
        self.launch_thread.log.connect(self._log)
        self.launch_thread.failed.connect(self._on_launch_failed)
        self.launch_thread.finished_ok.connect(self._on_launch_done)
        self.launch_thread.start()

    def _on_launch_failed(self, msg: str) -> None:
        self._log("[ОШИБКА ЗАПУСКА] " + msg)
        self.status.setText("Ошибка запуска.")
        self.play_btn.setEnabled(True)

    def _on_launch_done(self) -> None:
        self.status.setText("Игра завершена.")
        self.play_btn.setEnabled(True)


def _wrap(layout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    return w


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = XDLauncher()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
