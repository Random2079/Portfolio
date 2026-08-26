"""
IDEA-022 — прозрачный overlay: каталог музыки / mp4 поверх окон.

Always-on-top: список → play (видео или анимированный визуал для mp3),
громкость, opacity. Click-through только хоткеем Ctrl+Shift+O
(галка не нужна — под прозрачным окном её всё равно не снять).
"""
from __future__ import annotations

import ctypes
import math
import os
import random
import sys
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget

    _HAS_MULTIMEDIA = True
except ImportError:  # pragma: no cover
    QAudioOutput = None  # type: ignore[misc, assignment]
    QMediaPlayer = None  # type: ignore[misc, assignment]
    QVideoWidget = None  # type: ignore[misc, assignment]
    _HAS_MULTIMEDIA = False

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".wma"}
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".m4v"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_O = 0x4F
_HOTKEY_ID = 0x0220


def default_music_dirs() -> list[str]:
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "Music", "YouTube_DL"),
        os.path.join(home, "Music"),
    ]
    out: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        ap = os.path.abspath(path)
        if ap in seen:
            continue
        seen.add(ap)
        if os.path.isdir(ap):
            out.append(ap)
    return out


def scan_media(folder: str) -> list[Path]:
    root = Path(folder)
    if not root.is_dir():
        return []
    files: list[Path] = []
    try:
        for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if entry.is_file() and entry.suffix.lower() in MEDIA_EXTS:
                files.append(entry)
    except OSError:
        return []
    return files


def resolve_play_path(path: Path) -> Path:
    """mp3 + соседний mp4 с тем же именем → играем mp4."""
    if path.suffix.lower() in VIDEO_EXTS:
        return path
    sibling = path.with_suffix(".mp4")
    if sibling.is_file():
        return sibling
    for ext in (".webm", ".mkv", ".mov", ".m4v"):
        alt = path.with_suffix(ext)
        if alt.is_file():
            return alt
    return path


class PulseVisual(QWidget):
    """Анимированные «эквалайзер»-полосы — для audio-only (без mp4)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self._n_bars = 36
        self._levels = [0.25] * self._n_bars
        self._targets = [0.4] * self._n_bars
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self.setMinimumSize(240, 180)
        self.setStyleSheet("background: #070b14;")

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._levels = [0.12] * self._n_bars
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.07) % 6.28318
        for i in range(self._n_bars):
            # Цели «пляшут», уровни догоняют — выглядит живее одной ноты ♫
            wave = 0.35 + 0.55 * abs(math.sin(self._phase * 1.3 + i * 0.33))
            noise = random.uniform(-0.12, 0.18)
            self._targets[i] = max(0.08, min(1.0, wave + noise))
            self._levels[i] += (self._targets[i] - self._levels[i]) * 0.28
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor("#0c1220"))
        bg.setColorAt(0.55, QColor("#0a1628"))
        bg.setColorAt(1.0, QColor("#05080f"))
        painter.fillRect(0, 0, w, h, bg)

        # мягкое свечение сверху
        glow = QLinearGradient(0, 0, w, 0)
        glow.setColorAt(0.0, QColor(56, 189, 248, 0))
        glow.setColorAt(0.5, QColor(99, 102, 241, 35))
        glow.setColorAt(1.0, QColor(56, 189, 248, 0))
        painter.fillRect(0, 0, w, int(h * 0.35), glow)

        margin_x = 28
        margin_bottom = 28
        top = int(h * 0.18)
        usable_w = max(1, w - 2 * margin_x)
        usable_h = max(1, h - top - margin_bottom)
        gap = 3
        bar_w = max(3, (usable_w - gap * (self._n_bars - 1)) / self._n_bars)

        for i, level in enumerate(self._levels):
            bh = usable_h * level
            x = margin_x + i * (bar_w + gap)
            y = top + usable_h - bh
            grad = QLinearGradient(x, y + bh, x, y)
            grad.setColorAt(0.0, QColor(14, 165, 233, 220))
            grad.setColorAt(0.55, QColor(99, 102, 241, 230))
            grad.setColorAt(1.0, QColor(244, 114, 182, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bh), 3, 3)

        painter.setPen(QPen(QColor(148, 163, 184, 140), 1))
        painter.drawText(
            self.rect().adjusted(0, 8, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "audio · без mp4 — визуал",
        )


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        et = bytes(eventType) if isinstance(eventType, (bytes, bytearray)) else str(eventType).encode()
        if et not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False
        try:
            addr = int(message)
            msg = ctypes.wintypes.MSG.from_address(addr)
        except (TypeError, ValueError, OverflowError):
            return False
        if msg.message == WM_HOTKEY and int(msg.wParam) == _HOTKEY_ID:
            self._callback()
            return True
        return False


class OverlayPlayerWindow(QWidget):
    """Окно фона: каталог → play + volume + opacity; click-through = хоткей."""

    closed = Signal()

    def __init__(self, start_dir: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Фон — overlay (IDEA-022)")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(900, 540)

        self._folder = start_dir or (default_music_dirs()[0] if default_music_dirs() else os.path.expanduser("~"))
        self._click_through = False
        self._hotkey_filter: _HotkeyFilter | None = None
        self._hotkey_registered = False
        self._base_exstyle: int | None = None

        self._player: QMediaPlayer | None = None
        self._audio: QAudioOutput | None = None
        if _HAS_MULTIMEDIA:
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._audio.setVolume(0.7)
            self._player.setAudioOutput(self._audio)
            self._player.mediaStatusChanged.connect(self._on_media_status)
            self._player.errorOccurred.connect(self._on_player_error)
            self._player.playbackStateChanged.connect(self._on_playback_state)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        self.folder_label = QLabel()
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet("color: #94a3b8;")
        top.addWidget(self.folder_label, stretch=1)
        self.pick_folder_btn = QPushButton("Папка…")
        self.pick_folder_btn.clicked.connect(self._pick_folder)
        top.addWidget(self.pick_folder_btn)
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedWidth(36)
        self.refresh_btn.setToolTip("Обновить список")
        self.refresh_btn.clicked.connect(self._reload_list)
        top.addWidget(self.refresh_btn)
        root.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._play_selected)
        self.list.itemClicked.connect(self._play_selected)
        split.addWidget(self.list)

        self.media_stack = QStackedWidget()
        if _HAS_MULTIMEDIA:
            self.video = QVideoWidget()
            self.video.setStyleSheet("background: #000;")
        else:
            self.video = QLabel("Нет QtMultimedia")
            self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pulse = PulseVisual()
        self.media_stack.addWidget(self.video)  # 0
        self.media_stack.addWidget(self.pulse)  # 1
        self.media_stack.setCurrentWidget(self.pulse)
        split.addWidget(self.media_stack)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        root.addWidget(split, stretch=1)

        ctrl = QHBoxLayout()
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(40)
        self.play_btn.clicked.connect(self._toggle_play)
        ctrl.addWidget(self.play_btn)

        self.stop_btn = QPushButton("■")
        self.stop_btn.setFixedWidth(40)
        self.stop_btn.clicked.connect(self._stop)
        ctrl.addWidget(self.stop_btn)

        ctrl.addWidget(QLabel("🔊"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.setToolTip("Громкость")
        self.volume_slider.valueChanged.connect(self._on_volume)
        ctrl.addWidget(self.volume_slider)

        ctrl.addWidget(QLabel("Прозрачность"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(85)
        self.opacity_slider.setToolTip("Ниже = прозрачнее")
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        ctrl.addWidget(self.opacity_slider, stretch=1)

        self.ct_label = QLabel("Сквозь: выкл")
        self.ct_label.setStyleSheet("color: #94a3b8; min-width: 88px;")
        self.ct_label.setToolTip("Вкл/выкл только хоткеем Ctrl+Shift+O")
        ctrl.addWidget(self.ct_label)

        self.hide_btn = QPushButton("Скрыть")
        self.hide_btn.setToolTip("Спрятать. Показать: Ctrl+Shift+O или «Фон» в Translator")
        self.hide_btn.clicked.connect(self.hide)
        ctrl.addWidget(self.hide_btn)
        root.addLayout(ctrl)

        hint = QLabel(
            "Ctrl+Shift+O — клики насквозь вкл/выкл (и показать, если скрыто). "
            "Без mp4 справа — анимация-эквалайзер, не одна нота."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        root.addWidget(hint)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #94a3b8;")
        root.addWidget(self.status)

        self._apply_opacity(self.opacity_slider.value())
        self._reload_list()
        self._register_hotkey()

        if not _HAS_MULTIMEDIA:
            self.status.setText(
                "Нет PySide6.QtMultimedia — поставь PySide6 с multimedia."
            )
            self.play_btn.setEnabled(False)

    def _set_folder(self, folder: str) -> None:
        self._folder = os.path.abspath(folder)
        self.folder_label.setText(self._folder)
        self._reload_list()

    def _pick_folder(self) -> None:
        start = self._folder if os.path.isdir(self._folder) else os.path.expanduser("~")
        chosen = QFileDialog.getExistingDirectory(self, "Каталог музыки / видео", start)
        if chosen:
            self._set_folder(chosen)

    def _reload_list(self) -> None:
        self.folder_label.setText(self._folder)
        self.list.clear()
        files = scan_media(self._folder)
        for path in files:
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.list.addItem(item)
        n = len(files)
        self.status.setText(f"{n} файл(ов)" if n else "Пусто — выбери папку с mp3/mp4")

    def _play_selected(self, item: QListWidgetItem | None = None) -> None:
        if not _HAS_MULTIMEDIA or self._player is None:
            return
        item = item or self.list.currentItem()
        if item is None:
            return
        raw = Path(item.data(Qt.ItemDataRole.UserRole))
        play = resolve_play_path(raw)
        self._play_path(play)

    def _play_path(self, path: Path) -> None:
        assert self._player is not None
        path = path.resolve()
        if not path.is_file():
            self.status.setText(f"Нет файла: {path.name}")
            return

        is_video = path.suffix.lower() in VIDEO_EXTS

        # Важно: для audio-only сбрасываем videoOutput — иначе на части
        # сборок Qt mp3 «молчит» / зависает, а на экране пустота.
        if is_video:
            self.pulse.stop()
            self.media_stack.setCurrentWidget(self.video)
            self._player.setVideoOutput(self.video)
        else:
            self._player.setVideoOutput(None)
            self.media_stack.setCurrentWidget(self.pulse)
            self.pulse.start()

        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        self.play_btn.setText("⏸")
        if is_video:
            self.status.setText(f"▶ {path.name}")
        else:
            self.status.setText(f"▶ {path.name} · визуал (нет соседнего mp4)")

    def _toggle_play(self) -> None:
        if not _HAS_MULTIMEDIA or self._player is None:
            return
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._player.play()
            if self.media_stack.currentWidget() is self.pulse:
                self.pulse.start()
        else:
            self._play_selected()

    def _stop(self) -> None:
        if self._player is not None:
            self._player.stop()
        self.play_btn.setText("▶")
        self.pulse.stop()

    def _on_playback_state(self, state) -> None:
        if not _HAS_MULTIMEDIA:
            return
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("⏸")
        else:
            self.play_btn.setText("▶")
            if state == QMediaPlayer.PlaybackState.StoppedState:
                self.pulse.stop()

    def _on_media_status(self, status) -> None:
        if not _HAS_MULTIMEDIA or self._player is None:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._player.setPosition(0)
            self._player.play()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.status.setText("InvalidMedia — кодек/файл не открылся")
            self.pulse.stop()

    def _on_player_error(self, *_args) -> None:
        if self._player is None:
            return
        err = self._player.errorString() or "ошибка воспроизведения"
        self.status.setText(f"Ошибка: {err}")
        self.pulse.stop()

    def _on_volume(self, value: int) -> None:
        if self._audio is not None:
            self._audio.setVolume(max(0.0, min(1.0, value / 100.0)))

    def _on_opacity(self, value: int) -> None:
        self._apply_opacity(value)

    def _apply_opacity(self, percent: int) -> None:
        self.setWindowOpacity(max(0.15, min(1.0, percent / 100.0)))

    def _update_ct_label(self) -> None:
        if self._click_through:
            self.ct_label.setText("Сквозь: вкл")
            self.ct_label.setStyleSheet("color: #38bdf8; min-width: 88px; font-weight: 600;")
        else:
            self.ct_label.setText("Сквозь: выкл")
            self.ct_label.setStyleSheet("color: #94a3b8; min-width: 88px;")

    def _set_click_through(self, enabled: bool) -> None:
        if sys.platform != "win32":
            self.status.setText("Click-through только на Windows")
            return
        self._click_through = bool(enabled)
        self._apply_exstyle()
        self._update_ct_label()
        if enabled:
            self.status.setText("Клики насквозь — Ctrl+Shift+O выключит")
        else:
            self.status.setText("Клики снова ловятся окном")

    def _toggle_click_through(self) -> None:
        self._set_click_through(not self._click_through)

    def _apply_exstyle(self) -> None:
        if sys.platform != "win32":
            return
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            get_long = user32.GetWindowLongPtrW
            set_long = user32.SetWindowLongPtrW
        else:
            get_long = user32.GetWindowLongW
            set_long = user32.SetWindowLongW
        if self._base_exstyle is None:
            self._base_exstyle = int(get_long(hwnd, GWL_EXSTYLE))
        style = self._base_exstyle
        style |= WS_EX_LAYERED
        if self._click_through:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        set_long(hwnd, GWL_EXSTYLE, style)
        self._apply_opacity(self.opacity_slider.value())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_exstyle)

    def _register_hotkey(self) -> None:
        if sys.platform != "win32" or self._hotkey_registered:
            return
        ok = ctypes.windll.user32.RegisterHotKey(
            None, _HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_O
        )
        if not ok:
            self.status.setText("Хоткей Ctrl+Shift+O занят — смени в другой проге")
            return
        self._hotkey_registered = True
        app = QApplication.instance()
        if app is not None and self._hotkey_filter is None:
            self._hotkey_filter = _HotkeyFilter(self._on_global_hotkey)
            app.installNativeEventFilter(self._hotkey_filter)

    def _unregister_hotkey(self) -> None:
        if not self._hotkey_registered:
            return
        ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
        self._hotkey_registered = False
        app = QApplication.instance()
        if app is not None and self._hotkey_filter is not None:
            app.removeNativeEventFilter(self._hotkey_filter)
            self._hotkey_filter = None

    def _on_global_hotkey(self) -> None:
        """Ctrl+Shift+O: показать если скрыто, иначе toggle click-through."""
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()
            if self._click_through:
                self._set_click_through(False)
            return
        self._toggle_click_through()
        if not self._click_through:
            self.raise_()
            self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop()
        self._unregister_hotkey()
        self.closed.emit()
        super().closeEvent(event)


_overlay_singleton: OverlayPlayerWindow | None = None


def open_overlay_player(
    start_dir: str | None = None,
    parent: QWidget | None = None,
) -> OverlayPlayerWindow | None:
    global _overlay_singleton

    if not _HAS_MULTIMEDIA:
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Фон / overlay")
        box.setText(
            "Не найден PySide6.QtMultimedia.\n\n"
            "Окно откроется, но play не заработает без multimedia-части Qt."
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        if box.exec() != QMessageBox.StandardButton.Ok:
            return None

    if start_dir is None:
        dirs = default_music_dirs()
        start_dir = dirs[0] if dirs else os.path.expanduser("~")

    if _overlay_singleton is not None:
        try:
            if start_dir and os.path.isdir(start_dir):
                _overlay_singleton._set_folder(start_dir)
            _overlay_singleton.show()
            _overlay_singleton.raise_()
            _overlay_singleton.activateWindow()
            return _overlay_singleton
        except RuntimeError:
            _overlay_singleton = None

    win = OverlayPlayerWindow(start_dir=start_dir, parent=None)
    win.closed.connect(_clear_singleton)
    _overlay_singleton = win
    win.show()
    return win


def _clear_singleton() -> None:
    global _overlay_singleton
    _overlay_singleton = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    open_overlay_player()
    sys.exit(app.exec())
