"""
IDEA-022 — overlay «Фон»: каталог музыки / mp4.

UX polish P1–P9: обычное окно, Назад, opacity только в play,
хоткеи как у плеера (Ctrl+O = сквозь), play when hidden, prefs.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import math
import os
import random
import re
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QSize, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
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
_MEDIA_FILTER = (
    "Медиа (*.mp3 *.mp4 *.m4a *.wav *.flac *.ogg *.aac *.wma *.webm *.mkv *.avi *.mov *.m4v);;"
    "Видео (*.mp4 *.webm *.mkv *.avi *.mov *.m4v);;"
    "Аудио (*.mp3 *.m4a *.wav *.flac *.ogg *.aac *.wma);;"
    "Все файлы (*)"
)

# Одна тема иконок: stroke slate, без заливок «зелёных кирпичей»
_SVG_STROKE = "#cbd5e1"
_SVG_ICONS: dict[str, str] = {
    "prev": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg>'
    ),
    "play": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<polygon points="6 4 20 12 6 20 6 4"/></svg>'
    ),
    "pause": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<rect x="6" y="5" width="4" height="14"/><rect x="14" y="5" width="4" height="14"/></svg>'
    ),
    "stop": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<rect x="6" y="6" width="12" height="12" rx="1"/></svg>'
    ),
    "next": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>'
    ),
    "vol": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>'
        f'<path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>'
    ),
    "minus": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round">'
        f'<line x1="5" y1="12" x2="19" y2="12"/></svg>'
    ),
    "plus": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round">'
        f'<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>'
    ),
    "folder": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M3 7h5l2 2h11v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>'
    ),
    "settings": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<circle cx="12" cy="12" r="3"/>'
        f'<path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2'
        f'M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg>'
    ),
    "catalog": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round">'
        f'<line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/>'
        f'<line x1="4" y1="17" x2="20" y2="17"/></svg>'
    ),
    "hide": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M17 7l-10 10M7 7l10 10"/></svg>'
    ),
    "back": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<polyline points="15 18 9 12 15 6"/></svg>'
    ),
}

_OVERLAY_QSS = """
OverlayPlayerWindow {
    background: #0b0e14;
    color: #e2e8f0;
}
QListWidget {
    background: #11151e;
    border: 1px solid #1e2533;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 6px;
    color: #cbd5e1;
}
QListWidget::item:selected {
    background: #1e3a5f;
    color: #f8fafc;
    border: 1px solid #38bdf8;
}
QListWidget::item:hover {
    background: #1a2230;
}
QListWidget::item:selected:hover {
    background: #254a73;
}
QLabel#folderLabel, QLabel#timeLabel, QLabel#hintLabel, QLabel#statusLabel,
QLabel#opacityCaption, QLabel#opacityValue, QLabel#ctLabel {
    color: #94a3b8;
    background: transparent;
}
QLabel#ctLabel[ctOn="true"] {
    color: #7dd3fc;
    font-weight: 600;
}
QWidget#densityBar {
    background: transparent;
}
QWidget#chromeBottom {
    background: #10141c;
    border-top: 1px solid #1e2533;
    border-radius: 0px;
}
QWidget#videoColumn {
    background: #05070c;
    border: 1px solid #1e2533;
    border-radius: 8px;
}
QStackedWidget#mediaStack {
    background: #000;
    border: none;
    border-bottom: none;
}
QWidget#transportBar {
    background: #0a0e16;
    border: none;
    border-top: 1px solid #1e2533;
    border-radius: 0 0 7px 7px;
    min-height: 48px;
}
QSplitter::handle:horizontal {
    width: 6px;
    background: transparent;
}
QPushButton#iconBtn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px;
    min-width: 36px;
    min-height: 36px;
}
QPushButton#iconBtn:hover {
    background: #1a2230;
    border-color: #2a3548;
}
QPushButton#iconBtn:pressed {
    background: #0f1520;
}
QPushButton#ghostBtn {
    background: #151a24;
    color: #e2e8f0;
    border: 1px solid #2a3548;
    border-radius: 8px;
    padding: 6px 12px;
}
QPushButton#ghostBtn:hover {
    background: #1a2230;
    border-color: #3b4a63;
}
QSlider#softSlider::groove:horizontal {
    height: 4px;
    background: #1e2533;
    border-radius: 2px;
}
QSlider#softSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    margin: -5px 0;
    background: #94a3b8;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
}
QSlider#softSlider::sub-page:horizontal {
    background: #475569;
    border-radius: 2px;
}
"""


def _svg_icon(name: str, size: int = 20) -> QIcon:
    svg = _SVG_ICONS.get(name)
    if not svg:
        return QIcon()
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return QIcon(pm)


def _icon_button(tooltip: str, icon_name: str, slot) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("iconBtn")
    btn.setIcon(_svg_icon(icon_name, 20))
    btn.setIconSize(QSize(20, 20))
    btn.setToolTip(tooltip)
    btn.setFixedSize(40, 40)
    btn.clicked.connect(slot)
    btn.setAutoDefault(False)
    btn.setDefault(False)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_HOTKEY_CLICK = 0x0221
_HOTKEY_HIDE = 0x0222
_HOTKEY_NEXT = 0x0223
_HOTKEY_PREV = 0x0224
_HOTKEY_STOP = 0x0225
_HOTKEY_OPACITY_UP = 0x0226
_HOTKEY_OPACITY_DOWN = 0x0227
_HOTKEY_ESC = 0x0228
_HOTKEY_SEEK_BACK = 0x0229
_HOTKEY_SEEK_FWD = 0x022A
_HOTKEY_VOL_UP = 0x022B
_HOTKEY_VOL_DOWN = 0x022C
# Тест: кнопки наушников / клавиатуры (VK_MEDIA_*)
_HOTKEY_MEDIA_PLAY = 0x0231
_HOTKEY_MEDIA_NEXT = 0x0232
_HOTKEY_MEDIA_PREV = 0x0233
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
_SEEK_MS = 5000
_VOLUME_STEP = 5
_OPACITY_STEP = 5
_OPACITY_MIN = 5
_OPACITY_MAX = 100
# Метка «сейчас играет» в QListWidgetItem
_ROLE_PLAYING = int(Qt.ItemDataRole.UserRole) + 1

# Зажатие → повтор (без MOD_NOREPEAT)
_REPEATABLE_HOTKEY_IDS = frozenset({
    _HOTKEY_OPACITY_UP,
    _HOTKEY_OPACITY_DOWN,
    _HOTKEY_SEEK_BACK,
    _HOTKEY_SEEK_FWD,
    _HOTKEY_VOL_UP,
    _HOTKEY_VOL_DOWN,
})
_REPEATABLE_SHORTCUT_NAMES = frozenset({
    "seek_back",
    "seek_fwd",
    "vol_up",
    "vol_down",
    "opacity_up",
    "opacity_down",
})
_MEDIA_HOTKEY_IDS = frozenset({
    _HOTKEY_MEDIA_PLAY,
    _HOTKEY_MEDIA_NEXT,
    _HOTKEY_MEDIA_PREV,
})

# Стрелки с Ctrl (±5с / громкость).
_DEFAULT_HOTKEYS = {
    "play_pause": "Space",
    "seek_back": "Ctrl+Left",
    "seek_fwd": "Ctrl+Right",
    "vol_up": "Ctrl+Up",
    "vol_down": "Ctrl+Down",
    "click_through": "Ctrl+O",
    "hide_show": "Ctrl+Shift+O",
    "next_track": "Ctrl+Shift+1",
    "prev_track": "Ctrl+Shift+2",
    "stop_track": "Ctrl+Shift+F1",
    "opacity_up": "Ctrl+]",
    "opacity_down": "Ctrl+[",
    "back_esc": "Esc",
}

# Старые prefs → Ctrl+стрелка
_LEGACY_ARROW_HOTKEYS = {
    "seek_back": ("Left", "Ctrl+Shift+Left"),
    "seek_fwd": ("Right", "Ctrl+Shift+Right"),
    "vol_up": ("Up", "Ctrl+Shift+Up"),
    "vol_down": ("Down", "Ctrl+Shift+Down"),
}

_DEFAULT_PREFS = {
    "stage_opacity": 85,
    "volume": 10,
    "play_when_hidden": True,
    "catalog_preview": True,
    "preview_sound": True,
    "auto_density": False,
    "auto_density_pct": 45,
    "auto_density_idle_sec": 4,
    "hotkeys": dict(_DEFAULT_HOTKEYS),
}

# YouTube-id в скобках: [dQw4w9WgXcQ], [Ci_zad39Uhw]
_YT_ID_BRACKET_RE = re.compile(r"\s*\[[a-zA-Z0-9_-]{10,13}\]\s*")


def _clean_media_title(stem: str) -> str:
    """Убрать [youtubeId] из отображаемого имени; файл не трогаем."""
    t = _YT_ID_BRACKET_RE.sub(" ", stem)
    return re.sub(r"\s{2,}", " ", t).strip() or stem


def _win_long_fns():
    user32 = ctypes.windll.user32
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        get_long = user32.GetWindowLongPtrW
        set_long = user32.SetWindowLongPtrW
        get_long.restype = ctypes.c_longlong
        set_long.restype = ctypes.c_longlong
        get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
        set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
    else:
        get_long = user32.GetWindowLongW
        set_long = user32.SetWindowLongW
    return get_long, set_long


def _prefs_path() -> Path:
    return Path.home() / ".subtitle_ripper" / "overlay_prefs.json"


def load_overlay_prefs() -> dict:
    path = _prefs_path()
    data = dict(_DEFAULT_PREFS)
    data["hotkeys"] = dict(_DEFAULT_HOTKEYS)
    if not path.is_file():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if isinstance(raw, dict):
        if "stage_opacity" in raw:
            data["stage_opacity"] = max(_OPACITY_MIN, min(_OPACITY_MAX, int(raw["stage_opacity"])))
        if "volume" in raw:
            data["volume"] = max(0, min(100, int(raw["volume"])))
        if "play_when_hidden" in raw:
            data["play_when_hidden"] = bool(raw["play_when_hidden"])
        if "catalog_preview" in raw:
            data["catalog_preview"] = bool(raw["catalog_preview"])
        if "preview_sound" in raw:
            data["preview_sound"] = bool(raw["preview_sound"])
        if "auto_density" in raw:
            data["auto_density"] = bool(raw["auto_density"])
        if "auto_density_pct" in raw:
            data["auto_density_pct"] = max(
                _OPACITY_MIN, min(_OPACITY_MAX, int(raw["auto_density_pct"]))
            )
        if "auto_density_idle_sec" in raw:
            data["auto_density_idle_sec"] = max(1, min(120, int(raw["auto_density_idle_sec"])))
        hk = raw.get("hotkeys")
        if isinstance(hk, dict):
            for key, default in _DEFAULT_HOTKEYS.items():
                val = hk.get(key, default)
                if isinstance(val, str) and val.strip():
                    data["hotkeys"][key] = val.strip()
            # Миграция: Left / Ctrl+Shift+Left → Ctrl+Left (как жмёт юзер)
            migrated = False
            for key, legacies in _LEGACY_ARROW_HOTKEYS.items():
                cur = (data["hotkeys"].get(key) or "").strip().lower()
                if cur in {x.lower() for x in legacies}:
                    data["hotkeys"][key] = _DEFAULT_HOTKEYS[key]
                    migrated = True
            if migrated:
                try:
                    path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
    return data


def save_overlay_prefs(**updates) -> dict:
    data = load_overlay_prefs()
    # Не гоняем миграцию повторно через load→save→load: правки уже в data
    for key, value in updates.items():
        if key == "hotkeys" and isinstance(value, dict):
            merged = dict(data["hotkeys"])
            merged.update({k: str(v) for k, v in value.items() if v})
            data["hotkeys"] = merged
        else:
            data[key] = value
    path = _prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


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
    """Список треков без дублей: один stem → видео важнее; тот же YouTube [id] → одна запись."""
    root = Path(folder)
    if not root.is_dir():
        return []
    by_key: dict[str, Path] = {}
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []

    def _prefer(prev: Path, cur: Path) -> Path:
        prev_vid = prev.suffix.lower() in VIDEO_EXTS
        cur_vid = cur.suffix.lower() in VIDEO_EXTS
        if cur_vid and not prev_vid:
            return cur
        if prev_vid and not cur_vid:
            return prev
        # оба видео или оба аудио — более длинное имя часто «полное» (Gojo x Miku),
        # но для id предпочитаем уже выбранное видео; иначе больший файл
        try:
            if cur.stat().st_size > prev.stat().st_size:
                return cur
        except OSError:
            pass
        return prev

    for entry in entries:
        if not entry.is_file() or entry.suffix.lower() not in MEDIA_EXTS:
            continue
        ytid = None
        m = re.search(r"\[([A-Za-z0-9_-]{11})\]", entry.name)
        if m:
            ytid = m.group(1)
        key = f"id:{ytid}" if ytid else f"stem:{entry.stem.lower()}"
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = entry
        else:
            by_key[key] = _prefer(prev, entry)
    return sorted(by_key.values(), key=lambda p: p.name.lower())


def resolve_play_path(path: Path) -> Path:
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


def _parse_hotkey(spec: str, *, allow_repeat: bool = False) -> tuple[int, int] | None:
    """'Ctrl+Shift+O' → (mods, vk) for RegisterHotKey. None if not parseable.

    allow_repeat=True — без MOD_NOREPEAT (зажатие Ctrl+[ крутит плотность).
    """
    parts = [p.strip().lower() for p in spec.replace("-", "+").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    key = parts[-1]
    for p in parts[:-1]:
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p == "alt":
            mods |= MOD_ALT
        elif p in ("win", "meta", "cmd"):
            mods |= MOD_WIN
        else:
            return None
    special = {
        "space": 0x20,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "esc": 0x1B,
        "escape": 0x1B,
        "f1": 0x70,
        "f2": 0x71,
        "[": 0xDB,
        "]": 0xDD,
        "-": 0xBD,
        "=": 0xBB,
        "plus": 0xBB,
        "minus": 0xBD,
    }
    if key in special:
        vk = special[key]
    elif key.startswith("f") and key[1:].isdigit():
        n = int(key[1:])
        if not 1 <= n <= 12:
            return None
        vk = 0x70 + n - 1  # VK_F1..F12
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    else:
        return None
    if not allow_repeat:
        mods |= MOD_NOREPEAT
    return mods, vk


def _qt_match(spec: str, event) -> bool:
    """Сравнить событие клавиши со строкой вроде 'Ctrl+O' / 'Space' / 'Left'."""
    parts = [p.strip().lower() for p in spec.replace("-", "+").split("+") if p.strip()]
    if not parts:
        return False
    key_name = parts[-1]
    need_ctrl = any(p in ("ctrl", "control") for p in parts[:-1])
    need_shift = any(p == "shift" for p in parts[:-1])
    need_alt = any(p == "alt" for p in parts[:-1])
    mods = event.modifiers()
    has_ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
    has_shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
    has_alt = bool(mods & Qt.KeyboardModifier.AltModifier)
    if has_ctrl != need_ctrl or has_shift != need_shift or has_alt != need_alt:
        return False
    key_map = {
        "space": Qt.Key.Key_Space,
        "left": Qt.Key.Key_Left,
        "right": Qt.Key.Key_Right,
        "up": Qt.Key.Key_Up,
        "down": Qt.Key.Key_Down,
        "esc": Qt.Key.Key_Escape,
        "escape": Qt.Key.Key_Escape,
        "f1": Qt.Key.Key_F1,
        "[": Qt.Key.Key_BracketLeft,
        "]": Qt.Key.Key_BracketRight,
        "-": Qt.Key.Key_Minus,
        "=": Qt.Key.Key_Equal,
        "minus": Qt.Key.Key_Minus,
        "plus": Qt.Key.Key_Equal,
    }
    if key_name in key_map:
        return event.key() == key_map[key_name]
    if len(key_name) == 1:
        return event.key() == ord(key_name.upper())
    return False


def _key_event_to_hotkey_spec(event) -> str | None:
    """QKeyEvent → 'Ctrl+Shift+1' / 'Space' / 'Esc'. Lone modifiers → None."""
    key = event.key()
    if key in (
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
        Qt.Key.Key_AltGr,
        Qt.Key.Key_unknown,
    ):
        return None
    mods = event.modifiers()
    parts: list[str] = []
    if mods & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if mods & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if mods & Qt.KeyboardModifier.MetaModifier:
        parts.append("Win")

    named = {
        Qt.Key.Key_Space: "Space",
        Qt.Key.Key_Left: "Left",
        Qt.Key.Key_Right: "Right",
        Qt.Key.Key_Up: "Up",
        Qt.Key.Key_Down: "Down",
        Qt.Key.Key_Escape: "Esc",
        Qt.Key.Key_BracketLeft: "[",
        Qt.Key.Key_BracketRight: "]",
        Qt.Key.Key_Minus: "-",
        Qt.Key.Key_Equal: "=",
        Qt.Key.Key_Plus: "=",
        Qt.Key.Key_Return: "Enter",
        Qt.Key.Key_Enter: "Enter",
        Qt.Key.Key_Tab: "Tab",
        Qt.Key.Key_Backspace: "Backspace",
        Qt.Key.Key_Delete: "Delete",
    }
    if key in named:
        parts.append(named[key])
    elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
        parts.append(f"F{int(key) - int(Qt.Key.Key_F1) + 1}")
    elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        parts.append(chr(ord("0") + (int(key) - int(Qt.Key.Key_0))))
    elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        parts.append(chr(ord("A") + (int(key) - int(Qt.Key.Key_A))))
    else:
        text = (event.text() or "").strip()
        if len(text) == 1 and text.isprintable():
            parts.append(text.upper() if text.isalpha() else text)
        else:
            return None
    return "+".join(parts)


def _hotkey_spec_to_sequence(spec: str) -> QKeySequence:
    return QKeySequence(str(spec or "").strip())


def _sequence_to_hotkey_spec(seq: QKeySequence) -> str:
    """PortableText → 'Ctrl+Shift+1' (как в prefs / RegisterHotKey)."""
    if seq.isEmpty():
        return ""
    raw = seq.toString(QKeySequence.SequenceFormat.PortableText)
    return raw.split(", ")[0].strip()


def _normalize_hotkey_spec(spec: str) -> str:
    s = (spec or "").strip()
    low = s.lower().replace(" ", "")
    aliases = {
        "xbutton1": "Mouse4",
        "mouse4": "Mouse4",
        "back": "Mouse4",
        "xbutton2": "Mouse5",
        "mouse5": "Mouse5",
        "forward": "Mouse5",
        "mouse3": "Mouse3",
        "middle": "Mouse3",
        "mid": "Mouse3",
    }
    return aliases.get(low, s)


def _is_mouse_hotkey_spec(spec: str) -> bool:
    return _normalize_hotkey_spec(spec).lower() in ("mouse3", "mouse4", "mouse5")


def _mouse_button_to_spec(button) -> str | None:
    if button == Qt.MouseButton.MiddleButton:
        return "Mouse3"
    if button == Qt.MouseButton.XButton1:
        return "Mouse4"
    if button == Qt.MouseButton.XButton2:
        return "Mouse5"
    return None


def _is_valid_hotkey_spec(spec: str) -> bool:
    n = _normalize_hotkey_spec(spec)
    if not n:
        return False
    if _is_mouse_hotkey_spec(n):
        return True
    return _parse_hotkey(n, allow_repeat=True) is not None or _parse_hotkey(n) is not None


class HotkeyCaptureEdit(QLineEdit):
    """Клик → жми клавиши или боковую кнопку мыши. Не свободный текст."""

    def __init__(self, initial: str, default: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._default = _normalize_hotkey_spec(default) or default
        self.setReadOnly(True)
        self.setText(_normalize_hotkey_spec(initial) or self._default)
        self.setMinimumHeight(32)
        self.setMinimumWidth(150)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(
            "QLineEdit {"
            "  padding: 6px 12px 6px 12px;"
            "  background: #1a2230;"
            "  color: #e2e8f0;"
            "  border: 1px solid #334155;"
            "  border-radius: 6px;"
            "  font-size: 13px;"
            "}"
            "QLineEdit:focus {"
            "  border: 1px solid #38bdf8;"
            "  background: #0f172a;"
            "}"
        )
        self.setToolTip(
            "Кликни поле → жми сочетание (Ctrl+Shift+1) или боковую кнопку мыши (Mouse4/5),\n"
            "курсор над полем. Esc / клик мимо — выйти из редактирования. Backspace — дефолт."
        )

    def _finish_capture(self) -> None:
        """Отпустить фокус — иначе «залипает» в поле."""
        self.clearFocus()

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self.selectAll()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.isAutoRepeat():
            event.accept()
            return
        key = event.key()
        # Esc — просто выйти из поля, не меняя значение
        if key == Qt.Key.Key_Escape and not (
            event.modifiers()
            & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
                | Qt.KeyboardModifier.ShiftModifier
            )
        ):
            self._finish_capture()
            event.accept()
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not (
            event.modifiers()
            & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
            )
        ):
            self.setText(self._default)
            self._finish_capture()
            event.accept()
            return
        # Enter/Return — принять текущее и выйти
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish_capture()
            event.accept()
            return
        spec = _key_event_to_hotkey_spec(event)
        if spec is None:
            event.accept()
            return
        # Один Esc как хоткей (поле back_esc) — пишем и выходим
        if not _is_valid_hotkey_spec(spec):
            event.accept()
            return
        self.setText(_normalize_hotkey_spec(spec))
        self._finish_capture()
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        mspec = _mouse_button_to_spec(event.button())
        # Mouse3/4/5: пишем сразу (даже если фокус ещё не был — иначе «не ставится»)
        if mspec:
            self.setText(mspec)
            self._finish_capture()
            event.accept()
            return
        super().mousePressEvent(event)
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def current_spec(self) -> str:
        raw = _normalize_hotkey_spec(self.text())
        if not raw or not _is_valid_hotkey_spec(raw):
            return self._default
        return raw


class PulseVisual(QWidget):
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


class OverlaySettingsDialog(QDialog):
    def __init__(self, prefs: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настр. — Фон")
        self.setModal(True)
        self.resize(540, 640)
        self.setMinimumSize(480, 480)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        top = QFormLayout()
        self.play_hidden = QCheckBox("Играть при скрытом фоне / сквозь")
        self.play_hidden.setChecked(bool(prefs.get("play_when_hidden", True)))
        top.addRow(self.play_hidden)
        self.catalog_preview = QCheckBox("Клик в каталоге сразу играет")
        self.catalog_preview.setChecked(bool(prefs.get("catalog_preview", True)))
        top.addRow(self.catalog_preview)
        self.preview_sound = QCheckBox("Звук превью в каталоге")
        self.preview_sound.setToolTip(
            "Выкл = авто-клик по треку без звука (только картинка). "
            "Кнопка ▶ / Enter / 2× в списке — всегда со звуком. В полном окне звук как обычно."
        )
        self.preview_sound.setChecked(bool(prefs.get("preview_sound", True)))
        top.addRow(self.preview_sound)
        self.volume_spin = QSpinBox()
        self.volume_spin.setRange(0, 100)
        self.volume_spin.setSuffix(" %")
        self.volume_spin.setValue(max(0, min(100, int(prefs.get("volume", 10)))))
        self.volume_spin.setToolTip("Стартовая громкость плеера (каталог и fullscreen)")
        top.addRow("Громкость по умолчанию", self.volume_spin)

        self.auto_density = QCheckBox("Авто-плотность (полный экран + play → idle → сквозь)")
        self.auto_density.setChecked(bool(prefs.get("auto_density", False)))
        self.auto_density.setToolTip(
            "Через N сек без мыши по кадру: сам включает сквозь и ставит плотность %"
        )
        top.addRow(self.auto_density)
        self.auto_density_pct = QSpinBox()
        self.auto_density_pct.setRange(_OPACITY_MIN, _OPACITY_MAX)
        self.auto_density_pct.setSuffix(" %")
        self.auto_density_pct.setValue(
            max(_OPACITY_MIN, min(_OPACITY_MAX, int(prefs.get("auto_density_pct", 45))))
        )
        top.addRow("Авто: целевая плотность", self.auto_density_pct)
        self.auto_density_idle = QSpinBox()
        self.auto_density_idle.setRange(1, 120)
        self.auto_density_idle.setSuffix(" с")
        self.auto_density_idle.setValue(max(1, min(120, int(prefs.get("auto_density_idle_sec", 4)))))
        top.addRow("Авто: пауза до сквозь", self.auto_density_idle)
        layout.addLayout(top)

        hk_title = QLabel(
            "Горячие клавиши — клик по полю, потом жми сочетание или Mouse4/5 (скролл ↓)"
        )
        hk_title.setStyleSheet("color:#94a3b8;font-size:12px;")
        layout.addWidget(hk_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumHeight(320)
        scroll.setFrameShape(QScrollArea.Shape.StyledPanel)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setSpacing(8)
        form.setContentsMargins(8, 8, 12, 8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.hk_edits: dict[str, HotkeyCaptureEdit] = {}
        labels = {
            "play_pause": "Play/Pause (фокус на Фон)",
            "seek_back": "Seek −5с (глоб.)",
            "seek_fwd": "Seek +5с (глоб.)",
            "vol_up": "Громкость + (глоб.)",
            "vol_down": "Громкость − (глоб.)",
            "next_track": "След. трек",
            "prev_track": "Пред. трек",
            "stop_track": "Play/Pause (глоб.)",
            "opacity_up": "Прозрачность +",
            "opacity_down": "Прозрачность −",
            "click_through": "Сквозь",
            "hide_show": "Скрыть/показать",
            "back_esc": "Esc (сквозь выкл / каталог)",
        }
        hotkeys = prefs.get("hotkeys") or _DEFAULT_HOTKEYS
        for key, label in labels.items():
            default = _DEFAULT_HOTKEYS[key]
            edit = HotkeyCaptureEdit(str(hotkeys.get(key, default)), default)
            self.hk_edits[key] = edit
            form.addRow(label, edit)

        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        hint = QLabel(
            "Пока окно открыто — глобальные хоткеи Фон выкл (можно записать комбо).\n"
            "Backspace — сброс. Боковые кнопки мыши: клик в поле → Mouse4/Mouse5."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#94a3b8;font-size:11px;")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_prefs(self) -> dict:
        hotkeys = {k: e.current_spec() for k, e in self.hk_edits.items()}
        return {
            "play_when_hidden": self.play_hidden.isChecked(),
            "catalog_preview": self.catalog_preview.isChecked(),
            "preview_sound": self.preview_sound.isChecked(),
            "volume": int(self.volume_spin.value()),
            "auto_density": self.auto_density.isChecked(),
            "auto_density_pct": int(self.auto_density_pct.value()),
            "auto_density_idle_sec": int(self.auto_density_idle.value()),
            "hotkeys": hotkeys,
        }


class OverlayPlayerWindow(QWidget):
    """Окно фона: каталог → play; always-on-top; Назад → close."""

    closed = Signal()
    hidden_keep = Signal()  # устарело: Ctrl+Shift+O больше не поднимает Translator
    hotkey_pressed = Signal(int)

    def __init__(self, start_dir: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_OVERLAY_WINDOW_TITLE)
        # Каталог — обычное окно; topmost только в полном экране (см. _sync_topmost_state)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1100, 640)
        self.setObjectName("OverlayPlayerWindow")
        self.setStyleSheet(_OVERLAY_QSS)
        # Без белой вспышки при showNormal / смене флагов (дефолт Win — белый)
        _bg = QColor("#0b0e14")
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, _bg)
        pal.setColor(QPalette.ColorRole.Base, _bg)
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        self._prefs = load_overlay_prefs()
        self._folder = start_dir or (
            default_music_dirs()[0] if default_music_dirs() else os.path.expanduser("~")
        )
        self._click_through = False
        self._playing = False
        self._seek_dragging = False
        self._stage_mode = False
        self._normal_geometry = None
        self._splitter_sizes: list[int] | None = None
        self._last_play_path: str | None = None
        self._force_catalog_sound = False  # ▶ / Enter — звук даже если «превью без звука»
        self._hold_stage_opacity = False  # смена трека: не мигать 100% на StoppedState
        # Клик по кадру: single = play/pause, dbl = stage/каталог (таймер гасит гонку с dblclick)
        self._video_click_timer = QTimer(self)
        self._video_click_timer.setSingleShot(True)
        self._video_click_timer.timeout.connect(self._on_video_single_click)
        self._suppress_video_click = False  # Release сразу после DblClick
        self._auto_density_timer = QTimer(self)
        self._auto_density_timer.setSingleShot(True)
        self._auto_density_timer.timeout.connect(self._on_auto_density_fire)
        self._auto_density_armed = False  # сквозь включили мы сами
        self._hk_retry_pending = False
        self._hotkeys_registered: set[int] = set()
        self._base_exstyle: int | None = None
        self._app_filter_installed = False
        self._hotkey_thread: threading.Thread | None = None
        self._hotkey_stop: threading.Event | None = None
        self._hotkey_thread_id: int | None = None
        self._last_hk_id: int | None = None
        self._last_hk_t: float = 0.0
        self._player: QMediaPlayer | None = None
        self._audio: QAudioOutput | None = None
        self.hotkey_pressed.connect(self._on_global_hotkey)
        if _HAS_MULTIMEDIA:
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            vol0 = max(0, min(100, int(self._prefs.get("volume", 10)))) / 100.0
            self._audio.setVolume(vol0)
            self._player.setAudioOutput(self._audio)
            self._player.mediaStatusChanged.connect(self._on_media_status)
            self._player.errorOccurred.connect(self._on_player_error)
            self._player.playbackStateChanged.connect(self._on_playback_state)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self.chrome_top = QWidget()
        top = QHBoxLayout(self.chrome_top)
        top.setContentsMargins(0, 0, 0, 0)
        self.back_btn = _icon_button("Назад в Translator", "back", self.close)
        top.addWidget(self.back_btn)
        self.folder_label = QLabel()
        self.folder_label.setObjectName("folderLabel")
        self.folder_label.setWordWrap(True)
        top.addWidget(self.folder_label, stretch=1)
        self.pick_folder_btn = QPushButton("Папка")
        self.pick_folder_btn.setObjectName("ghostBtn")
        self.pick_folder_btn.setIcon(_svg_icon("folder", 16))
        self.pick_folder_btn.setIconSize(QSize(16, 16))
        self.pick_folder_btn.setToolTip(
            "Диалог с фильтром mp3/mp4 — выбери любой файл в нужной папке"
        )
        self.pick_folder_btn.clicked.connect(self._pick_folder)
        top.addWidget(self.pick_folder_btn)
        self.settings_btn = QPushButton("Настр.")
        self.settings_btn.setObjectName("ghostBtn")
        self.settings_btn.setIcon(_svg_icon("settings", 16))
        self.settings_btn.setIconSize(QSize(16, 16))
        self.settings_btn.clicked.connect(self._open_settings)
        top.addWidget(self.settings_btn)
        root.addWidget(self.chrome_top)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setWordWrap(False)
        # 1-й клик — выбор; Enter/2× — play (если превью выкл); превью вкл — сразу play
        self.list.itemClicked.connect(self._on_list_clicked)
        self.list.itemActivated.connect(self._on_list_activated)
        self._splitter.addWidget(self.list)

        self.media_stack = QStackedWidget()
        self.media_stack.setObjectName("mediaStack")
        if _HAS_MULTIMEDIA:
            self.video = QVideoWidget()
            self.video.setStyleSheet("background: #000;")
            self.video.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        else:
            self.video = QLabel("Нет QtMultimedia")
            self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pulse = PulseVisual()
        self.pulse.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.media_stack.addWidget(self.video)
        self.media_stack.addWidget(self.pulse)
        self.media_stack.setCurrentWidget(self.pulse)
        self.video.installEventFilter(self)
        self.pulse.installEventFilter(self)
        self.media_stack.installEventFilter(self)
        self.video.setMouseTracking(True)
        self.pulse.setMouseTracking(True)
        self.media_stack.setMouseTracking(True)

        # Превью: одна карточка — видео сверху, transport вплотную снизу (0 gap).
        # Не оверлей на QVideoWidget: нативный HWND часто «отрывает» слой.
        self.video_column = QWidget()
        self.video_column.setObjectName("videoColumn")
        self._video_shell = QVBoxLayout(self.video_column)
        self._video_shell.setContentsMargins(0, 0, 0, 0)
        self._video_shell.setSpacing(0)
        self._video_shell.addWidget(self.media_stack, stretch=1)

        self.transport_bar = QWidget()
        self.transport_bar.setObjectName("transportBar")
        ctrl = QHBoxLayout(self.transport_bar)
        ctrl.setContentsMargins(10, 8, 10, 8)
        ctrl.setSpacing(4)
        self.prev_btn = _icon_button("Предыдущий (Ctrl+Shift+2)", "prev", self._play_prev)
        ctrl.addWidget(self.prev_btn)
        self.play_btn = _icon_button("Play / Pause (Space)", "play", self._toggle_play)
        ctrl.addWidget(self.play_btn)
        self.stop_btn = _icon_button("Стоп", "stop", self._stop)
        ctrl.addWidget(self.stop_btn)
        self.next_btn = _icon_button("Следующий (Ctrl+Shift+1)", "next", self._play_next)
        ctrl.addWidget(self.next_btn)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("timeLabel")
        self.time_label.setMinimumWidth(92)
        self.time_label.setToolTip("Текущая позиция / длительность")
        ctrl.addWidget(self.time_label)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setObjectName("softSlider")
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setToolTip("Перемотка")
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.sliderMoved.connect(self._on_seek_moved)
        ctrl.addWidget(self.seek_slider, stretch=2)

        self.vol_icon = QLabel()
        self.vol_icon.setPixmap(_svg_icon("vol", 18).pixmap(18, 18))
        ctrl.addWidget(self.vol_icon)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("softSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(max(0, min(100, int(self._prefs.get("volume", 10)))))
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.valueChanged.connect(self._on_volume)
        ctrl.addWidget(self.volume_slider)
        self._video_shell.addWidget(self.transport_bar, stretch=0)

        self._splitter.addWidget(self.video_column)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(6)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 3)
        self._splitter.setSizes([320, 740])
        root.addWidget(self._splitter, stretch=1)

        # Нижний хром: плотность / каталог / скрыть (скрыт в каталоге) / подсказки
        self.chrome_bottom = QWidget()
        self.chrome_bottom.setObjectName("chromeBottom")
        bottom = QVBoxLayout(self.chrome_bottom)
        bottom.setContentsMargins(10, 8, 10, 8)
        bottom.setSpacing(6)

        self.chrome_actions = QWidget()
        ctrl2 = QHBoxLayout(self.chrome_actions)
        ctrl2.setContentsMargins(0, 0, 0, 0)
        ctrl2.setSpacing(6)
        self.density_bar = QWidget()
        self.density_bar.setObjectName("densityBar")
        dens = QHBoxLayout(self.density_bar)
        dens.setContentsMargins(0, 0, 0, 0)
        dens.setSpacing(8)
        self.opacity_caption = QLabel("Плотность")
        self.opacity_caption.setObjectName("opacityCaption")
        _dens_tip = (
            "В сквозь (Ctrl+O): прозрачность окна. "
            "Без сквозь всегда 100% — иначе клики не доходят до YouTube/Cursor. "
            "Слайдер задаёт значение заранее; Ctrl+[ / ] в сквозь."
        )
        self.opacity_caption.setToolTip(_dens_tip)
        dens.addWidget(self.opacity_caption)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        # Тот же softSlider, что seek/volume — один стиль ручки
        self.opacity_slider.setObjectName("softSlider")
        self.opacity_slider.setRange(_OPACITY_MIN, _OPACITY_MAX)
        self.opacity_slider.setValue(
            max(_OPACITY_MIN, min(_OPACITY_MAX, int(self._prefs.get("stage_opacity", 85))))
        )
        self.opacity_slider.setFixedWidth(140)
        self.opacity_slider.setToolTip(_dens_tip)
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        self.opacity_slider.sliderReleased.connect(self._flush_opacity_prefs)
        dens.addWidget(self.opacity_slider)
        self.opacity_value = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_value.setObjectName("opacityValue")
        self.opacity_value.setMinimumWidth(36)
        dens.addWidget(self.opacity_value)
        self.ct_label = QLabel("Сквозь: выкл")
        self.ct_label.setObjectName("ctLabel")
        self.ct_label.setMinimumWidth(88)
        dens.addWidget(self.ct_label)
        dens.addStretch(1)
        # Старые +/- кнопки убраны — слайдер + Ctrl+[ / Ctrl+]
        self.opacity_down_btn = None
        self.opacity_up_btn = None
        self.density_bar.hide()
        ctrl2.addWidget(self.density_bar, stretch=1)
        self.catalog_btn = QPushButton("Каталог")
        self.catalog_btn.setObjectName("ghostBtn")
        self.catalog_btn.setIcon(_svg_icon("catalog", 16))
        self.catalog_btn.setIconSize(QSize(16, 16))
        self.catalog_btn.setToolTip("К списку — музыка не стопается")
        self.catalog_btn.clicked.connect(self._enter_catalog)
        self.catalog_btn.hide()
        ctrl2.addWidget(self.catalog_btn)
        self.hide_btn = QPushButton("Скрыть")
        self.hide_btn.setObjectName("ghostBtn")
        self.hide_btn.setIcon(_svg_icon("hide", 14))
        self.hide_btn.setIconSize(QSize(14, 14))
        self.hide_btn.setToolTip("Спрятать окно. Вернуть — кнопкой «Фон» в основном окне.")
        self.hide_btn.clicked.connect(self._hide_keep_music)
        self.hide_btn.hide()  # в каталоге не нужен — только fullscreen / хоткей
        ctrl2.addWidget(self.hide_btn)
        self.chrome_actions.hide()  # каталог: только подсказка/статус
        bottom.addWidget(self.chrome_actions)

        self.hint = QLabel("")
        self.hint.setObjectName("hintLabel")
        self.hint.setWordWrap(True)
        bottom.addWidget(self.hint)
        self._refresh_hint()

        self.status = QLabel("")
        self.status.setObjectName("statusLabel")
        bottom.addWidget(self.status)
        root.addWidget(self.chrome_bottom)

        for btn in (
            self.back_btn,
            self.pick_folder_btn,
            self.settings_btn,
            self.catalog_btn,
            self.prev_btn,
            self.play_btn,
            self.stop_btn,
            self.next_btn,
            self.hide_btn,
        ):
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._apply_catalog_opacity()
        self._reload_list()
        self._shortcuts: list[QShortcut] = []
        self._install_shortcuts()
        self._register_hotkeys()

        if not _HAS_MULTIMEDIA:
            self.status.setText("Нет PySide6.QtMultimedia — play недоступен.")
            self.play_btn.setEnabled(False)

    def _refresh_hint(self) -> None:
        hk = self._prefs.get("hotkeys") or _DEFAULT_HOTKEYS
        hide = hk.get("hide_show", "Ctrl+Shift+O")
        if self._stage_mode:
            self.hint.setText(
                f"Клик — play/pause · 2× — каталог · "
                f"{hk.get('play_pause', 'Space')} · "
                f"{hk.get('next_track', 'Ctrl+Shift+1')}/{hk.get('prev_track', 'Ctrl+Shift+2')} трек · "
                f"{hk.get('opacity_down', 'Ctrl+[')}/{hk.get('opacity_up', 'Ctrl+]')} плотность · "
                f"{hk.get('click_through', 'Ctrl+O')} сквозь · "
                f"{hide} скрыть · Esc — каталог · ☰ Каталог"
            )
        else:
            self.hint.setText(
                f"Кадр: клик — play/pause · 2× — полное окно · "
                f"{hk.get('play_pause', 'Space')} / {hk.get('stop_track', 'Ctrl+Shift+F1')} · "
                f"{hk.get('next_track', 'Ctrl+Shift+1')}/{hk.get('prev_track', 'Ctrl+Shift+2')} · "
                f"{hide} скрыть · "
                "Ctrl+O в каталоге не используется (только в полном окне)"
            )

    def _install_shortcuts(self) -> None:
        """QShortcut с WindowShortcut — работает даже когда фокус на видео/кнопке."""
        for sc in self._shortcuts:
            sc.setParent(None)
        self._shortcuts = []
        hk = self._prefs.get("hotkeys") or _DEFAULT_HOTKEYS
        pairs: list[tuple[str, str, object]] = [
            (hk.get("play_pause", "Space"), "play_pause", self._toggle_play),
            (hk.get("seek_back", "Ctrl+Left"), "seek_back", lambda: self._seek_by(-_SEEK_MS)),
            (hk.get("seek_fwd", "Ctrl+Right"), "seek_fwd", lambda: self._seek_by(_SEEK_MS)),
            (hk.get("vol_up", "Ctrl+Up"), "vol_up", lambda: self._nudge_volume(_VOLUME_STEP)),
            (hk.get("vol_down", "Ctrl+Down"), "vol_down", lambda: self._nudge_volume(-_VOLUME_STEP)),
            (
                hk.get("click_through", "Ctrl+O"),
                "click_through",
                lambda: self._toggle_click_through() if self._stage_mode else None,
            ),
            (hk.get("hide_show", "Ctrl+Shift+O"), "hide_show", self._toggle_hide_or_show),
            (hk.get("next_track", "Ctrl+Shift+1"), "next_track", self._play_next),
            (hk.get("prev_track", "Ctrl+Shift+2"), "prev_track", self._play_prev),
            (hk.get("stop_track", "Ctrl+Shift+F1"), "stop_track", self._toggle_play),
            (hk.get("opacity_up", "Ctrl+]"), "opacity_up", lambda: self._nudge_opacity(_OPACITY_STEP)),
            (hk.get("opacity_down", "Ctrl+["), "opacity_down", lambda: self._nudge_opacity(-_OPACITY_STEP)),
            (hk.get("back_esc", "Esc"), "back_esc", self._on_escape),
        ]
        for spec, name, slot in pairs:
            if not spec or not str(spec).strip():
                continue
            seq = QKeySequence(str(spec).strip())
            sc = QShortcut(seq, self)
            # WindowShortcut: не жрать Space/стрелки у других окон того же Qt-процесса
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            # Зажатие: плотность / seek / громкость повторяют
            sc.setAutoRepeat(name in _REPEATABLE_SHORTCUT_NAMES)
            sc.activated.connect(slot)
            self._shortcuts.append(sc)

    def _set_folder(self, folder: str) -> None:
        self._folder = os.path.abspath(folder)
        self.folder_label.setText(self._folder)
        self._reload_list()

    def _pick_folder(self) -> None:
        """Диалог с фильтром медиа: видно типы файлов; папка = родитель выбранного файла."""
        start = self._folder if os.path.isdir(self._folder) else os.path.expanduser("~")
        dlg = QFileDialog(self, "Папка с музыкой / видео", start)
        dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
        dlg.setNameFilter(_MEDIA_FILTER)
        dlg.selectNameFilter(_MEDIA_FILTER.split(";;")[0])
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, False)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        files = dlg.selectedFiles()
        if not files:
            return
        chosen = Path(files[0])
        folder = chosen.parent if chosen.is_file() else chosen
        if folder.is_dir():
            self._set_folder(str(folder))

    def _set_play_icon(self, playing: bool) -> None:
        self.play_btn.setIcon(_svg_icon("pause" if playing else "play", 20))

    def _apply_output_volume(self) -> None:
        """Каталог: mute только тихое превью; ▶/Enter — со звуком. Stage — слайдер."""
        if self._audio is None:
            return
        silent_preview = (
            not self._stage_mode
            and not self._prefs.get("preview_sound", True)
            and not self._force_catalog_sound
        )
        if silent_preview:
            self._audio.setVolume(0.0)
        else:
            self._audio.setVolume(max(0.0, min(1.0, self.volume_slider.value() / 100.0)))

    def _reload_list(self) -> None:
        self.folder_label.setText(self._folder)
        self.list.clear()
        files = scan_media(self._folder)
        for path in files:
            # Показываем stem без расширения и без [youtubeId]
            title = _clean_media_title(path.stem)
            label = title
            if path.suffix.lower() in VIDEO_EXTS:
                label = f"{title}  · video"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(path.name)
            self.list.addItem(item)
        self._refresh_playing_highlight()
        n = len(files)
        if n:
            self.status.setText(f"{n} трек(ов) (без дублей stem/YouTube id)")
        else:
            self.status.setText(
                "Пусто — Папка… → выбери любой .mp3/.mp4 в нужной папке "
                "(фильтр Медиа / Видео / Аудио)"
            )

    def _refresh_playing_highlight(self) -> None:
        """Цвет + ▶ у трека, который играет — иначе в каталоге не видно «какой»."""
        if not hasattr(self, "list"):
            return
        playing_key = self._last_play_path if self._playing else None
        font_normal = self.list.font()
        font_play = QFont(font_normal)
        font_play.setBold(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item is None:
                continue
            raw = Path(item.data(Qt.ItemDataRole.UserRole))
            key = str(resolve_play_path(raw).resolve())
            is_now = bool(playing_key and key == playing_key)
            base = item.text()
            if base.startswith("▶ "):
                base = base[2:]
            if is_now:
                item.setText(f"▶ {base}")
                item.setBackground(QBrush(QColor("#0e3a4a")))
                item.setForeground(QBrush(QColor("#7dd3fc")))
                item.setFont(font_play)
                item.setData(_ROLE_PLAYING, True)
                self.list.scrollToItem(item)
            else:
                item.setText(base)
                item.setBackground(QBrush())
                item.setForeground(QBrush(QColor("#cbd5e1")))
                item.setFont(font_normal)
                item.setData(_ROLE_PLAYING, False)

    def _on_list_clicked(self, item: QListWidgetItem | None = None) -> None:
        """Клик: превью вкл → play; выкл → только выбор."""
        if not _HAS_MULTIMEDIA or self._player is None:
            return
        item = item or self.list.currentItem()
        if item is None:
            return
        raw = Path(item.data(Qt.ItemDataRole.UserRole))
        play = resolve_play_path(raw)
        play_key = str(play.resolve())
        preview_on = bool(self._prefs.get("catalog_preview", True))
        if self._last_play_path == play_key:
            if not self._stage_mode and self._playing:
                self._enter_stage()
                return
            if preview_on and not self._playing:
                self._play_path(play, force_sound=False)
                return
            if not preview_on:
                self.status.setText(
                    f"Выбрано: {play.name} · ▶ / Enter / 2× в списке — play"
                )
            return
        if preview_on:
            self._play_path(play, force_sound=False)
        else:
            self.status.setText(
                f"Выбрано: {play.name} · ▶ / Enter / 2× в списке — play"
            )

    def _on_list_activated(self, item: QListWidgetItem | None = None) -> None:
        """Enter / двойной клик по строке — всегда play (со звуком)."""
        if not _HAS_MULTIMEDIA or self._player is None:
            return
        item = item or self.list.currentItem()
        if item is None:
            return
        raw = Path(item.data(Qt.ItemDataRole.UserRole))
        play = resolve_play_path(raw)
        play_key = str(play.resolve())
        if self._last_play_path == play_key and self._playing and not self._stage_mode:
            self._enter_stage()
            return
        self._play_path(play, force_sound=True)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """Кадр: клик play/pause, 2× stage↔каталог; Space/стрелки при фокусе на видео."""
        et = event.type()
        if et == QEvent.Type.KeyPress and not event.isAutoRepeat():
            if not self.isVisible():
                return super().eventFilter(watched, event)
            # Не перехватывать набор в диалогах/полях
            fw = QApplication.focusWidget()
            if fw is not None:
                from PySide6.QtWidgets import (
                    QComboBox,
                    QLineEdit,
                    QPlainTextEdit,
                    QSpinBox,
                    QTextEdit,
                )

                if isinstance(
                    fw,
                    (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox),
                ):
                    return super().eventFilter(watched, event)
                if not (fw is self or self.isAncestorOf(fw) or self.isActiveWindow()):
                    return super().eventFilter(watched, event)
            elif not self.isActiveWindow():
                return super().eventFilter(watched, event)
            hk = self._prefs.get("hotkeys") or _DEFAULT_HOTKEYS
            if _qt_match(hk.get("play_pause", "Space"), event):
                self._toggle_play()
                return True
            if _qt_match(hk.get("next_track", "Ctrl+Shift+1"), event):
                self._play_next()
                return True
            if _qt_match(hk.get("prev_track", "Ctrl+Shift+2"), event):
                self._play_prev()
                return True
            if _qt_match(hk.get("seek_back", "Left"), event):
                self._seek_by(-_SEEK_MS)
                return True
            if _qt_match(hk.get("seek_fwd", "Right"), event):
                self._seek_by(_SEEK_MS)
                return True
            if _qt_match(hk.get("vol_up", "Up"), event):
                self._nudge_volume(_VOLUME_STEP)
                return True
            if _qt_match(hk.get("vol_down", "Down"), event):
                self._nudge_volume(-_VOLUME_STEP)
                return True
            if _qt_match(hk.get("back_esc", "Esc"), event):
                self._on_escape()
                return True
        # Боковые кнопки мыши (Mouse4/5) — только когда Фон активен и не сквозь
        if (
            et == QEvent.Type.MouseButtonPress
            and not self._click_through
            and self.isVisible()
            and self.isActiveWindow()
        ):
            try:
                btn = event.button()
            except Exception:
                btn = None
            if btn is not None and self._dispatch_mouse_hotkey(btn):
                return True
        if watched in (self.video, self.pulse, self.media_stack) and not self._click_through:
            if et == QEvent.Type.MouseMove and self._stage_mode and self._playing:
                self._bump_auto_density_idle()
            try:
                btn = event.button()
            except Exception:
                btn = None
            if btn == Qt.MouseButton.LeftButton:
                if et == QEvent.Type.MouseButtonDblClick:
                    # Сбросить отложенный single — иначе dbl ещё и pause/play мигнёт
                    self._video_click_timer.stop()
                    self._suppress_video_click = True  # следующий Release от dbl
                    if self._stage_mode:
                        self._enter_catalog()
                        return True
                    # Каталог: 2× по кадру → полное окно
                    if self._playing or self._last_play_path:
                        self._enter_stage()
                        return True
                    self._suppress_video_click = False
                if et == QEvent.Type.MouseButtonRelease:
                    if self._suppress_video_click:
                        self._suppress_video_click = False
                        return True
                    # Ждём doubleClickInterval: один клик = play/pause (каталог и stage)
                    interval = QApplication.doubleClickInterval()
                    self._video_click_timer.start(max(200, int(interval)))
                    self._bump_auto_density_idle()
                    return True
        return super().eventFilter(watched, event)

    def _dispatch_mouse_hotkey(self, button) -> bool:
        """Mouse3/4/5 из prefs → то же, что глобальные хоткеи (пока Фон в фокусе)."""
        want = _mouse_button_to_spec(button)
        if not want:
            return False
        hk = self._prefs.get("hotkeys") or _DEFAULT_HOTKEYS
        want_l = want.lower()
        action = None
        for key, spec in hk.items():
            if _normalize_hotkey_spec(str(spec)).lower() == want_l:
                action = key
                break
        if action is None:
            return False
        if action == "play_pause" or action == "stop_track":
            self._toggle_play()
        elif action == "next_track":
            self._play_next()
        elif action == "prev_track":
            self._play_prev()
        elif action == "seek_back":
            self._seek_by(-_SEEK_MS)
        elif action == "seek_fwd":
            self._seek_by(_SEEK_MS)
        elif action == "vol_up":
            self._nudge_volume(_VOLUME_STEP)
        elif action == "vol_down":
            self._nudge_volume(-_VOLUME_STEP)
        elif action == "opacity_up":
            self._nudge_opacity(_OPACITY_STEP)
        elif action == "opacity_down":
            self._nudge_opacity(-_OPACITY_STEP)
        elif action == "click_through":
            if self._stage_mode:
                self._toggle_click_through()
        elif action == "hide_show":
            self._toggle_hide_or_show()
        elif action == "back_esc":
            self._on_escape()
        else:
            return False
        return True

    def _bump_auto_density_idle(self) -> None:
        """Сброс idle-таймера авто-плотности (движение/клик по кадру)."""
        if self._click_through or not self._prefs.get("auto_density"):
            return
        if self._stage_mode and self._playing:
            self._arm_auto_density_timer()

    def _arm_auto_density_timer(self) -> None:
        self._auto_density_timer.stop()
        if not self._prefs.get("auto_density"):
            return
        if not self._stage_mode or not self._playing or self._click_through:
            return
        sec = max(1, min(120, int(self._prefs.get("auto_density_idle_sec", 4))))
        self._auto_density_timer.start(sec * 1000)

    def _stop_auto_density_timer(self, *, exit_ct_if_armed: bool = False) -> None:
        self._auto_density_timer.stop()
        if exit_ct_if_armed and self._auto_density_armed and self._click_through:
            self._auto_density_armed = False
            self._set_click_through(False)
        else:
            if not self._click_through:
                self._auto_density_armed = False

    def _on_auto_density_fire(self) -> None:
        """Idle истёк → сквозь + целевая плотность (не пишем prefs на диск)."""
        if not self._prefs.get("auto_density"):
            return
        if not self._stage_mode or not self._playing or self._click_through:
            return
        pct = max(
            _OPACITY_MIN,
            min(_OPACITY_MAX, int(self._prefs.get("auto_density_pct", 45))),
        )
        self._auto_density_armed = True
        self._set_click_through(True)
        # После CT: выставить % (CT сам мог ужать >55→40)
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(pct)
        self.opacity_slider.blockSignals(False)
        if hasattr(self, "opacity_value"):
            self.opacity_value.setText(f"{pct}%")
        self._apply_stage_opacity()
        self.status.setText(
            f"Авто-плотность {pct}% · сквозь · Ctrl+O / Esc — вернуть управление"
        )

    def _on_video_single_click(self) -> None:
        """Один клик по кадру (после таймера) — play/pause."""
        if self._click_through or not self.isVisible():
            return
        self._toggle_play()

    def _play_selected(self, item: QListWidgetItem | None = None) -> None:
        if not _HAS_MULTIMEDIA or self._player is None:
            return
        item = item or self.list.currentItem()
        if item is None:
            return
        raw = Path(item.data(Qt.ItemDataRole.UserRole))
        self._play_path(resolve_play_path(raw), force_sound=True)

    def _play_path(self, path: Path, *, force_sound: bool = False) -> None:
        assert self._player is not None
        path = path.resolve()
        if not path.is_file():
            self.status.setText(f"Нет файла: {path.name}")
            return
        self._force_catalog_sound = bool(force_sound) or self._stage_mode
        # setSource → StoppedState → раньше мигал opacity 100%. Держим плотность.
        if self._stage_mode:
            self._hold_stage_opacity = True
            self._apply_stage_opacity()
        is_video = path.suffix.lower() in VIDEO_EXTS
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
        self._set_play_icon(True)
        self._playing = True
        self._last_play_path = str(path)
        if self._stage_mode:
            self._apply_stage_opacity()
        else:
            self._apply_catalog_opacity()
        self._apply_output_volume()
        self.status.setText(f"▶ {_clean_media_title(path.stem)}{path.suffix.lower()}")
        self._refresh_playing_highlight()
        QTimer.singleShot(1000, self._clear_opacity_hold)
        if self._stage_mode and self._playing:
            self._arm_auto_density_timer()
        key = str(path)
        for i in range(self.list.count()):
            item = self.list.item(i)
            raw = Path(item.data(Qt.ItemDataRole.UserRole))
            if str(resolve_play_path(raw).resolve()) == key:
                self.list.setCurrentRow(i)
                break

    def _clear_opacity_hold(self) -> None:
        self._hold_stage_opacity = False

    def _playlist_index(self) -> int:
        if self._last_play_path:
            for i in range(self.list.count()):
                item = self.list.item(i)
                raw = Path(item.data(Qt.ItemDataRole.UserRole))
                if str(resolve_play_path(raw).resolve()) == self._last_play_path:
                    return i
        row = self.list.currentRow()
        return row if row >= 0 else 0

    def _play_at_index(self, index: int) -> None:
        """Сменить трек. Не уводит в fullscreen — только play в текущем режиме."""
        n = self.list.count()
        if n <= 0 or not _HAS_MULTIMEDIA or self._player is None:
            return
        index %= n
        item = self.list.item(index)
        if item is None:
            return
        self.list.setCurrentRow(index)
        path = resolve_play_path(Path(item.data(Qt.ItemDataRole.UserRole)))
        self._play_path(path, force_sound=True)
        if self._stage_mode:
            self._apply_stage_opacity()
        else:
            self._apply_catalog_opacity()

    def _play_next(self) -> None:
        self._play_at_index(self._playlist_index() + 1)

    def _play_prev(self) -> None:
        self._play_at_index(self._playlist_index() - 1)

    def _nudge_opacity(self, delta: int) -> None:
        if not self._stage_mode:
            return
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(
            max(_OPACITY_MIN, min(_OPACITY_MAX, self.opacity_slider.value() + delta))
        )
        self.opacity_slider.blockSignals(False)
        if hasattr(self, "opacity_value"):
            self.opacity_value.setText(f"{self.opacity_slider.value()}%")
        self._prefs["stage_opacity"] = int(self.opacity_slider.value())
        self._apply_stage_opacity()
        self._flush_opacity_prefs()

    def _enter_stage(self) -> None:
        """Полное окно: каталог спрятан, видео/пульс на весь экран, управление снизу."""
        if self._stage_mode:
            return
        self._stage_mode = True
        sizes = self._splitter.sizes()
        if len(sizes) >= 2 and sizes[0] > 40:
            self._splitter_sizes = sizes
        if not self.isFullScreen():
            self._normal_geometry = self.geometry()
        self.list.hide()
        self.list.setMaximumWidth(0)
        self._splitter.setSizes([0, max(self._splitter.width(), 1)])
        # Topmost только через Win32 (_sync_topmost_state) — setWindowFlag
        # пересоздаёт HWND и даёт белую вспышку.
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self._sync_topmost_state()
        self._update_chrome_visibility()
        QTimer.singleShot(50, self._sync_topmost_state)
        self._apply_output_volume()
        self._refresh_hint()
        self._register_hotkeys()
        if not self._click_through:
            self._repair_video_surface()
        self._apply_stage_opacity()
        if not self._click_through:
            self.status.setText(
                "Полное окно · плотность снизу · Ctrl+O — сквозь · Ctrl+Shift+O — скрыть"
            )
        self._arm_auto_density_timer()

    def _enter_catalog(self) -> None:
        """Вернуть каталог; воспроизведение не стопаем."""
        self._stop_auto_density_timer(exit_ct_if_armed=True)
        if not self._stage_mode:
            self._apply_catalog_opacity()
            return
        if self._click_through:
            self._set_click_through(False)
        # Сначала плотный тёмный кадр, потом showNormal — меньше «дыры» в рабочий стол.
        self.setWindowOpacity(1.0)
        self.setUpdatesEnabled(False)
        try:
            self._stage_mode = False
            self.showNormal()
            if self._normal_geometry is not None:
                self.setGeometry(self._normal_geometry)
            else:
                self.resize(1100, 640)
            self.list.setMaximumWidth(16777215)
            self.list.show()
            restore = self._splitter_sizes or [320, 740]
            self._splitter.setSizes(restore)
            self._update_chrome_visibility()
            self._apply_catalog_opacity()
            self._apply_output_volume()
            self._refresh_hint()
        finally:
            self.setUpdatesEnabled(True)
        self.raise_()
        self.activateWindow()
        self._sync_topmost_state()
        self._register_hotkeys()
        self.status.setText(
            "Каталог · клик по кадру — play/pause · 2× — полный экран · трек: клик — play"
        )

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
        self._hold_stage_opacity = False
        self._force_catalog_sound = False
        if self._player is not None:
            self._player.stop()
        self._set_play_icon(False)
        self.pulse.stop()
        self._playing = False
        self._seek_dragging = False
        self.seek_slider.setValue(0)
        self._update_time_label(0, self.seek_slider.maximum())
        self._apply_catalog_opacity()
        self._refresh_playing_highlight()

    @staticmethod
    def _fmt_ms(ms: int) -> str:
        sec = max(0, int(ms) // 1000)
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _update_time_label(self, pos_ms: int, dur_ms: int) -> None:
        self.time_label.setText(f"{self._fmt_ms(pos_ms)} / {self._fmt_ms(dur_ms)}")

    def _on_duration(self, duration_ms: int) -> None:
        if not hasattr(self, "seek_slider"):
            return
        dur = max(0, int(duration_ms))
        self.seek_slider.setRange(0, dur)
        if not self._seek_dragging and self._player is not None:
            self._update_time_label(int(self._player.position()), dur)

    def _on_position(self, position_ms: int) -> None:
        if self._seek_dragging or not hasattr(self, "seek_slider"):
            return
        pos = max(0, int(position_ms))
        self.seek_slider.blockSignals(True)
        self.seek_slider.setValue(pos)
        self.seek_slider.blockSignals(False)
        self._update_time_label(pos, self.seek_slider.maximum())

    def _on_seek_pressed(self) -> None:
        self._seek_dragging = True

    def _on_seek_moved(self, value: int) -> None:
        self._update_time_label(int(value), self.seek_slider.maximum())

    def _on_seek_released(self) -> None:
        self._seek_dragging = False
        if self._player is not None:
            self._player.setPosition(int(self.seek_slider.value()))

    def _seek_by(self, delta_ms: int) -> None:
        if self._player is None:
            return
        pos = max(0, int(self._player.position()) + delta_ms)
        dur = int(self._player.duration())
        if dur > 0:
            pos = min(pos, dur)
        self._player.setPosition(pos)

    def _nudge_volume(self, delta: int) -> None:
        before = self.volume_slider.value()
        self.volume_slider.setValue(max(0, min(100, before + delta)))

    def _on_playback_state(self, state) -> None:
        if not _HAS_MULTIMEDIA:
            return
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._hold_stage_opacity = False
            self._set_play_icon(True)
            was = self._playing
            self._playing = True
            if self._stage_mode:
                self._apply_stage_opacity()
            else:
                self._apply_catalog_opacity()
            self._apply_output_volume()
            if not was:
                # Подцепить VK_MEDIA_* пока играет
                QTimer.singleShot(0, self._register_hotkeys)
            self._arm_auto_density_timer()
        else:
            self._set_play_icon(False)
            if state == QMediaPlayer.PlaybackState.StoppedState:
                self.pulse.stop()
                self._playing = False
                self._stop_auto_density_timer(exit_ct_if_armed=True)
                # Смена трека: Stopped → Playing. Не вспыхивать 100%.
                if self._hold_stage_opacity and self._stage_mode:
                    self._apply_stage_opacity()
                else:
                    self._apply_catalog_opacity()
                if not self._hold_stage_opacity:
                    QTimer.singleShot(0, self._register_hotkeys)
            elif state == QMediaPlayer.PlaybackState.PausedState:
                self._playing = True
                self._stop_auto_density_timer(exit_ct_if_armed=False)
                if not self._stage_mode:
                    self._apply_catalog_opacity()
                self._set_play_icon(False)
        self._refresh_playing_highlight()

    def _on_media_status(self, status) -> None:
        if not _HAS_MULTIMEDIA or self._player is None:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._play_next()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.status.setText("InvalidMedia — кодек/файл не открылся")
            self.pulse.stop()
            self._playing = False
            self._hold_stage_opacity = False
            self._apply_catalog_opacity()
            self._refresh_playing_highlight()

    def _on_player_error(self, *_args) -> None:
        if self._player is None:
            return
        self.status.setText(f"Ошибка: {self._player.errorString() or 'playback'}")
        self.pulse.stop()
        self._playing = False
        self._hold_stage_opacity = False
        self._apply_catalog_opacity()

    def _on_volume(self, value: int) -> None:
        if self._audio is not None:
            # слайдер = желаемая громкость; mute превью учитывается отдельно
            silent_preview = (
                not self._stage_mode
                and not self._prefs.get("preview_sound", True)
                and not self._force_catalog_sound
            )
            if silent_preview:
                self._audio.setVolume(0.0)
            else:
                self._audio.setVolume(max(0.0, min(1.0, value / 100.0)))

    def _on_opacity(self, value: int) -> None:
        """Живой preview; prefs на диск — debounce / отпускание (иначе лаг на каждом тике)."""
        self._prefs["stage_opacity"] = int(value)
        if hasattr(self, "opacity_value"):
            self.opacity_value.setText(f"{int(value)}%")
        if self._stage_mode:
            self._apply_stage_opacity()
        else:
            # Каталог всегда плотный — слайдер только запоминает значение для fullscreen
            self._apply_catalog_opacity()
        self._schedule_opacity_save()

    def _schedule_opacity_save(self) -> None:
        if not hasattr(self, "_opacity_save_timer"):
            self._opacity_save_timer = QTimer(self)
            self._opacity_save_timer.setSingleShot(True)
            self._opacity_save_timer.timeout.connect(self._flush_opacity_prefs)
        self._opacity_save_timer.start(400)

    def _flush_opacity_prefs(self) -> None:
        if not hasattr(self, "opacity_slider"):
            return
        val = int(self.opacity_slider.value())
        self._prefs["stage_opacity"] = val
        save_overlay_prefs(stage_opacity=val)

    def _apply_catalog_opacity(self) -> None:
        self.setWindowOpacity(1.0)
        self._write_root_exstyle()

    def _apply_stage_opacity(self) -> None:
        """Плотность <100% только со сквозь. Без сквозь всегда 100% — иначе стекло жрёт клики YouTube/Cursor."""
        if not self._click_through:
            self.setWindowOpacity(1.0)
        else:
            val = self.opacity_slider.value()
            self.setWindowOpacity(max(_OPACITY_MIN / 100.0, min(1.0, val / 100.0)))
        self._sync_density_enabled()

    def _chrome_is_detached(self) -> bool:
        return False

    def _detach_chrome_for_stage(self) -> None:
        """Панель в том же окне. Ctrl+O — спрятать управление (только видео)."""
        if self._click_through:
            self._hide_stage_controls()
            return
        self.hide_btn.show()
        if hasattr(self, "density_bar"):
            self.density_bar.show()
        if hasattr(self, "chrome_actions"):
            self.chrome_actions.show()
        self.catalog_btn.show()
        self.transport_bar.show()
        self.chrome_bottom.show()

    def _hide_stage_controls(self) -> None:
        self.chrome_top.hide()
        self.transport_bar.hide()
        self.chrome_bottom.hide()
        self.hint.hide()
        self.catalog_btn.hide()
        self.hide_btn.hide()
        if hasattr(self, "density_bar"):
            self.density_bar.hide()
        if hasattr(self, "chrome_actions"):
            self.chrome_actions.hide()
        lay = self.layout()
        if lay is not None:
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)

    def _attach_chrome_to_main(self) -> None:
        self.hide_btn.hide()
        if hasattr(self, "density_bar"):
            self.density_bar.hide()
        self.transport_bar.show()
        self.chrome_bottom.show()

    def _sync_chrome_host_geometry(self) -> None:
        return

    def _force_topmost_widget(self, widget: QWidget, *, topmost: bool = True) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = int(widget.winId())
        except Exception:
            return
        HWND_TOPMOST = ctypes.c_void_p(-1)
        HWND_NOTOPMOST = ctypes.c_void_p(-2)
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        ctypes.windll.user32.SetWindowPos(
            ctypes.c_void_p(hwnd),
            HWND_TOPMOST if topmost else HWND_NOTOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _sync_topmost_state(self) -> None:
        """Topmost только в полном окне. Каталог — обычный z-order."""
        want = bool(self._stage_mode)
        self._force_topmost_widget(self, topmost=want)

    def _update_ct_label(self) -> None:
        if self._click_through:
            self.ct_label.setText("Сквозь: вкл")
            self.ct_label.setProperty("ctOn", True)
        else:
            self.ct_label.setText("Сквозь: выкл")
            self.ct_label.setProperty("ctOn", False)
        self.ct_label.style().unpolish(self.ct_label)
        self.ct_label.style().polish(self.ct_label)
        self._sync_density_enabled()

    def _sync_density_enabled(self) -> None:
        """Слайдер всегда крутится (запоминает %). Живое стекло — только в сквозь."""
        if not hasattr(self, "opacity_slider"):
            return
        self.opacity_slider.setEnabled(bool(self._stage_mode))
        self.opacity_caption.setText("Плотность")
        if not self._stage_mode:
            self.opacity_value.setText("100%")
            self.opacity_value.setToolTip("В каталоге всегда 100%.")
            return
        if self._click_through:
            self.opacity_value.setText(f"{self.opacity_slider.value()}%")
            self.opacity_value.setToolTip("Сейчас применено (сквозь).")
        else:
            self.opacity_value.setText(f"{self.opacity_slider.value()}%→")
            self.opacity_value.setToolTip(
                "Без сквозь окно 100%. Это значение включится по Ctrl+O."
            )

    def _update_chrome_visibility(self) -> None:
        """Каталог / сцена: одна панель в том же окне (без второго HWND)."""
        lay = self.layout()
        if self._click_through:
            self._hide_stage_controls()
            return
        if self._stage_mode:
            self.chrome_top.hide()
            self.hint.hide()
            self.catalog_btn.show()
            if hasattr(self, "density_bar"):
                self.density_bar.show()
            if hasattr(self, "hide_btn"):
                self.hide_btn.show()
            if lay is not None:
                lay.setContentsMargins(0, 0, 0, 0)
                lay.setSpacing(0)
            if hasattr(self, "chrome_actions"):
                self.chrome_actions.show()
            self._detach_chrome_for_stage()
            self._sync_density_enabled()
        else:
            self._attach_chrome_to_main()
            self.chrome_top.show()
            self.chrome_bottom.show()
            self.hint.show()
            self.catalog_btn.hide()
            if hasattr(self, "density_bar"):
                self.density_bar.hide()
            if hasattr(self, "hide_btn"):
                self.hide_btn.hide()
            if hasattr(self, "chrome_actions"):
                self.chrome_actions.hide()
            if lay is not None:
                lay.setContentsMargins(8, 8, 8, 8)
                lay.setSpacing(6)
            self.setWindowOpacity(1.0)

    def _force_topmost(self) -> None:
        """Совместимость: делегирует в _sync_topmost_state."""
        self._sync_topmost_state()

    def _set_click_through(self, enabled: bool) -> None:
        if sys.platform != "win32":
            self.status.setText("Click-through только на Windows")
            return
        if not enabled:
            self._auto_density_armed = False
            self._auto_density_timer.stop()
        self._click_through = bool(enabled)
        self._apply_exstyle()
        self._update_ct_label()
        self._update_chrome_visibility()
        if enabled:
            # Fail-safe: без WS_EX_TRANSPARENT получится невидимый щит кликов
            try:
                hwnd = int(self.winId())
                get_long, _set_long = _win_long_fns()
                st = int(get_long(hwnd, GWL_EXSTYLE))
                if not (st & WS_EX_TRANSPARENT):
                    self._click_through = False
                    self._auto_density_armed = False
                    self._apply_exstyle()
                    self._update_ct_label()
                    self._update_chrome_visibility()
                    self.hide()
                    self.status.setText("Сквозь не применился — окно скрыто (защита кликов)")
                    return
            except Exception:
                pass
            if self._stage_mode:
                # Ручной сквозь: если плотность высокая — ужать; авто уже выставил %
                if not self._auto_density_armed and self.opacity_slider.value() > 55:
                    self.opacity_slider.blockSignals(True)
                    self.opacity_slider.setValue(40)
                    self.opacity_slider.blockSignals(False)
                    if hasattr(self, "opacity_value"):
                        self.opacity_value.setText("40%")
                self._apply_stage_opacity()
                if not self._auto_density_armed:
                    self.status.setText(
                        "Сквозь · UI скрыт · Ctrl+O — вернуть · Ctrl+[ / ] плотность · Ctrl+Shift+O — скрыть"
                    )
                self._register_hotkeys()
            self._sync_topmost_state()
            QTimer.singleShot(50, self._reapply_ct_children)
            QTimer.singleShot(50, self._sync_topmost_state)
        else:
            if self._stage_mode:
                self._apply_stage_opacity()
                self.status.setText("Сквозь выкл · плотность после Ctrl+O · Ctrl+Shift+O — скрыть")
                self._register_hotkeys()
                self._arm_auto_density_timer()
            else:
                self._apply_catalog_opacity()
                self.status.setText("Сквозь выкл")
            self._sync_topmost_state()
            self._write_root_exstyle()
            if self._stage_mode:
                self._detach_chrome_for_stage()
            QTimer.singleShot(0, self._repair_video_surface)
            QTimer.singleShot(50, self._sync_topmost_state)

    def _reapply_ct_children(self) -> None:
        if not self._click_through or sys.platform != "win32":
            return
        try:
            self._set_video_input_enabled(False)
        except Exception:
            pass

    def _toggle_click_through(self) -> None:
        self._set_click_through(not self._click_through)

    def _hide_keep_music(self) -> None:
        """Спрятать Фон, музыка играет. Сначала hide — не снимать сквозь на видимом окне (чёрная дыра кликов)."""
        was_ct = bool(self._click_through)
        self._click_through = False
        self.hide()
        # Пока скрыты — почистить TRANSPARENT / EnableWindow, без activate/show
        QTimer.singleShot(0, lambda: self._sanitize_after_hide(was_ct))
        # Не emit hidden_keep: иначе Translator вылезает поверх Cursor.

    def _sanitize_after_hide(self, was_ct: bool) -> None:
        """Убрать залипший click-through со скрытого окна — иначе клики/клава в других приложениях мертвы."""
        if sys.platform != "win32":
            return
        try:
            self._update_ct_label()
            self._write_root_exstyle()
            self._set_video_input_enabled(True)
            for w in (self.media_stack, self.video, self.pulse, self.video_column):
                try:
                    w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
                except Exception:
                    pass
            if was_ct:
                hwnd = int(self.winId()) if self.winId() else 0
                if hwnd:
                    self._clear_child_transparent_styles(hwnd)
        except Exception:
            pass

    def present_visible(self) -> None:
        """Кнопка «Фон» / повторный show: каталог на экране, не невидимый leftover."""
        if self._click_through:
            self._set_click_through(False)
        if self._stage_mode:
            self._enter_catalog()
        self.showNormal()
        if self._normal_geometry is not None:
            self.setGeometry(self._normal_geometry)
        else:
            self.resize(1100, 640)
        self.raise_()
        self.activateWindow()

    def _toggle_hide_or_show(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self._hide_keep_music()
            return
        self.show()
        if self._stage_mode:
            self.showFullScreen()
        self.raise_()
        self.activateWindow()
        if self._click_through:
            self._set_click_through(False)
        elif self._stage_mode:
            self._update_chrome_visibility()
            self._apply_stage_opacity()
            self._sync_topmost_state()
            self._set_video_input_enabled(True)
            QTimer.singleShot(0, self._repair_video_surface)

    def _write_root_exstyle(self) -> None:
        """Сквозь: LAYERED+TRANSPARENT. Иначе не форсить LAYERED — иначе окно невидимо."""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        if not hwnd:
            return
        get_long, set_long = _win_long_fns()
        cur = int(get_long(hwnd, GWL_EXSTYLE))
        if (self._base_exstyle is None or self._base_exstyle == 0) and (cur & ~WS_EX_TRANSPARENT):
            self._base_exstyle = cur & ~WS_EX_TRANSPARENT
        if self._click_through:
            style = (cur | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        else:
            style = cur & ~WS_EX_TRANSPARENT
        if self._stage_mode:
            style |= WS_EX_TOPMOST
        else:
            style &= ~WS_EX_TOPMOST
        set_long(hwnd, GWL_EXSTYLE, style)
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        SWP_FRAMECHANGED = 0x0020
        after = ctypes.c_void_p(-1) if self._stage_mode else ctypes.c_void_p(-2)
        ctypes.windll.user32.SetWindowPos(
            ctypes.c_void_p(hwnd),
            after,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )

    def _apply_exstyle(self) -> None:
        if sys.platform != "win32":
            return
        hwnd = int(self.winId())
        self._write_root_exstyle()
        # Не WS_EX_TRANSPARENT на children (убивает QVideoWidget).
        # Клики с video: EnableWindow(False) — рисует, но не принимает мышь.
        self._clear_child_transparent_styles(hwnd)
        self._set_video_input_enabled(not self._click_through)
        for w in (self.media_stack, self.video, self.pulse, self.video_column):
            try:
                w.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                    self._click_through,
                )
            except Exception:
                pass
        if not self._click_through:
            self._repair_video_surface()
        if self._stage_mode:
            self._apply_stage_opacity()
        else:
            self._apply_catalog_opacity()
        self._write_root_exstyle()

    def _clear_child_transparent_styles(self, root_hwnd: int) -> None:
        """Снять залипший TRANSPARENT/LAYERED с children (не ставить заново)."""
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        get_long, set_long = _win_long_fns()
        from ctypes import wintypes

        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        @EnumProc
        def _enum(h, _lp):  # type: ignore[misc]
            try:
                st = int(get_long(h, GWL_EXSTYLE))
                if st & (WS_EX_TRANSPARENT | WS_EX_LAYERED):
                    st &= ~WS_EX_TRANSPARENT
                    st &= ~WS_EX_LAYERED
                    set_long(h, GWL_EXSTYLE, st)
            except Exception:
                pass
            return True

        user32.EnumChildWindows(root_hwnd, _enum, 0)

    def _set_video_input_enabled(self, enabled: bool) -> None:
        """R1: EnableWindow на QVideoWidget и его детях — без WS_EX_TRANSPARENT."""
        if sys.platform != "win32":
            return
        if not hasattr(self, "video") or self.video is None:
            return
        try:
            if not self.video.winId():
                return
            root = int(self.video.winId())
        except Exception:
            return
        user32 = ctypes.windll.user32
        from ctypes import wintypes

        targets: list[int] = [root]
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        @EnumProc
        def _enum(h, _lp):  # type: ignore[misc]
            targets.append(int(h))
            return True

        user32.EnumChildWindows(root, _enum, 0)
        for h in targets:
            try:
                user32.EnableWindow(h, bool(enabled))
            except Exception:
                pass

    def _repair_video_surface(self) -> None:
        """После CT/hide: снять залипшие стили, EnableWindow(True). Без pause/play."""
        if sys.platform != "win32":
            return
        if self._click_through:
            return
        try:
            root = int(self.winId()) if self.winId() else 0
            if root:
                self._clear_child_transparent_styles(root)
                self._set_video_input_enabled(True)
        except Exception:
            pass

    def _open_settings(self) -> None:
        # P6: пауза перед модальным диалогом
        was_playing = False
        if self._player is not None:
            was_playing = (
                self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            if was_playing:
                self._player.pause()
        QApplication.processEvents()
        # Иначе RegisterHotKey съедает Ctrl+Shift+1 и поле не видит комбо
        self._unregister_hotkeys()
        try:
            dlg = OverlaySettingsDialog(self._prefs, self)
            accepted = dlg.exec() == QDialog.DialogCode.Accepted
            if accepted:
                updates = dlg.result_prefs()
                self._prefs = save_overlay_prefs(**updates)
                if "volume" in updates:
                    self.volume_slider.blockSignals(True)
                    self.volume_slider.setValue(int(updates["volume"]))
                    self.volume_slider.blockSignals(False)
                self._refresh_hint()
                self._install_shortcuts()
                self._apply_output_volume()
                self.status.setText("Настройки сохранены")
        finally:
            self._register_hotkeys()
        if was_playing and self._player is not None and self._prefs.get("play_when_hidden", True):
            # не авто-resume если юзер сам на паузе ради настроек — resume ок
            self._player.play()

    def _on_escape(self) -> None:
        """Esc: 1) выкл сквозь + вернуть панель; 2) из fullscreen → каталог."""
        if self._click_through:
            self._set_click_through(False)
            return
        if self._stage_mode:
            self._enter_catalog()
            return
        self._apply_catalog_opacity()
        if hasattr(self, "status") and self.status.isVisible():
            self.status.setText("Каталог · Esc — ок")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.isAutoRepeat():
            return super().keyPressEvent(event)
        if event.key() == Qt.Key.Key_Escape:
            self._on_escape()
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._reload_list()
        if not self._app_filter_installed:
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
                self._app_filter_installed = True
        QTimer.singleShot(0, self._apply_exstyle)
        QTimer.singleShot(0, self._sync_topmost_state)
        QTimer.singleShot(0, self._register_hotkeys)
        QTimer.singleShot(0, self._install_shortcuts)

    def hideEvent(self, event) -> None:  # noqa: N802
        # Не стопаем музыку. В скрытом режиме оставляем только AIMP-style
        # транспорт/громкость + show/hide, без Ctrl+O/плотности/перемотки.
        super().hideEvent(event)
        self._register_hotkeys(hidden_only=True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_chrome_host_geometry()

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._sync_chrome_host_geometry()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop()
        self._unregister_hotkeys()
        try:
            self._attach_chrome_to_main()
        except Exception:
            pass
        self.closed.emit()
        super().closeEvent(event)

    def _register_hotkeys(self, *, hidden_only: bool = False, _retry: int = 0) -> None:
        if sys.platform != "win32":
            return
        # Не рвём поток, пока старый не отпустил RegisterHotKey (иначе 1409 на части клавиш).
        if not self._unregister_hotkeys():
            if _retry < 8:
                QTimer.singleShot(150, lambda: self._register_hotkeys(hidden_only=hidden_only, _retry=_retry + 1))
            return
        hk = self._prefs.get("hotkeys") or _DEFAULT_HOTKEYS
        priority = [
            (_HOTKEY_HIDE, hk.get("hide_show", "Ctrl+Shift+O")),
            (_HOTKEY_NEXT, hk.get("next_track", "Ctrl+Shift+1")),
            (_HOTKEY_PREV, hk.get("prev_track", "Ctrl+Shift+2")),
            (_HOTKEY_STOP, hk.get("stop_track", "Ctrl+Shift+F1")),
            (_HOTKEY_VOL_UP, hk.get("vol_up", "Ctrl+Up")),
            (_HOTKEY_VOL_DOWN, hk.get("vol_down", "Ctrl+Down")),
            (_HOTKEY_SEEK_BACK, hk.get("seek_back", "Ctrl+Left")),
            (_HOTKEY_SEEK_FWD, hk.get("seek_fwd", "Ctrl+Right")),
        ]
        if not hidden_only and self._stage_mode:
            # Сквозь: окно не получает клавиши — Ctrl+O и плотность глобально.
            priority.append((_HOTKEY_CLICK, hk.get("click_through", "Ctrl+O")))
            priority.append((_HOTKEY_OPACITY_UP, hk.get("opacity_up", "Ctrl+]")))
            priority.append((_HOTKEY_OPACITY_DOWN, hk.get("opacity_down", "Ctrl+[")))
        # Тест наушников: play/pause/next/prev — только пока Фон играет или в stage
        # (чтобы меньше драться с YouTube, когда overlay просто открыт в каталоге).
        media_entries: list[tuple[int, str, int, int]] = []
        if self._playing or self._stage_mode:
            media_entries = [
                (_HOTKEY_MEDIA_PLAY, "MediaPlayPause", MOD_NOREPEAT, VK_MEDIA_PLAY_PAUSE),
                (_HOTKEY_MEDIA_NEXT, "MediaNext", MOD_NOREPEAT, VK_MEDIA_NEXT_TRACK),
                (_HOTKEY_MEDIA_PREV, "MediaPrev", MOD_NOREPEAT, VK_MEDIA_PREV_TRACK),
            ]
        entries = []
        seen_vk: set[tuple[int, int]] = set()
        for hk_id, spec in priority:
            parsed = _parse_hotkey(spec, allow_repeat=(hk_id in _REPEATABLE_HOTKEY_IDS))
            if not parsed:
                continue
            mods, vk = parsed
            # Одиночные клавиши (Esc/Space) глобально не регистрируем — кроме media_* ниже.
            if (mods & ~MOD_NOREPEAT) == 0 and hk_id not in _MEDIA_HOTKEY_IDS:
                continue
            key = (int(mods), int(vk))
            if key in seen_vk:
                continue
            seen_vk.add(key)
            entries.append((int(hk_id), str(spec), int(mods), int(vk)))
        for hk_id, spec, mods, vk in media_entries:
            key = (int(mods), int(vk))
            if key in seen_vk:
                continue
            seen_vk.add(key)
            entries.append((int(hk_id), str(spec), int(mods), int(vk)))
        if entries:
            self._start_hotkey_thread(entries, hidden_only=hidden_only, conflict_retry=_retry)

    def _unregister_hotkeys(self, *, full: bool = True) -> bool:
        """False = старый поток ещё жив — не стартовать новый."""
        ok = self._stop_hotkey_thread()
        self._hotkeys_registered.clear()
        return ok

    def _start_hotkey_thread(
        self,
        entries: list[tuple[int, str, int, int]],
        *,
        hidden_only: bool,
        conflict_retry: int = 0,
    ) -> None:
        stop = threading.Event()
        self._hotkey_stop = stop
        failed_specs: list[str] = []

        def _worker() -> None:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            tid = int(kernel32.GetCurrentThreadId())
            self._hotkey_thread_id = tid
            msg = ctypes.wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
            registered: list[int] = []
            local_failed: list[str] = []
            for hk_id, spec, mods, vk in entries:
                kernel32.SetLastError(0)
                ok = bool(user32.RegisterHotKey(None, hk_id, mods, vk))
                if ok:
                    registered.append(hk_id)
                else:
                    local_failed.append(spec)
            self._hotkeys_registered = set(registered)
            failed_specs.extend(local_failed)
            while not stop.is_set():
                res = int(user32.GetMessageW(ctypes.byref(msg), None, 0, 0))
                if res <= 0 or stop.is_set():
                    break
                if int(msg.message) == WM_HOTKEY:
                    hotkey_id = int(msg.wParam)
                    self.hotkey_pressed.emit(hotkey_id)
            for hk_id in registered:
                try:
                    user32.UnregisterHotKey(None, hk_id)
                except Exception:
                    pass

        self._hotkey_thread = threading.Thread(target=_worker, name="overlay-hotkeys", daemon=True)
        self._hotkey_thread.start()

        def _after_reg() -> None:
            if failed_specs:
                uniq = ", ".join(dict.fromkeys(failed_specs))
                try:
                    self.status.setText(f"Хоткей занят (другое приложение): {uniq}")
                except Exception:
                    pass
                if conflict_retry >= 1 or self._hk_retry_pending:
                    return
                self._hk_retry_pending = True

                def _retry() -> None:
                    self._hk_retry_pending = False
                    self._register_hotkeys(hidden_only=hidden_only, _retry=conflict_retry + 1)

                QTimer.singleShot(400, _retry)
                return
            # Успех: если подхватили media — короткий статус (тест)
            if self._hotkeys_registered & _MEDIA_HOTKEY_IDS:
                try:
                    self.status.setText("Тест: наушники play/next/prev → Фон (пока играет)")
                except Exception:
                    pass

        QTimer.singleShot(120, _after_reg)

    def _stop_hotkey_thread(self) -> bool:
        stop = self._hotkey_stop
        thread = self._hotkey_thread
        tid = self._hotkey_thread_id
        if stop is not None:
            stop.set()
        if tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(int(tid), 0x0012, 0, 0)
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
            if thread.is_alive():
                return False
        self._hotkey_thread = None
        self._hotkey_stop = None
        self._hotkey_thread_id = None
        return True

    def _on_global_hotkey(self, hotkey_id: int) -> None:
        now = time.monotonic()
        # Seek/громкость/плотность — зажатие; остальное антидребезг
        gap = 0.02 if hotkey_id in _REPEATABLE_HOTKEY_IDS else 0.08
        if self._last_hk_id == hotkey_id and (now - self._last_hk_t) < gap:
            return
        self._last_hk_id = hotkey_id
        self._last_hk_t = now
        if hotkey_id == _HOTKEY_HIDE:
            self._toggle_hide_or_show()
            return
        if hotkey_id == _HOTKEY_CLICK:
            if not self._stage_mode:
                return
            if not self.isVisible():
                self.show()
                if self._stage_mode:
                    self.showFullScreen()
                self.raise_()
            self._toggle_click_through()
            return
        if hotkey_id in (_HOTKEY_NEXT, _HOTKEY_MEDIA_NEXT):
            self._play_next()
            return
        if hotkey_id in (_HOTKEY_PREV, _HOTKEY_MEDIA_PREV):
            self._play_prev()
            return
        if hotkey_id in (_HOTKEY_STOP, _HOTKEY_MEDIA_PLAY):
            self._toggle_play()
            return
        if hotkey_id == _HOTKEY_SEEK_BACK:
            self._seek_by(-_SEEK_MS)
            return
        if hotkey_id == _HOTKEY_SEEK_FWD:
            self._seek_by(_SEEK_MS)
            return
        if hotkey_id == _HOTKEY_VOL_UP:
            self._nudge_volume(_VOLUME_STEP)
            return
        if hotkey_id == _HOTKEY_VOL_DOWN:
            self._nudge_volume(-_VOLUME_STEP)
            return
        if hotkey_id == _HOTKEY_OPACITY_UP:
            if self._stage_mode:
                self._nudge_opacity(_OPACITY_STEP)
            return
        if hotkey_id == _HOTKEY_OPACITY_DOWN:
            if self._stage_mode:
                self._nudge_opacity(-_OPACITY_STEP)
            return
        if hotkey_id == _HOTKEY_ESC:
            self._on_escape()
            return


_OVERLAY_WINDOW_TITLE = "Фон — overlay (IDEA-022)"
_overlay_singleton: OverlayPlayerWindow | None = None


def _find_overlay_hwnd() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(ctypes.windll.user32.FindWindowW(None, _OVERLAY_WINDOW_TITLE) or 0)
    except Exception:
        return 0


def _bring_overlay_hwnd(hwnd: int) -> None:
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)


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
            _overlay_singleton.present_visible()
            return _overlay_singleton
        except RuntimeError:
            _overlay_singleton = None

    existing = _find_overlay_hwnd()
    if existing:
        _bring_overlay_hwnd(existing)
        return _overlay_singleton

    win = OverlayPlayerWindow(start_dir=start_dir, parent=None)
    win.closed.connect(_clear_singleton)
    _overlay_singleton = win
    win.present_visible()
    return win


def close_overlay_player() -> None:
    global _overlay_singleton
    if _overlay_singleton is not None:
        try:
            _overlay_singleton.close()
        except RuntimeError:
            pass
        _overlay_singleton = None


def _clear_singleton() -> None:
    global _overlay_singleton
    _overlay_singleton = None


if __name__ == "__main__":
    existing = _find_overlay_hwnd()
    if existing:
        _bring_overlay_hwnd(existing)
        sys.exit(0)
    app = QApplication(sys.argv)
    open_overlay_player()
    sys.exit(app.exec())
