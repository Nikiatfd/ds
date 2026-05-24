"""iOS 26 "Liquid Glass" styled media player running its UI loop at 120 FPS.

Run:
    pip install PyQt6
    python media_player.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

TARGET_FPS = 120
FRAME_MS = max(1, int(round(1000 / TARGET_FPS)))

ACCENT = QColor(120, 170, 255)
ACCENT_SOFT = QColor(180, 140, 255)
GLASS_TINT = QColor(255, 255, 255, 18)
GLASS_BORDER = QColor(255, 255, 255, 60)
TEXT_PRIMARY = QColor(245, 245, 250)
TEXT_SECONDARY = QColor(200, 205, 220, 200)


def format_time(ms: int) -> str:
    if ms < 0:
        ms = 0
    s = ms // 1000
    return f"{s // 60:d}:{s % 60:02d}"


class AnimatedBackdrop(QWidget):
    """Liquid Glass backdrop: drifting color blobs behind a frosted glass pane."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(FRAME_MS)

    def _tick(self) -> None:
        self._t += 1.0 / TARGET_FPS
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect()

        base = QLinearGradient(0, 0, 0, r.height())
        base.setColorAt(0.0, QColor(14, 14, 22))
        base.setColorAt(1.0, QColor(6, 6, 12))
        p.fillRect(r, base)

        t = self._t
        blobs = [
            (0.30 + 0.18 * math.sin(t * 0.35),
             0.35 + 0.20 * math.cos(t * 0.27),
             QColor(120, 170, 255, 180)),
            (0.70 + 0.15 * math.cos(t * 0.41),
             0.60 + 0.22 * math.sin(t * 0.33),
             QColor(200, 110, 220, 170)),
            (0.50 + 0.25 * math.sin(t * 0.23 + 1.2),
             0.80 + 0.10 * math.cos(t * 0.47),
             QColor(80, 220, 200, 150)),
            (0.20 + 0.12 * math.cos(t * 0.51),
             0.85 + 0.08 * math.sin(t * 0.39),
             QColor(255, 150, 120, 140)),
        ]
        radius = max(r.width(), r.height()) * 0.55
        for fx, fy, color in blobs:
            cx, cy = r.width() * fx, r.height() * fy
            grad = QRadialGradient(QPointF(cx, cy), radius)
            grad.setColorAt(0.0, color)
            faded = QColor(color)
            faded.setAlpha(0)
            grad.setColorAt(1.0, faded)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), radius, radius)


class GlassCard(QWidget):
    """Frosted-glass container with rounded corners and subtle inner highlight."""

    def __init__(self, radius: int = 28, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        fill = QLinearGradient(0, 0, 0, rect.height())
        fill.setColorAt(0.0, QColor(255, 255, 255, 38))
        fill.setColorAt(1.0, QColor(255, 255, 255, 12))
        p.fillPath(path, fill)

        highlight = QLinearGradient(0, 0, 0, rect.height() * 0.5)
        highlight.setColorAt(0.0, QColor(255, 255, 255, 70))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(highlight))
        inner = QPainterPath()
        inner.addRoundedRect(rect.adjusted(1, 1, -1, -rect.height() * 0.5),
                             self._radius - 1, self._radius - 1)
        p.drawPath(inner)

        pen = QPen(GLASS_BORDER, 1.2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


class GlassButton(QPushButton):
    """Round glass button with a glyph and a tactile press animation."""

    def __init__(self, glyph: str, size: int = 56, accent: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glyph = glyph
        self._accent = accent
        self._scale = 1.0
        self._hover = 0.0
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._press = QPropertyAnimation(self, b"scale", self)
        self._press.setDuration(140)
        self._press.setEasingCurve(QEasingCurve.Type.OutCubic)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 140))
        self.setGraphicsEffect(shadow)

    def get_scale(self) -> float:
        return self._scale

    def set_scale(self, v: float) -> None:
        self._scale = v
        self.update()

    scale = pyqtProperty(float, fget=get_scale, fset=set_scale)

    def enterEvent(self, e) -> None:  # noqa: N802
        self._hover = 1.0
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._hover = 0.0
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self._press.stop()
        self._press.setStartValue(self._scale)
        self._press.setEndValue(0.92)
        self._press.start()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._press.stop()
        self._press.setStartValue(self._scale)
        self._press.setEndValue(1.0)
        self._press.start()
        super().mouseReleaseEvent(e)

    def set_glyph(self, glyph: str) -> None:
        self._glyph = glyph
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        cx, cy = rect.center().x(), rect.center().y()
        p.translate(cx, cy)
        p.scale(self._scale, self._scale)
        p.translate(-cx, -cy)

        inset = 2
        circle = rect.adjusted(inset, inset, -inset, -inset)

        if self._accent:
            grad = QLinearGradient(circle.topLeft(), circle.bottomRight())
            grad.setColorAt(0.0, ACCENT)
            grad.setColorAt(1.0, ACCENT_SOFT)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(circle)
            sheen = QLinearGradient(circle.topLeft(),
                                    QPointF(circle.center().x(), circle.center().y()))
            sheen.setColorAt(0.0, QColor(255, 255, 255, 130))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(sheen))
            p.drawEllipse(circle.adjusted(2, 2, -2, -circle.height() * 0.45))
        else:
            grad = QLinearGradient(circle.topLeft(), circle.bottomRight())
            base_top = 70 + int(40 * self._hover)
            base_bot = 18 + int(20 * self._hover)
            grad.setColorAt(0.0, QColor(255, 255, 255, base_top))
            grad.setColorAt(1.0, QColor(255, 255, 255, base_bot))
            p.setBrush(QBrush(grad))
            p.setPen(QPen(GLASS_BORDER, 1.0))
            p.drawEllipse(circle)

        p.setPen(QPen(QColor(255, 255, 255, 250), 0))
        font = QFont(self.font())
        font.setPixelSize(int(circle.height() * 0.42))
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.drawText(circle, Qt.AlignmentFlag.AlignCenter, self._glyph)


class LiquidSlider(QWidget):
    """Custom slider with a glass groove, a glowing fill, and a floating knob."""

    valueChanged = pyqtSignal(float)
    sliderReleased = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._displayed = 0.0
        self._dragging = False
        self._hover = False
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._animate)
        self._timer.start(FRAME_MS)

    def _animate(self) -> None:
        diff = self._value - self._displayed
        if abs(diff) > 0.0005:
            self._displayed += diff * 0.22
            self.update()

    def setValue(self, v: float, *, animate: bool = True) -> None:  # noqa: N802
        v = max(0.0, min(1.0, v))
        self._value = v
        if not animate:
            self._displayed = v
        self.update()

    def value(self) -> float:
        return self._value

    def _value_from_x(self, x: float) -> float:
        groove = self._groove_rect()
        if groove.width() <= 0:
            return 0.0
        return max(0.0, min(1.0, (x - groove.left()) / groove.width()))

    def _groove_rect(self) -> QRectF:
        margin = 12
        h = 6
        return QRectF(margin, (self.height() - h) / 2,
                      self.width() - margin * 2, h)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._value = self._value_from_x(e.position().x())
            self._displayed = self._value
            self.valueChanged.emit(self._value)
            self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        self._hover = True
        if self._dragging:
            self._value = self._value_from_x(e.position().x())
            self._displayed = self._value
            self.valueChanged.emit(self._value)
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.sliderReleased.emit()
            self.update()

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        groove = self._groove_rect()

        path = QPainterPath()
        path.addRoundedRect(groove, groove.height() / 2, groove.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 32))
        p.drawPath(path)

        fill_w = groove.width() * self._displayed
        fill = QRectF(groove.left(), groove.top(), fill_w, groove.height())
        grad = QLinearGradient(fill.topLeft(), fill.topRight())
        grad.setColorAt(0.0, ACCENT)
        grad.setColorAt(1.0, ACCENT_SOFT)
        fpath = QPainterPath()
        fpath.addRoundedRect(fill, fill.height() / 2, fill.height() / 2)
        p.setBrush(QBrush(grad))
        p.drawPath(fpath)

        knob_r = 11 if (self._dragging or self._hover) else 8
        knob_cx = groove.left() + fill_w
        knob_cy = groove.center().y()

        glow = QRadialGradient(QPointF(knob_cx, knob_cy), knob_r * 2.4)
        glow.setColorAt(0.0, QColor(150, 190, 255, 160))
        glow.setColorAt(1.0, QColor(150, 190, 255, 0))
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(knob_cx, knob_cy), knob_r * 2.2, knob_r * 2.2)

        kgrad = QLinearGradient(knob_cx, knob_cy - knob_r, knob_cx, knob_cy + knob_r)
        kgrad.setColorAt(0.0, QColor(255, 255, 255, 255))
        kgrad.setColorAt(1.0, QColor(220, 230, 250, 255))
        p.setBrush(QBrush(kgrad))
        p.setPen(QPen(QColor(255, 255, 255, 160), 1))
        p.drawEllipse(QPointF(knob_cx, knob_cy), knob_r, knob_r)


class VisualizerBar(QWidget):
    """Faux audio visualizer that animates smoothly at 120 FPS."""

    def __init__(self, bars: int = 36, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bars = bars
        self._levels = [0.2] * bars
        self._targets = [0.2] * bars
        self._t = 0.0
        self._playing = False
        self.setMinimumHeight(72)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(FRAME_MS)

    def set_playing(self, playing: bool) -> None:
        self._playing = playing

    def _tick(self) -> None:
        self._t += 1.0 / TARGET_FPS
        for i in range(self._bars):
            if self._playing:
                base = 0.45 + 0.35 * math.sin(self._t * 2.1 + i * 0.4)
                ripple = 0.25 * math.sin(self._t * 5.3 + i * 0.9)
                self._targets[i] = max(0.05, min(1.0, base + ripple))
            else:
                self._targets[i] = 0.12 + 0.04 * math.sin(self._t * 0.6 + i * 0.3)
            self._levels[i] += (self._targets[i] - self._levels[i]) * 0.18
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        gap = 4
        total_gap = gap * (self._bars - 1)
        bw = max(2.0, (w - total_gap) / self._bars)
        for i, lv in enumerate(self._levels):
            bh = max(3.0, lv * (h - 6))
            x = i * (bw + gap)
            y = (h - bh) / 2
            rect = QRectF(x, y, bw, bh)
            grad = QLinearGradient(0, y, 0, y + bh)
            grad.setColorAt(0.0, ACCENT)
            grad.setColorAt(1.0, ACCENT_SOFT)
            path = QPainterPath()
            path.addRoundedRect(rect, bw / 2, bw / 2)
            p.fillPath(path, QBrush(grad))


class MediaPlayer(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Liquid Player")
        self.resize(560, 760)
        self.setMinimumSize(QSize(420, 640))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(0.7)

        self._duration_ms = 0
        self._scrubbing = False
        self._playlist: list[Path] = []
        self._index = -1

        self._build_ui()
        self._wire_player()

    def _build_ui(self) -> None:
        self._backdrop = AnimatedBackdrop(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(18)

        # Header
        header = QHBoxLayout()
        title = QLabel("Now Playing")
        title.setStyleSheet(
            f"color: rgba(245,245,250,230); font-size: 13px; letter-spacing: 1.5px;"
        )
        header.addWidget(title)
        header.addStretch(1)
        self._open_btn = GlassButton("➕", size=36)
        self._open_btn.clicked.connect(self._open_files)
        header.addWidget(self._open_btn)
        root.addLayout(header)

        # Artwork card
        self._art_card = GlassCard(radius=32)
        art_layout = QVBoxLayout(self._art_card)
        art_layout.setContentsMargins(22, 22, 22, 22)
        art_layout.setSpacing(10)

        self._visualizer = VisualizerBar(bars=32)
        art_layout.addWidget(self._visualizer, 1)

        self._track_label = QLabel("No track loaded")
        f = QFont()
        f.setPixelSize(22)
        f.setWeight(QFont.Weight.DemiBold)
        self._track_label.setFont(f)
        self._track_label.setStyleSheet("color: rgba(245,245,250,245);")
        self._track_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art_layout.addWidget(self._track_label)

        self._subtitle = QLabel("Open a file to begin")
        sf = QFont()
        sf.setPixelSize(13)
        self._subtitle.setFont(sf)
        self._subtitle.setStyleSheet("color: rgba(200,205,220,200);")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art_layout.addWidget(self._subtitle)
        root.addWidget(self._art_card, 1)

        # Progress card
        progress_card = GlassCard(radius=24)
        pl = QVBoxLayout(progress_card)
        pl.setContentsMargins(20, 16, 20, 16)
        pl.setSpacing(6)
        self._progress = LiquidSlider()
        self._progress.valueChanged.connect(self._on_progress_drag)
        self._progress.sliderReleased.connect(self._on_progress_release)
        pl.addWidget(self._progress)

        time_row = QHBoxLayout()
        self._time_now = QLabel("0:00")
        self._time_total = QLabel("0:00")
        for lbl in (self._time_now, self._time_total):
            lbl.setStyleSheet("color: rgba(200,205,220,200); font-size: 12px;")
        time_row.addWidget(self._time_now)
        time_row.addStretch(1)
        time_row.addWidget(self._time_total)
        pl.addLayout(time_row)
        root.addWidget(progress_card)

        # Transport
        transport = QHBoxLayout()
        transport.setSpacing(18)
        transport.addStretch(1)
        self._prev_btn = GlassButton("⏮", size=52)
        self._play_btn = GlassButton("▶", size=72, accent=True)
        self._next_btn = GlassButton("⏭", size=52)
        self._prev_btn.clicked.connect(self._prev)
        self._next_btn.clicked.connect(self._next)
        self._play_btn.clicked.connect(self._toggle_play)
        transport.addWidget(self._prev_btn)
        transport.addWidget(self._play_btn)
        transport.addWidget(self._next_btn)
        transport.addStretch(1)
        root.addLayout(transport)

        # Volume card
        vol_card = GlassCard(radius=22)
        vl = QHBoxLayout(vol_card)
        vl.setContentsMargins(18, 12, 18, 12)
        vl.setSpacing(12)
        vmin = QLabel("\U0001F509")
        vmax = QLabel("\U0001F50A")
        for lbl in (vmin, vmax):
            lbl.setStyleSheet("color: rgba(245,245,250,220); font-size: 14px;")
        self._volume = LiquidSlider()
        self._volume.setValue(0.7, animate=False)
        self._volume.valueChanged.connect(self._on_volume)
        vl.addWidget(vmin)
        vl.addWidget(self._volume, 1)
        vl.addWidget(vmax)
        root.addWidget(vol_card)

    def resizeEvent(self, e) -> None:  # noqa: N802
        self._backdrop.setGeometry(self.rect())
        self._backdrop.lower()
        super().resizeEvent(e)

    def _wire_player(self) -> None:
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)

    # ---- Playlist / playback ---------------------------------------------
    def _open_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Open audio",
            str(Path.home()),
            "Audio (*.mp3 *.wav *.flac *.ogg *.m4a *.aac);;All files (*)",
        )
        if not files:
            return
        self._playlist = [Path(f) for f in files]
        self._index = 0
        self._load_current()
        self._player.play()

    def _load_current(self) -> None:
        if not (0 <= self._index < len(self._playlist)):
            return
        path = self._playlist[self._index]
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._track_label.setText(path.stem)
        self._subtitle.setText(
            f"{self._index + 1} of {len(self._playlist)}  ·  {path.suffix.upper().lstrip('.')}"
        )

    def _toggle_play(self) -> None:
        if not self._playlist:
            self._open_files()
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _prev(self) -> None:
        if not self._playlist:
            return
        self._index = (self._index - 1) % len(self._playlist)
        self._load_current()
        self._player.play()

    def _next(self) -> None:
        if not self._playlist:
            return
        self._index = (self._index + 1) % len(self._playlist)
        self._load_current()
        self._player.play()

    # ---- Slots ------------------------------------------------------------
    def _on_position(self, pos: int) -> None:
        if self._duration_ms > 0 and not self._scrubbing:
            self._progress.setValue(pos / self._duration_ms)
        self._time_now.setText(format_time(pos))

    def _on_duration(self, dur: int) -> None:
        self._duration_ms = dur
        self._time_total.setText(format_time(dur))

    def _on_state(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_btn.set_glyph("⏸" if playing else "▶")
        self._visualizer.set_playing(playing)

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._next()

    def _on_progress_drag(self, v: float) -> None:
        self._scrubbing = True
        self._time_now.setText(format_time(int(v * self._duration_ms)))

    def _on_progress_release(self) -> None:
        if self._duration_ms > 0:
            self._player.setPosition(int(self._progress.value() * self._duration_ms))
        self._scrubbing = False

    def _on_volume(self, v: float) -> None:
        self._audio.setVolume(v)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MediaPlayer()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
