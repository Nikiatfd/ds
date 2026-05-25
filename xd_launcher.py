"""xd launcher — Minecraft launcher, vaguely Prizm-flavored.

Run with:
    pip install -r requirements.txt
    python xd_launcher.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSize, QUrl
from PyQt6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPalette,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from launcher import APP_NAME, APP_VERSION
from launcher.accounts import AccountStore
from launcher.assets import install_asset
from launcher.config import LauncherConfig, DEFAULT_OPTIMIZED_ARGS
from launcher.paths import (
    BACKGROUND_FILE,
    MINECRAFT_DIR,
    MODS_DIR,
    RESOURCEPACKS_DIR,
    SHADERS_DIR,
    ensure_dirs,
)
from launcher import java_manager, minecraft, system_info
from launcher.workers import InstallWorker


MODRINTH_URL = "https://modrinth.com/"


# ---------------------------------------------------------------------------
# Styling (Prizm-ish dark theme)
# ---------------------------------------------------------------------------

QSS = """
* { font-family: "Segoe UI", "Helvetica Neue", "Cantarell", sans-serif; }

QMainWindow, QWidget#root {
    background-color: #1f1f23;
    color: #ececec;
}

QFrame#sidebar {
    background-color: rgba(24, 24, 28, 220);
    border-right: 1px solid #2c2c33;
}

QFrame#contentPane {
    background-color: rgba(34, 34, 40, 200);
}

QLabel#title {
    font-size: 22px;
    font-weight: 700;
    color: #f4f4f8;
    letter-spacing: 1px;
}

QLabel#subtitle {
    font-size: 11px;
    color: #9aa0a6;
}

QListWidget {
    background-color: transparent;
    border: none;
    padding: 4px;
    outline: 0;
}
QListWidget::item {
    padding: 9px 12px;
    margin: 2px 4px;
    border-radius: 8px;
    color: #d9dadf;
}
QListWidget::item:hover { background-color: #2c2c34; }
QListWidget::item:selected {
    background-color: #3a6ea5;
    color: white;
}

QPushButton {
    background-color: #2d2d36;
    border: 1px solid #3a3a44;
    padding: 7px 14px;
    border-radius: 8px;
    color: #ececec;
}
QPushButton:hover { background-color: #393944; }
QPushButton:pressed { background-color: #1f1f25; }
QPushButton:disabled { color: #6b6b73; border-color: #2a2a30; }

QPushButton#playButton {
    background-color: #2ea043;
    border: 1px solid #1f7a32;
    color: white;
    font-size: 15px;
    font-weight: 700;
    padding: 12px;
}
QPushButton#playButton:hover { background-color: #36b34c; }
QPushButton#playButton:disabled { background-color: #2a4a30; color: #aaa; }

QPushButton#modrinthButton {
    background-color: #1bd96a;
    color: #0c2a17;
    border: 1px solid #15a050;
    font-weight: 700;
}
QPushButton#modrinthButton:hover { background-color: #2dee7d; }

QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background-color: #15151a;
    border: 1px solid #2c2c33;
    border-radius: 6px;
    padding: 5px 7px;
    color: #ececec;
    selection-background-color: #3a6ea5;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
    border-color: #4d8fd1;
}

QComboBox::drop-down { border: none; width: 18px; }

QTabWidget::pane {
    border: 1px solid #2c2c33;
    border-radius: 8px;
    background: rgba(28, 28, 34, 200);
    top: -1px;
}
QTabBar::tab {
    background: #25252c;
    border: 1px solid #2c2c33;
    border-bottom: none;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #c5c5cb;
}
QTabBar::tab:selected { background: #3a3a44; color: white; }

QProgressBar {
    background-color: #15151a;
    border: 1px solid #2c2c33;
    border-radius: 6px;
    text-align: center;
    color: #ececec;
}
QProgressBar::chunk { background-color: #3a6ea5; border-radius: 5px; }

QStatusBar { background: #15151a; color: #b6b6bd; }

QSlider::groove:horizontal {
    height: 6px;
    background: #2a2a32;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #3a6ea5;
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
}

QCheckBox { color: #d9dadf; }
"""


# ---------------------------------------------------------------------------
# Account dialog
# ---------------------------------------------------------------------------

class AccountDialog(QDialog):
    def __init__(self, store: AccountStore, selected: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Аккаунты")
        self.resize(420, 360)
        self.store = store
        self.selected_name = selected

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Список аккаунтов (никнеймы):"))

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)
        self._refresh_list()

        row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Введи ник…")
        row.addWidget(self.name_input, 1)

        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add)
        row.addWidget(add_btn)

        del_btn = QPushButton("Удалить")
        del_btn.clicked.connect(self._delete)
        row.addWidget(del_btn)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for acc in self.store.accounts:
            item = QListWidgetItem(f"{acc.name}    ({acc.uuid[:8]}…)")
            item.setData(Qt.ItemDataRole.UserRole, acc.name)
            self.list_widget.addItem(item)
            if acc.name == self.selected_name:
                self.list_widget.setCurrentItem(item)

    def _add(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "xd launcher", "Ник не может быть пустым.")
            return
        try:
            self.store.add(name)
        except ValueError as e:
            QMessageBox.warning(self, "xd launcher", str(e))
            return
        self.name_input.clear()
        self._refresh_list()

    def _delete(self) -> None:
        cur = self.list_widget.currentItem()
        if not cur:
            return
        name = cur.data(Qt.ItemDataRole.UserRole)
        self.store.remove(name)
        self._refresh_list()

    def chosen_name(self) -> str:
        cur = self.list_widget.currentItem()
        if cur:
            return cur.data(Qt.ItemDataRole.UserRole)
        return self.selected_name


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class XDLauncherWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_dirs()
        self.config = LauncherConfig.load()
        self.accounts = AccountStore.load()
        self._install_worker: Optional[InstallWorker] = None

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1020, 640)
        self.setStyleSheet(QSS)

        self._build_ui()
        self._apply_background()
        self._refresh_versions()
        self._refresh_accounts_combo()

    # ----- UI -----
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(14, 14, 14, 14)
        sb.setSpacing(10)

        title = QLabel("xd launcher")
        title.setObjectName("title")
        subtitle = QLabel(f"v{APP_VERSION} • by you ❤")
        subtitle.setObjectName("subtitle")
        sb.addWidget(title)
        sb.addWidget(subtitle)

        sb.addSpacing(6)
        sb.addWidget(QLabel("Версии:"))
        self.version_list = QListWidget()
        self.version_list.itemSelectionChanged.connect(self._on_version_selected)
        sb.addWidget(self.version_list, 1)

        # Reload + folder buttons
        row = QHBoxLayout()
        reload_btn = QPushButton("⟳ Обновить")
        reload_btn.setToolTip("Перезагрузить список версий")
        reload_btn.clicked.connect(self._refresh_versions)
        row.addWidget(reload_btn)

        folder_btn = QPushButton("📁 Папка")
        folder_btn.setToolTip("Открыть папку с игрой")
        folder_btn.clicked.connect(self._open_game_folder)
        row.addWidget(folder_btn)
        sb.addLayout(row)

        # Account row
        acc_row = QHBoxLayout()
        self.account_combo = QComboBox()
        self.account_combo.currentTextChanged.connect(self._on_account_changed)
        acc_row.addWidget(self.account_combo, 1)
        acc_btn = QPushButton("👤")
        acc_btn.setToolTip("Настройки аккаунтов")
        acc_btn.setFixedWidth(36)
        acc_btn.clicked.connect(self._open_accounts)
        acc_row.addWidget(acc_btn)
        sb.addLayout(acc_row)

        # Modrinth button
        modr_btn = QPushButton("🧩 Открыть Modrinth")
        modr_btn.setObjectName("modrinthButton")
        modr_btn.setToolTip("Открыть modrinth.com — после скачивания нажми «Установить файл…»")
        modr_btn.clicked.connect(self._open_modrinth)
        sb.addWidget(modr_btn)

        install_file_btn = QPushButton("➕ Установить мод/пак/шейдер из файла…")
        install_file_btn.clicked.connect(self._install_from_file)
        sb.addWidget(install_file_btn)

        # Play
        self.play_btn = QPushButton("▶  ИГРАТЬ")
        self.play_btn.setObjectName("playButton")
        self.play_btn.clicked.connect(self._on_play)
        sb.addWidget(self.play_btn)

        root_layout.addWidget(sidebar)

        # Right side / content
        content = QFrame()
        content.setObjectName("contentPane")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_game_tab(), "Игра")
        self.tabs.addTab(self._build_java_tab(), "Java")
        self.tabs.addTab(self._build_gpu_tab(), "GPU")
        self.tabs.addTab(self._build_appearance_tab(), "Оформление")
        self.tabs.addTab(self._build_logs_tab(), "Лог")
        cl.addWidget(self.tabs, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        cl.addWidget(self.progress)

        root_layout.addWidget(content, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._set_status(f"Готов. Папка игры: {MINECRAFT_DIR}")

    def _build_game_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        # RAM
        total = system_info.total_ram_mb()
        ram_row = QHBoxLayout()
        self.ram_slider = QSlider(Qt.Orientation.Horizontal)
        self.ram_slider.setRange(512, max(2048, total))
        self.ram_slider.setSingleStep(256)
        self.ram_slider.setPageStep(512)
        self.ram_slider.setValue(min(self.config.ram_mb, max(2048, total)))
        self.ram_label = QLabel()
        self._update_ram_label(self.ram_slider.value())
        self.ram_slider.valueChanged.connect(self._update_ram_label)
        self.ram_slider.valueChanged.connect(self._save_from_inputs)
        ram_row.addWidget(self.ram_slider, 1)
        ram_row.addWidget(self.ram_label)
        ram_wrapper = QWidget()
        ram_wrapper.setLayout(ram_row)
        form.addRow(f"Память (всего {total} MB):", ram_wrapper)

        # Resolution
        res_row = QHBoxLayout()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(320, 7680)
        self.width_spin.setValue(self.config.width)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(240, 4320)
        self.height_spin.setValue(self.config.height)
        self.width_spin.valueChanged.connect(self._save_from_inputs)
        self.height_spin.valueChanged.connect(self._save_from_inputs)
        res_row.addWidget(self.width_spin)
        res_row.addWidget(QLabel(" × "))
        res_row.addWidget(self.height_spin)
        res_row.addStretch(1)
        res_wrap = QWidget()
        res_wrap.setLayout(res_row)
        form.addRow("Разрешение игры:", res_wrap)

        # JVM arguments
        self.jvm_input = QLineEdit(self.config.extra_jvm_args)
        self.jvm_input.setPlaceholderText("например: -Dfile.encoding=UTF-8")
        self.jvm_input.editingFinished.connect(self._save_from_inputs)
        form.addRow("Аргументы Java:", self.jvm_input)

        # Optimized
        opt_row = QHBoxLayout()
        self.opt_check = QCheckBox("Использовать оптимизированные аргументы")
        self.opt_check.setChecked(self.config.use_optimized)
        self.opt_check.toggled.connect(self._save_from_inputs)
        opt_row.addWidget(self.opt_check)
        reset_opt = QPushButton("Сброс к стандартным")
        reset_opt.clicked.connect(self._reset_optimized)
        opt_row.addWidget(reset_opt)
        opt_wrap = QWidget()
        opt_wrap.setLayout(opt_row)
        form.addRow("Оптимизация:", opt_wrap)

        self.opt_input = QTextEdit()
        self.opt_input.setPlainText(self.config.optimized_args)
        self.opt_input.setFixedHeight(80)
        self.opt_input.textChanged.connect(self._save_from_inputs)
        form.addRow("Оптимизированные аргументы:", self.opt_input)

        # Wrapper command
        self.wrap_input = QLineEdit(self.config.wrapper_command)
        self.wrap_input.setPlaceholderText("например: prime-run  или  gamemoderun")
        self.wrap_input.editingFinished.connect(self._save_from_inputs)
        form.addRow("Команда-обёртка:", self.wrap_input)

        return w

    def _build_java_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.bundled_check = QCheckBox(
            "Скачивать Java автоматически (рекомендуется)"
        )
        self.bundled_check.setChecked(self.config.use_bundled_java)
        self.bundled_check.toggled.connect(self._on_bundled_toggled)
        form.addRow("", self.bundled_check)

        row = QHBoxLayout()
        self.java_input = QLineEdit(self.config.java_path)
        self.java_input.setPlaceholderText("путь к java/java.exe")
        self.java_input.editingFinished.connect(self._save_from_inputs)
        browse_btn = QPushButton("Обзор…")
        browse_btn.clicked.connect(self._browse_java)
        row.addWidget(self.java_input, 1)
        row.addWidget(browse_btn)
        wrap = QWidget()
        wrap.setLayout(row)
        form.addRow("Своя Java:", wrap)
        self.java_input.setEnabled(not self.bundled_check.isChecked())

        info = QLabel(
            "<small style='color:#9aa0a6;'>"
            "Лаунчер автоматически подберёт Java 8 для 1.12.2/1.16.5 "
            "и Java 17 для 1.20.1, если включена авто-загрузка. "
            "Бинарники качаются с Adoptium."
            "</small>"
        )
        info.setWordWrap(True)
        form.addRow("", info)
        return w

    def _build_gpu_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel("Найденные видеокарты:"))
        self.gpu_list = QListWidget()
        for gpu in system_info.list_gpus():
            tag = {"discrete": "дискретная", "integrated": "встроенная"}.get(
                gpu.kind, "неизвестно"
            )
            self.gpu_list.addItem(f"{gpu.name}   [{tag}]")
        self.gpu_list.setFixedHeight(110)
        layout.addWidget(self.gpu_list)

        layout.addWidget(QLabel("Запускать игру на:"))
        self.gpu_combo = QComboBox()
        self.gpu_combo.addItem("Автоматически", "auto")
        self.gpu_combo.addItem("Дискретная (производительность)", "discrete")
        self.gpu_combo.addItem("Встроенная (энергосбережение)", "integrated")
        for i in range(self.gpu_combo.count()):
            if self.gpu_combo.itemData(i) == self.config.gpu_mode:
                self.gpu_combo.setCurrentIndex(i)
                break
        self.gpu_combo.currentIndexChanged.connect(self._save_from_inputs)
        layout.addWidget(self.gpu_combo)

        layout.addWidget(QLabel(
            "<small style='color:#9aa0a6;'>На Linux это задаёт переменные "
            "<b>__NV_PRIME_RENDER_OFFLOAD</b> / <b>DRI_PRIME</b> и при наличии "
            "<b>prime-run</b> подставляет его как обёртку. На Windows — "
            "подсказку драйверу через <b>SHIM_MCCOMPAT</b>.</small>"
        ))
        layout.addStretch(1)
        return w

    def _build_appearance_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Фон лаунчера:"))
        row = QHBoxLayout()
        self.bg_input = QLineEdit(self.config.background_path)
        self.bg_input.setPlaceholderText("путь к картинке (jpg/png)")
        self.bg_input.editingFinished.connect(self._on_bg_changed)
        browse = QPushButton("Выбрать…")
        browse.clicked.connect(self._browse_background)
        clear = QPushButton("Сброс")
        clear.clicked.connect(self._clear_background)
        row.addWidget(self.bg_input, 1)
        row.addWidget(browse)
        row.addWidget(clear)
        layout.addLayout(row)

        self.bg_preview = QLabel()
        self.bg_preview.setFixedHeight(220)
        self.bg_preview.setStyleSheet("border: 1px solid #2c2c33; border-radius: 8px;")
        self.bg_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.bg_preview)
        layout.addStretch(1)
        return w

    def _build_logs_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            "QTextEdit{background:#0d0d12;color:#c5c5cb;font-family:Consolas,monospace;}"
        )
        layout.addWidget(self.log_view, 1)
        clear = QPushButton("Очистить лог")
        clear.clicked.connect(lambda: self.log_view.clear())
        layout.addWidget(clear)
        return w

    # ----- helpers -----
    def _set_status(self, text: str) -> None:
        self.status.showMessage(text, 7000)

    def _log(self, text: str) -> None:
        self.log_view.append(text)

    def _update_ram_label(self, value: int) -> None:
        self.ram_label.setText(f"{value} MB")

    def _refresh_versions(self) -> None:
        self.version_list.clear()
        for v in minecraft.list_available_versions():
            installed = v in minecraft.list_installed_versions()
            label = f"  {v}" + ("  ✓" if installed else "  (скачать)")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, v)
            self.version_list.addItem(item)
            if v == self.config.selected_version:
                self.version_list.setCurrentItem(item)
        if not self.version_list.currentItem() and self.version_list.count():
            self.version_list.setCurrentRow(0)
        self._set_status("Список версий обновлён.")

    def _on_version_selected(self) -> None:
        cur = self.version_list.currentItem()
        if cur:
            self.config.selected_version = cur.data(Qt.ItemDataRole.UserRole)
            self.config.save()

    def _refresh_accounts_combo(self) -> None:
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        if not self.accounts.accounts:
            self.account_combo.addItem("(нет аккаунтов — добавь →)", "")
        else:
            for a in self.accounts.accounts:
                self.account_combo.addItem(a.name, a.name)
            for i in range(self.account_combo.count()):
                if self.account_combo.itemData(i) == self.config.selected_account:
                    self.account_combo.setCurrentIndex(i)
                    break
            else:
                self.account_combo.setCurrentIndex(0)
                self.config.selected_account = self.account_combo.itemData(0) or ""
        self.account_combo.blockSignals(False)

    def _on_account_changed(self, *_args) -> None:
        self.config.selected_account = self.account_combo.currentData() or ""
        self.config.save()

    def _open_accounts(self) -> None:
        dlg = AccountDialog(self.accounts, self.config.selected_account, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            chosen = dlg.chosen_name()
            if chosen:
                self.config.selected_account = chosen
            self.config.save()
        self._refresh_accounts_combo()

    def _open_game_folder(self) -> None:
        ensure_dirs()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(MINECRAFT_DIR)))

    def _open_modrinth(self) -> None:
        QDesktopServices.openUrl(QUrl(MODRINTH_URL))
        self._set_status(
            "Открыт Modrinth. После скачивания нажми «Установить файл…» "
            "— лаунчер сам разложит мод/пак/шейдер в нужную папку."
        )

    def _install_from_file(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выбери файлы (моды .jar, ресурс-паки/шейдеры .zip)",
            self.config.last_modrinth_dir or str(Path.home()),
            "Моды и паки (*.jar *.zip);;Все файлы (*)",
        )
        if not files:
            return
        self.config.last_modrinth_dir = str(Path(files[0]).parent)
        self.config.save()

        summary = []
        for f in files:
            kind, dest = install_asset(Path(f))
            if not dest:
                summary.append(f"⚠ {Path(f).name}: не удалось определить тип")
                continue
            label = {
                "mod": "mods",
                "resourcepack": "resourcepacks",
                "shader": "shaderpacks",
            }.get(kind, "—")
            summary.append(f"✓ {Path(f).name} → {label}/")
        QMessageBox.information(
            self, "Установка", "\n".join(summary) or "Ничего не установлено."
        )
        self._set_status("Файлы установлены.")

    def _reset_optimized(self) -> None:
        self.opt_input.setPlainText(DEFAULT_OPTIMIZED_ARGS)

    def _on_bundled_toggled(self, checked: bool) -> None:
        self.config.use_bundled_java = checked
        self.java_input.setEnabled(not checked)
        self.config.save()

    def _browse_java(self) -> None:
        filter_ = "Java (java.exe)" if sys.platform.startswith("win") else "Java (java)"
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери исполняемый файл Java", str(Path.home()), filter_
        )
        if path:
            self.java_input.setText(path)
            self._save_from_inputs()

    def _browse_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбери фон",
            str(Path.home()),
            "Картинки (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return
        try:
            shutil.copy2(path, BACKGROUND_FILE)
            self.config.background_path = str(BACKGROUND_FILE)
            self.bg_input.setText(self.config.background_path)
            self.config.save()
            self._apply_background()
        except Exception as e:
            QMessageBox.warning(self, "xd launcher", f"Не удалось задать фон: {e}")

    def _clear_background(self) -> None:
        self.config.background_path = ""
        self.bg_input.setText("")
        self.config.save()
        self._apply_background()

    def _on_bg_changed(self) -> None:
        self.config.background_path = self.bg_input.text().strip()
        self.config.save()
        self._apply_background()

    def _apply_background(self) -> None:
        path = self.config.background_path
        if path and Path(path).exists():
            self.bg_preview.setPixmap(
                QPixmap(path).scaled(
                    self.bg_preview.width() or 400,
                    self.bg_preview.height() or 200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            url_path = path.replace(chr(92), "/")
            css = (
                f"QWidget#root {{ "
                f"background-image: url(\"{url_path}\"); "
                f"background-position: center; background-repeat: no-repeat; "
                f"background-attachment: fixed; }}"
            )
            self.setStyleSheet(QSS + "\n" + css)
        else:
            self.bg_preview.clear()
            self.bg_preview.setText("Фон не задан")
            self.setStyleSheet(QSS)

    def _save_from_inputs(self) -> None:
        self.config.ram_mb = int(self.ram_slider.value())
        self.config.width = int(self.width_spin.value())
        self.config.height = int(self.height_spin.value())
        self.config.extra_jvm_args = self.jvm_input.text()
        self.config.optimized_args = self.opt_input.toPlainText().strip() \
            or DEFAULT_OPTIMIZED_ARGS
        self.config.use_optimized = self.opt_check.isChecked()
        self.config.wrapper_command = self.wrap_input.text().strip()
        self.config.java_path = self.java_input.text().strip()
        self.config.gpu_mode = self.gpu_combo.currentData() or "auto"
        self.config.save()

    # ----- launch -----
    def _on_play(self) -> None:
        self._save_from_inputs()
        version = self.config.selected_version
        if not version:
            QMessageBox.warning(self, "xd launcher", "Выбери версию.")
            return
        if not self.accounts.accounts:
            QMessageBox.warning(self, "xd launcher",
                                "Сначала добавь аккаунт (кнопка 👤).")
            return
        acc = self.accounts.get(self.config.selected_account)
        if acc is None:
            acc = self.accounts.accounts[0]
            self.config.selected_account = acc.name
            self.config.save()

        # If the version is already installed, skip the installer and just launch.
        if version in minecraft.list_installed_versions():
            self._launch_now(version, acc)
            return

        # Otherwise: install then launch.
        self._start_install(version, then_launch_account=acc)

    def _start_install(self, version: str, then_launch_account=None) -> None:
        self.play_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate until we know
        self._log(f"--- Установка {version} ---")

        worker = InstallWorker(
            version,
            self.config.use_bundled_java,
            self.config.java_path,
        )
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(lambda: self._on_install_done(version, then_launch_account))
        worker.finished_err.connect(self._on_install_err)
        worker.finished.connect(worker.deleteLater)
        self._install_worker = worker
        worker.start()

    def _on_progress(self, value: int, total: int, msg: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(value)
        else:
            self.progress.setRange(0, 0)
        if msg:
            self._set_status(msg)
            self._log(msg)

    def _on_install_done(self, version: str, account) -> None:
        self.progress.setVisible(False)
        self.play_btn.setEnabled(True)
        self._refresh_versions()
        if account is not None:
            self._launch_now(version, account)

    def _on_install_err(self, err: str) -> None:
        self.progress.setVisible(False)
        self.play_btn.setEnabled(True)
        self._log(f"ОШИБКА: {err}")
        QMessageBox.critical(self, "xd launcher", f"Не удалось установить:\n{err}")

    def _launch_now(self, version: str, account) -> None:
        try:
            java = java_manager.resolve_java_for(
                version,
                self.config.use_bundled_java,
                self.config.java_path,
            )
            cmd = minecraft.build_launch_command(
                version_id=version,
                username=account.name,
                uuid=account.uuid,
                token=account.token,
                java_path=java,
                ram_mb=int(self.config.ram_mb),
                width=int(self.config.width),
                height=int(self.config.height),
                extra_jvm=self.config.extra_jvm_args,
                optimized_jvm=self.config.optimized_args,
                use_optimized=self.config.use_optimized,
            )
            wrapper = self.config.wrapper_command
            gpu_env = system_info.gpu_launch_env(self.config.gpu_mode)
            gpu_wrap = system_info.gpu_wrapper_command(self.config.gpu_mode)
            if not wrapper and gpu_wrap:
                wrapper = gpu_wrap

            self._log(f"$ {' '.join(cmd[:4])} … ({len(cmd)} args)")
            self._set_status(
                f"Запускаю {version} как {account.name} ({self.config.width}×{self.config.height})"
            )
            minecraft.launch(cmd, wrapper=wrapper, env_overrides=gpu_env)
        except Exception as e:
            self._log(f"ОШИБКА запуска: {e}")
            QMessageBox.critical(self, "xd launcher", f"Не удалось запустить:\n{e}")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    win = XDLauncherWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
