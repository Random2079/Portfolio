"""
YouTube Subtitle Ripper — GUI (CustomTkinter) + yt-dlp.

КАРТА ФАЙЛА (читай отсюда, не весь код ):
  вход:  ссылка YouTube + язык RU/EN
  выход: папка dist/субтитры_<title> [id]/
         0_весь_текст_для_буфера.txt  — чистый текст (+ Ctrl+V)
         1_текст_с_таймкодами.txt     — [mm:ss] фраза
         player.html                  — iframe + кнопки таймкодов
         часть_xx_N.txt               — куски, если текст огромный

БЛОКИ:
  1.  имена / метаданные yt-dlp     — id, title, auto vs manual субы
  1b. разбор SRT                   — сегменты → склейка → plain / timed
  2.  download_and_split           — весь пайплайн скачивания (мозг)
  2b. download_audio               — MP3 через yt-dlp (Music/YouTube_DL)
  2c. overlay_player (IDEA-022)    — фон: каталог mp3/mp4, opacity, click-through
  2d. dist files (IDEA-021 F0)     — список dist/субтитры_* + открыть в проводнике
  3.  SubtitleApp                  — окно, кнопки, поток, буфер
  4.  __main__                     — GUI или CLI: python Subtitle_App.py URL lang

Функции: не учить «как внутри». Достаточно docstring «что делает».
Имена с _ в начале — внутренние хелперы, в UI не зовутся.
"""
from __future__ import annotations

import html
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QByteArray, QEvent, QObject, QSize, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPixmap,
    QShortcut,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ui_motion import BusyPulse, attach_many

from ai_analyze import (  # DeepSeek — без доп. зависимостей
    AnalyzeCancelled,
    analyze_subtitles,
    load_saved_analysis,
)
from overlay_player import close_overlay_player, open_overlay_player
from timecode_player import PLAYER_FILENAME, load_player_data, write_player_html

StatusCb = Callable[[str], None]


class DownloadCancelled(Exception):
    """yt-dlp прерван пользователем (кнопка «Отмена»)."""

# Локальный HTTP для player.html (YouTube API с file:// часто молчит)
_player_httpd: ThreadingHTTPServer | None = None
_player_httpd_folder: str | None = None
_player_httpd_lock = threading.Lock()
# Живые yt-dlp/ffmpeg от скачиваний — гасим при закрытии окна
_active_child_procs: set[subprocess.Popen] = set()
_active_child_lock = threading.Lock()
# Windows: не индексировать (SearchIndexer / «Поиск»)
_FILE_ATTR_NOT_CONTENT_INDEXED = 0x2000


# =====================================================================
# 1. ВАЛИДАТОР И ИМЕНА
# =====================================================================
# Стандартный YouTube video id: 11 символов [A-Za-z0-9_-]
_YOUTUBE_ID_RE = re.compile(
    r"(?:v=|/shorts/|/live/|/embed/|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def get_video_id(url: str) -> str | None:
    """Достаёт ID ролика из ссылки YouTube (или None, если ссылка кривая)."""
    match = _YOUTUBE_ID_RE.search(url)
    return match.group(1) if match else None


def sanitize_filename(name: str) -> str:
    """Чистит название под имя папки Windows (без \\ / : * ? и т.п.)."""
    name = name.replace("\ufffd", "")
    name = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "Без названия"


def _lang_available(tracks: dict | None, lang_code: str) -> bool:
    """Есть ли дорожка языка (ru / ru-RU / en / en-US …)."""
    return resolve_lang_key(tracks, lang_code) is not None


def resolve_lang_key(tracks: dict | None, lang_code: str) -> str | None:
    """Точный ключ дорожки в meta yt-dlp (ru → ru или ru-RU)."""
    if not tracks or not isinstance(tracks, dict):
        return None
    if lang_code in tracks:
        return lang_code
    prefix = lang_code + "-"
    for key in tracks:
        if key.startswith(prefix):
            return key
    return None


def resolve_subtitle_track(meta: dict, lang_code: str) -> tuple[str, str] | None:
    """
    Что качать: (mode, yt_lang_key) или None.
    mode: auto | manual. yt_lang_key — как в JSON yt-dlp (для --sub-lang).
    Для выбранного языка: сначала обычные (manual), потом авто.
    """
    manual_key = resolve_lang_key(meta.get("subtitles"), lang_code)
    if manual_key:
        return "manual", manual_key
    auto_key = resolve_lang_key(meta.get("automatic_captions"), lang_code)
    if auto_key:
        return "auto", auto_key
    return None


def resolve_subtitle_track_with_fallback(
    meta: dict, preferred: str
) -> tuple[str, str, str] | None:
    """
    (mode, yt_lang_key, effective_lang) с запасными языками.

    en → en (manual/auto) → ru → любой доступный
    ru → ru (manual/auto) → en → любой доступный
    """
    preferred = (preferred or "ru").lower().strip()
    order = [preferred]
    if preferred == "en":
        order.append("ru")
    elif preferred == "ru":
        order.append("en")
    else:
        order.extend(["en", "ru"])

    seen: set[str] = set()
    for lang in order:
        if lang in seen:
            continue
        seen.add(lang)
        hit = resolve_subtitle_track(meta, lang)
        if hit:
            return hit[0], hit[1], lang

    # последний шанс: первая попавшаяся дорожка
    for bucket, mode in (
        ("subtitles", "manual"),
        ("automatic_captions", "auto"),
    ):
        tracks = meta.get(bucket)
        if not isinstance(tracks, dict) or not tracks:
            continue
        key = next(iter(tracks.keys()))
        base = str(key).split("-", 1)[0] or str(key)
        return mode, str(key), base
    return None


def pick_subtitle_mode(meta: dict, lang_code: str) -> str | None:
    """Обратная совместимость: только mode (auto/manual/None)."""
    resolved = resolve_subtitle_track(meta, lang_code)
    return resolved[0] if resolved else None


def _ytdlp_cookies_file() -> str | None:
    """Путь к Netscape cookies, если файл уже лежит в ~/.subtitle_ripper/."""
    folder = os.path.join(os.path.expanduser("~"), ".subtitle_ripper")
    if not os.path.isdir(folder):
        return None
    # Типичные имена экспорта («Get cookies.txt LOCALLY» и наше каноническое)
    candidates = [
        "youtube_cookies.txt",
        "www.youtube.com_cookies.txt",
        "cookies.txt",
    ]
    for name in candidates:
        path = os.path.join(folder, name)
        if os.path.isfile(path) and os.path.getsize(path) > 32:
            return path
    try:
        for name in sorted(os.listdir(folder)):
            low = name.lower()
            if not low.endswith(".txt"):
                continue
            if "cookie" not in low:
                continue
            path = os.path.join(folder, name)
            if os.path.isfile(path) and os.path.getsize(path) > 32:
                return path
    except OSError:
        return None
    return None


def _inspect_youtube_cookies(path: str | None) -> dict:
    """Метаданные Netscape-cookies без значений (для диагностики bot-check).

    Полноценный логин обычно даёт LOGIN_INFO и/или SID+SAPISID /
    __Secure-1PSID. Гостевой экспорт (VISITOR_* + пара __Secure-3*)
    yt-dlp принимает, но YouTube всё равно шлёт «confirm you're not a bot».
    """
    info: dict = {
        "path_name": None,
        "bytes": 0,
        "rows": 0,
        "has_login_info": False,
        "has_sid": False,
        "has_sapisid": False,
        "has_secure_1psid": False,
        "has_secure_3psid": False,
        "looks_logged_in": False,
    }
    if not path or not os.path.isfile(path):
        return info
    info["path_name"] = os.path.basename(path)
    try:
        info["bytes"] = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return info
    names: set[str] = set()
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) < 7:
            continue
        info["rows"] += 1
        names.add(parts[5])
    info["has_login_info"] = "LOGIN_INFO" in names
    info["has_sid"] = "SID" in names
    info["has_sapisid"] = "SAPISID" in names or "__Secure-3PAPISID" in names
    info["has_secure_1psid"] = "__Secure-1PSID" in names
    info["has_secure_3psid"] = "__Secure-3PSID" in names
    # Достаточно типичных маркеров аккаунта (не только visitor)
    info["looks_logged_in"] = bool(
        info["has_login_info"]
        or (info["has_sid"] and info["has_sapisid"])
        or (info["has_secure_1psid"] and info["has_secure_3psid"])
    )
    return info


def _mark_not_content_indexed(path: str) -> None:
    """Пометить путь «не индексировать» — меньше работы Search на OneDrive."""
    if os.name != "nt" or not path or not os.path.exists(path):
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        get_attrs = kernel32.GetFileAttributesW
        set_attrs = kernel32.SetFileAttributesW
        get_attrs.argtypes = [ctypes.c_wchar_p]
        get_attrs.restype = ctypes.c_uint32
        set_attrs.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        set_attrs.restype = ctypes.c_bool
        attrs = int(get_attrs(path))
        if attrs == 0xFFFFFFFF:
            return
        if attrs & _FILE_ATTR_NOT_CONTENT_INDEXED:
            return
        set_attrs(path, attrs | _FILE_ATTR_NOT_CONTENT_INDEXED)
    except Exception:
        pass


def webengine_data_root() -> str:
    """Профили Chromium вне OneDrive: %LOCALAPPDATA%\\SubtitleRipperPro.

    Иначе SearchIndexer + OneDrive синк жрут тысячи мелких файлов профиля
    при каждом старте WebEngine — «Поиск» в диспетчере и подвисания.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        root = os.path.join(base, "SubtitleRipperPro")
    else:
        root = os.path.join(os.path.expanduser("~"), ".cache", "SubtitleRipperPro")
    os.makedirs(root, exist_ok=True)
    _mark_not_content_indexed(root)
    return root


def webengine_profile_dir(name: str) -> str:
    """Каталог профиля WebEngine; один раз мигрирует со старого пути в project/."""
    dest = os.path.join(webengine_data_root(), name)
    legacy = os.path.join(app_install_dir(), name)
    if not os.path.isdir(dest) and os.path.isdir(legacy):
        try:
            shutil.move(legacy, dest)
        except OSError:
            try:
                shutil.copytree(legacy, dest, dirs_exist_ok=True)
            except OSError:
                pass
    os.makedirs(dest, exist_ok=True)
    _mark_not_content_indexed(dest)
    if os.path.isdir(legacy):
        _mark_not_content_indexed(legacy)
    return dest


def _yt_profile_cookie_db_paths() -> list[str]:
    """Файлы Cookies Chromium/Qt WebEngine в yt_profile."""
    root = webengine_profile_dir("yt_profile")
    return [
        os.path.join(root, "Cookies"),
        os.path.join(root, "Network", "Cookies"),
        os.path.join(root, "Default", "Cookies"),
        os.path.join(root, "Default", "Network", "Cookies"),
    ]


def _yt_profile_looks_logged_in() -> bool:
    """True, если в persistent WebView-профиле есть маркеры логина Google/YouTube."""
    markers = {
        "LOGIN_INFO",
        "SID",
        "SAPISID",
        "__Secure-1PSID",
        "__Secure-3PSID",
        "__Secure-3PAPISID",
    }
    found: set[str] = set()
    for path in _yt_profile_cookie_db_paths():
        if not os.path.isfile(path):
            continue
        try:
            # readonly URI — меньше шансов подраться с живым Chromium
            uri = path.replace("\\", "/")
            if os.name == "nt" and len(uri) >= 2 and uri[1] == ":":
                uri = "/" + uri
            conn = sqlite3.connect(f"file:{uri}?mode=ro", uri=True, timeout=0.3)
            try:
                rows = conn.execute(
                    "SELECT name FROM cookies WHERE host_key LIKE '%youtube%' "
                    "OR host_key LIKE '%google%' LIMIT 200"
                ).fetchall()
            finally:
                conn.close()
        except (sqlite3.Error, OSError):
            continue
        for (name,) in rows:
            if name in markers:
                found.add(name)
        if "LOGIN_INFO" in found:
            return True
        if "SID" in found and (
            "SAPISID" in found or "__Secure-3PAPISID" in found
        ):
            return True
        if "__Secure-1PSID" in found and "__Secure-3PSID" in found:
            return True
    return False


def _ytdlp_cookies_args() -> list[str]:
    """Cookies для обхода YouTube bot-check (VPN/VPS IP).

    На Windows Chrome/Edge 127+ cookies с app-bound encryption —
    `--cookies-from-browser chrome` обычно даёт Failed to decrypt DPAPI.
    Рабочий путь: Netscape-файл в ~/.subtitle_ripper/

    Приоритет:
    1) youtube_cookies.txt / www.youtube.com_cookies.txt / *cookie*.txt
    2) --cookies-from-browser только если задан SUBTITLE_RIPPER_COOKIES_BROWSER

    Выключить всё: SUBTITLE_RIPPER_NO_COOKIES=1
    """
    if os.environ.get("SUBTITLE_RIPPER_NO_COOKIES", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return []
    cookies_file = _ytdlp_cookies_file()
    if cookies_file:
        return ["--cookies", cookies_file]
    browser = os.environ.get("SUBTITLE_RIPPER_COOKIES_BROWSER", "").strip().lower()
    if browser:
        return ["--cookies-from-browser", browser]
    return []


def _ytdlp_js_runtime_args() -> list[str]:
    """YouTube в 2026 часто требует JS runtime (EJS), иначе субы/форматы пустые."""
    import shutil

    if shutil.which("deno"):
        return ["--js-runtimes", "deno"]
    if shutil.which("node"):
        return ["--js-runtimes", "node"]
    return []


def ytdlp_argv(*args: str) -> list[str]:
    """Команда yt-dlp без Scripts\\yt-dlp.exe.

    На Windows exe-обёртка в Scripts часто даёт WinError 5 (Access denied),
    а `python -m yt_dlp` работает. В frozen-сборке остаётся PATH-yt-dlp.
    """
    cookie = _ytdlp_cookies_args()
    js = _ytdlp_js_runtime_args()
    if getattr(sys, "frozen", False):
        return ["yt-dlp", *cookie, *js, *args]
    return [sys.executable, "-m", "yt_dlp", *cookie, *js, *args]


def build_meta_yt_dlp_cmd(url: str, extra: list[str] | None = None) -> list[str]:
    """Аргументы yt-dlp для meta (для пайплайна и тестов)."""
    return ytdlp_argv(
        "--dump-single-json",
        "--skip-download",
        "--ignore-no-formats-error",
        "--no-warnings",
        *(extra or []),
        "--",
        url,
    )


def _ytdlp_player_client_extra() -> list[str]:
    """Клиент yt-dlp для YouTube.

    С cookies: web/mweb требуют PO token для Subs → пустой .srt при живых auto maps.
    web_embedded не требует PO для субтитров (проверено runtime на jTJvyKZDFsY).
    Без cookies: android+web как раньше.
    """
    if _ytdlp_cookies_args():
        return ["--extractor-args", "youtube:player_client=web_embedded"]
    return ["--extractor-args", "youtube:player_client=android,web"]



def fetch_video_meta(
    url: str,
    creation_flags: int,
    status_cb: StatusCb | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Один проход yt-dlp: title + список субтитров (JSON UTF-8).

    При ConnectionReset / сбое API — до 3 попыток с разными player_client.
    С cookies не используем android (не поддерживает cookies).
    """
    if _ytdlp_cookies_args():
        attempts: list[list[str]] = [
            [
                "--socket-timeout",
                "20",
                "--extractor-args",
                "youtube:player_client=web_embedded",
            ],
            ["--socket-timeout", "20"],
            [
                "--socket-timeout",
                "20",
                "--extractor-args",
                "youtube:player_client=web",
            ],
            [
                "--socket-timeout",
                "25",
                "--extractor-args",
                "youtube:player_client=web,tv",
            ],
            [
                "--socket-timeout",
                "25",
                "--extractor-args",
                "youtube:player_client=mweb",
            ],
        ]
    else:
        attempts = [
            ["--socket-timeout", "20"],
            [
                "--socket-timeout",
                "20",
                "--extractor-args",
                "youtube:player_client=android",
            ],
            [
                "--socket-timeout",
                "25",
                "--extractor-args",
                "youtube:player_client=android,web",
            ],
            [
                "--socket-timeout",
                "25",
                "--extractor-args",
                "youtube:player_client=tv",
            ],
        ]
    last_exc: BaseException | None = None
    best_title_meta: dict | None = None
    # на попытку: socket-timeout + запас; суммарно не раздувать до 5 минут
    process_timeout = 55

    for attempt_i, extra in enumerate(attempts, start=1):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled()
        prefix = f"Статус: [1/3] метаданные — попытка {attempt_i}/{len(attempts)}"
        _emit(status_cb, f"{prefix}…")
        cmd = build_meta_yt_dlp_cmd(url, extra)
        try:
            result = _run_ytdlp_with_heartbeat(
                cmd,
                creation_flags,
                timeout=process_timeout,
                status_cb=status_cb,
                status_prefix=prefix,
                cancel_event=cancel_event,
            )
        except subprocess.TimeoutExpired as exc:
            # зависание handshake/API — другие player_client обычно не спасают
            last_exc = exc
            break
        except OSError as exc:
            last_exc = exc
            continue

        if result.returncode != 0:
            last_exc = subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
            continue

        raw = (result.stdout or "").strip()
        if not raw:
            last_exc = ValueError("yt-dlp вернул пустой JSON метаданных")
            continue
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
        # ignore-no-formats может вернуть заглушку без title — это не успех
        title = (meta.get("title") or "").strip()
        auto_count = (
            len(meta.get("automatic_captions") or {})
            if isinstance(meta.get("automatic_captions"), dict)
            else -1
        )
        manual_count = (
            len(meta.get("subtitles") or {})
            if isinstance(meta.get("subtitles"), dict)
            else -1
        )
        if not title or title.lower().startswith("youtube video #"):
            last_exc = ValueError(
                _proc_output_text(result.stderr)
                or "Видео недоступно / нет метаданных (регион, удалено, или cookies устарели)"
            )
            continue
        # Caption maps есть — сразу ок. Иначе продолжаем другие client'ы.
        if auto_count > 0 or manual_count > 0:
            return meta
        if best_title_meta is None:
            best_title_meta = meta

    if best_title_meta is not None:
        return best_title_meta

    assert last_exc is not None
    raise last_exc


def _extract_id_from_folder(folder: str) -> str | None:
    """Достаёт YouTube ID из имени папки субтитры_... [ID]."""
    name = os.path.basename(folder)
    m = re.search(r"\[([A-Za-z0-9_-]{11})\]$", name)
    return m.group(1) if m else None


def find_output_folder(video_id: str, base_dir: str | None = None) -> str | None:
    """Находит созданную папку по уникальному ID видео."""
    roots = [base_dir] if base_dir is not None else _subtitle_search_roots()
    suffix = f" [{video_id}]"
    folders: list[str] = []
    for root in roots:
        try:
            for entry in os.scandir(root):
                if (
                    entry.is_dir()
                    and entry.name.startswith("субтитры_")
                    and entry.name.endswith(suffix)
                ):
                    folders.append(entry.path)
        except OSError:
            continue
    return max(folders, key=os.path.getmtime) if folders else None


def find_latest_subtitle_folder(base_dir: str | None = None) -> str | None:
    """Самая свежая папка субтитры_* (cwd, рядом со скриптом, dist/)."""
    folders = list_subtitle_folders(base_dir)
    return folders[0] if folders else None


def list_subtitle_folders(base_dir: str | None = None) -> list[str]:
    """Все папки субтитры_* (корни поиска), свежие сверху, без дублей пути."""
    roots = [base_dir] if base_dir is not None else _subtitle_search_roots()
    folders: list[str] = []
    seen: set[str] = set()
    for root in roots:
        try:
            for entry in os.scandir(root):
                if not (entry.is_dir() and entry.name.startswith("субтитры_")):
                    continue
                try:
                    norm = os.path.normcase(os.path.abspath(entry.path))
                except OSError:
                    continue
                if norm in seen:
                    continue
                seen.add(norm)
                folders.append(entry.path)
        except OSError:
            continue

    def _mtime(path: str) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    folders.sort(key=_mtime, reverse=True)
    return folders


def open_path_in_explorer(path: str) -> None:
    """Открыть папку/файл в проводнике ОС."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return
    if sys.platform == "win32":
        # explorer с папкой — открыть; /select,файл — выделить
        if os.path.isdir(path):
            subprocess.Popen(["explorer", path], close_fds=True)
        else:
            subprocess.Popen(["explorer", f"/select,{path}"], close_fds=True)
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def app_install_dir() -> str:
    """Корень приложения: рядом с .exe (PyInstaller) или с Subtitle_App.py."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def bookmarks_config_path() -> str:
    """Путь к bookmarks.json рядом с приложением."""
    return os.path.join(app_install_dir(), "bookmarks.json")


def load_bookmarks_items() -> list[dict]:
    """Закладки из bookmarks.json: [{title, url}, …]."""
    path = bookmarks_config_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        out.append(
            {
                "title": str(item.get("title") or item["url"]),
                "url": str(item["url"]),
            }
        )
    return out


BOOKMARKS_HISTORY_MAX = 100


def bookmarks_history_path() -> str:
    return os.path.join(app_install_dir(), "bookmarks_history.json")


def load_bookmarks_history() -> list[dict]:
    path = bookmarks_history_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict) and i.get("url")]


def append_bookmarks_history(url: str, title: str) -> None:
    url = (url or "").strip()
    if not url or url.startswith("about:"):
        return
    title = (title or url).strip()[:200]
    items = load_bookmarks_history()
    if items and items[0].get("url") == url:
        items[0]["title"] = title
        items[0]["ts"] = time.time()
    else:
        items.insert(0, {"url": url, "title": title, "ts": time.time()})
    items = items[:BOOKMARKS_HISTORY_MAX]
    try:
        with open(bookmarks_history_path(), "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _bookmarks_user_agent() -> str:
    """UA близкий к реальному Chrome; версию берём из Qt WebEngine, если есть."""
    base = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/{ver} Safari/537.36"
    )
    try:
        raw = QWebEngineProfile.defaultProfile().httpUserAgent() or ""
        m = re.search(r"Chrome/([\d.]+)", raw)
        if m:
            return base.format(ver=m.group(1))
    except Exception:
        pass
    return base.format(ver="131.0.0.0")


# Cloudflare Turnstile / challenge / CDN при bot-check на anime-сайтах
_BOOKMARK_NAV_EXTRA_HOSTS = (
    "challenges.cloudflare.com",
    "cloudflare.com",
    "cdnjs.cloudflare.com",
    "static.cloudflareinsights.com",
    "cloudflareinsights.com",
    "turnstile.cloudflare.com",
    "cf-assets.net",
)


def bookmark_allowed_hosts(items: list[dict] | None = None) -> tuple[str, ...]:
    """Домены закладок для whitelist навигации (поддомены тоже)."""
    if items is None:
        items = load_bookmarks_items()
    hosts: set[str] = set(_BOOKMARK_NAV_EXTRA_HOSTS)
    for item in items:
        host = QUrl(str(item.get("url") or "")).host().lower()
        if not host:
            continue
        hosts.add(host)
        if host.startswith("www."):
            hosts.add(host[4:])
    return tuple(sorted(hosts))


_YT_NAV_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "accounts.google.com",
    "google.com",
    "www.google.com",
    "ytimg.com",
    "yt3.ggpht.com",
    "googlevideo.com",
    "googleapis.com",
    "gstatic.com",
)


def _nav_host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    h = (host or "").lower()
    return any(h == d or h.endswith("." + d) for d in allowed)


def _make_safe_page_class(allowed_hosts: tuple[str, ...]):
    """QWebEnginePage с whitelist только для main-frame навигации."""

    class _SafePage(QWebEnginePage):
        def acceptNavigationRequest(self, url, nav_type, is_main):
            scheme = (url.scheme() or "").lower()
            # blank / ошибка Chromium — иначе unload ломается
            if scheme in ("about", "chrome", "chrome-error", "qrc"):
                return True
            # data/blob только во фреймах (не main) — меньше XSS-поверхности
            if scheme in ("data", "blob") and not is_main:
                return True
            host = (url.host() or "").lower()
            if not host and not is_main:
                return True
            if _nav_host_allowed(host, allowed_hosts):
                return True
            if not is_main:
                return True
            return False

    return _SafePage


def _find_chrome_or_edge() -> str | None:
    """Путь к Chrome/Edge для --app= (Cloudflare там проходит, в Qt — часто нет)."""
    candidates: list[str] = []
    for env_key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(env_key) or ""
        if not root:
            continue
        candidates.extend(
            [
                os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
        )
    # типичный Local AppData Chrome
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        candidates.append(
            os.path.join(local, "Google", "Chrome", "Application", "chrome.exe")
        )
    seen: set[str] = set()
    for path in candidates:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isfile(path):
            return path
    return None


def _subtitle_search_roots() -> list[str]:
    """Где лежат субтитры: cwd + каталог приложения + dist/."""
    roots: list[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        try:
            norm = os.path.normcase(os.path.abspath(path))
        except OSError:
            return
        if norm in seen or not os.path.isdir(path):
            return
        seen.add(norm)
        roots.append(path)

    _add(os.getcwd())
    here = app_install_dir()
    _add(here)
    # при разработке (.py) exe ещё нет — ищем и в dist/
    if not getattr(sys, "frozen", False):
        _add(os.path.join(here, "dist"))
    return roots


def default_output_root() -> str:
    """Куда писать новые прогоны: рядом с exe или в <script_dir>/dist/.

    При разработке (.py): кладём в YouTube_Translator/dist/.
    В exe (frozen): exe уже лежит в dist/ — кладём рядом с ним, без вложенного dist/dist/.
    """
    here = app_install_dir()
    if getattr(sys, "frozen", False):
        # exe уже в dist/ — писать рядом с ним
        os.makedirs(here, exist_ok=True)
        _mark_not_content_indexed(here)
        return here
    # скрипт — писать в dist/ внутри папки проекта
    dist = os.path.join(here, "dist")
    os.makedirs(dist, exist_ok=True)
    _mark_not_content_indexed(dist)
    # legacy-профили на OneDrive (если остались) — тоже не индексировать
    for legacy_name in ("yt_profile", "bookmarks_profile"):
        _mark_not_content_indexed(os.path.join(here, legacy_name))
    return dist


def default_audio_output_dir() -> str:
    """Куда класть MP3 — как в YouTube_DL (~/Music/YouTube_DL)."""
    path = os.path.join(os.path.expanduser("~"), "Music", "YouTube_DL")
    os.makedirs(path, exist_ok=True)
    _mark_not_content_indexed(path)
    return path


def build_audio_ytdlp_cmd(url: str, out_dir: str) -> list[str]:
    """Аргументы yt-dlp для аудио (MP3), как download_music.py."""
    tmpl = os.path.join(out_dir, "%(title).200B [%(id)s].%(ext)s")
    return ytdlp_argv(
        "--no-warnings",
        "--retries",
        "8",
        "--fragment-retries",
        "8",
        *_ytdlp_player_client_extra(),
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "192K",
        "-o",
        tmpl,
        "--",
        url,
    )


def ensure_player_http_url(folder: str) -> str:
    """
    Поднимает/переиспользует локальный HTTP для player.html и возвращает URL.
    Нужен и для встроенного webview, и для fallback в браузер.
    """
    global _player_httpd, _player_httpd_folder
    folder = os.path.abspath(folder)

    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=folder, **kwargs)

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

    with _player_httpd_lock:
        if _player_httpd is not None and _player_httpd_folder == folder:
            port = _player_httpd.server_address[1]
            return f"http://127.0.0.1:{port}/{PLAYER_FILENAME}"
        if _player_httpd is not None:
            try:
                _player_httpd.shutdown()
            except Exception:  # noqa: BLE001
                pass
            try:
                _player_httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
            _player_httpd = None
            _player_httpd_folder = None
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        _player_httpd = httpd
        _player_httpd_folder = folder
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]

    return f"http://127.0.0.1:{port}/{PLAYER_FILENAME}"


def shutdown_player_httpd() -> None:
    """Остановить локальный HTTP для player.html (при закрытии приложения)."""
    global _player_httpd, _player_httpd_folder
    with _player_httpd_lock:
        httpd = _player_httpd
        _player_httpd = None
        _player_httpd_folder = None
    if httpd is None:
        return
    try:
        httpd.shutdown()
    except Exception:  # noqa: BLE001
        pass
    try:
        httpd.server_close()
    except Exception:  # noqa: BLE001
        pass


def _register_child_proc(proc: subprocess.Popen) -> None:
    with _active_child_lock:
        _active_child_procs.add(proc)


def _unregister_child_proc(proc: subprocess.Popen) -> None:
    with _active_child_lock:
        _active_child_procs.discard(proc)


def _kill_proc_tree(proc: subprocess.Popen) -> None:
    """Убить процесс и детей (yt-dlp → ffmpeg)."""
    pid = getattr(proc, "pid", None)
    if not pid:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
                creationflags=0x08000000,
            )
        else:
            proc.kill()
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except (OSError, ProcessLookupError):
            pass


def kill_active_child_processes() -> int:
    """Убить зарегистрированные yt-dlp/ffmpeg и их деревья. Возвращает число попыток."""
    with _active_child_lock:
        procs = list(_active_child_procs)
        _active_child_procs.clear()
    killed = 0
    for proc in procs:
        if getattr(proc, "pid", None):
            _kill_proc_tree(proc)
            killed += 1
    return killed


def resolve_player_target(
    url: str, base_dir: str | None = None
) -> tuple[str | None, str | None]:
    """
    Папка для Плеера + video_id для write_player_html.
    id_for_write = None → брать id из имени папки (не из чужой ссылки в поле).
    """
    video_id = get_video_id(url) if url.strip() else None
    folder_from_url = find_output_folder(video_id, base_dir) if video_id else None
    folder_name = folder_from_url or find_latest_subtitle_folder(base_dir)
    if not folder_name:
        return None, None
    id_for_write = video_id if folder_from_url else None
    return folder_name, id_for_write


def _find_srt(folder: str, *lang_candidates: str) -> str | None:
    """Ищем субтитры в папке: .srt предпочтительнее, иначе .vtt."""
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    seen: set[str] = set()
    ordered: list[str] = []
    for lang in lang_candidates:
        if lang and lang not in seen:
            seen.add(lang)
            ordered.append(lang)

    def _match(ext: str) -> str | None:
        for lang in ordered:
            suffix = f".{lang}.{ext}"
            for name in names:
                if name.endswith(suffix):
                    return os.path.join(folder, name)
        for lang in ordered:
            needle = f".{lang}."
            for name in names:
                if name.endswith(f".{ext}") and needle in name:
                    return os.path.join(folder, name)
        # любой файл нужного расширения (если язык в имени странный)
        for name in names:
            if name.endswith(f".{ext}"):
                return os.path.join(folder, name)
        return None

    return _match("srt") or _match("vtt")


def _ensure_srt(path: str) -> str | None:
    """Если пришёл .vtt — конвертим в .srt (ffmpeg или простая замена)."""
    if path.lower().endswith(".srt"):
        return path
    if not path.lower().endswith(".vtt"):
        return None
    out = path[: -len(".vtt")] + ".srt"
    import shutil

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            subprocess.run(
                [ffmpeg, "-y", "-i", path, out],
                check=True,
                capture_output=True,
                creationflags=(0x08000000 if os.name == "nt" else 0),
            )
            if os.path.isfile(out) and os.path.getsize(out) > 0:
                return out
        except (OSError, subprocess.CalledProcessError):
            pass
    # fallback: грубая конвертация без таймкодов WEBVTT-специфики
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        lines = []
        idx = 1
        blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
        for block in blocks:
            bl = block.strip()
            if not bl or bl.upper().startswith("WEBVTT") or bl.startswith("NOTE"):
                continue
            bl_lines = bl.split("\n")
            timing = None
            text_lines: list[str] = []
            for ln in bl_lines:
                if "-->" in ln:
                    timing = ln.replace(".", ",").strip()
                elif not re.match(r"^\d+$", ln.strip()):
                    text_lines.append(re.sub(r"<[^>]+>", "", ln).strip())
            text = " ".join(t for t in text_lines if t)
            if timing and text:
                lines.append(f"{idx}\n{timing}\n{text}\n")
                idx += 1
        if not lines:
            return None
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return out
    except OSError:
        return None


def _emit(status_cb: StatusCb | None, message: str) -> None:
    print(message)
    if status_cb:
        status_cb(message)


def _proc_output_text(blob: object | None) -> str:
    """stdout/stderr из CompletedProcess: text=True → str, иначе bytes."""
    if blob is None:
        return ""
    if isinstance(blob, bytes):
        return blob.decode("utf-8", errors="replace").strip()
    return str(blob).strip()


def _run_ytdlp_with_heartbeat(
    cmd: list[str],
    creation_flags: int,
    timeout: int,
    status_cb: StatusCb | None,
    status_prefix: str,
    cancel_event: threading.Event | None = None,
) -> subprocess.CompletedProcess:
    """
    yt-dlp с живым статусом и чтением stdout/stderr в фоне.

    Без drain PIPE забивается → yt-dlp стопорится, UI вечно на «попытка N».
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creation_flags,
    )
    _register_child_proc(proc)
    chunks_out: list[str] = []
    chunks_err: list[str] = []

    def _read(stream, dest: list[str]) -> None:
        try:
            dest.append(stream.read() or "")
        except OSError:
            dest.append("")

    t_out = threading.Thread(target=_read, args=(proc.stdout, chunks_out), daemon=True)
    t_err = threading.Thread(target=_read, args=(proc.stderr, chunks_err), daemon=True)
    t_out.start()
    t_err.start()

    t0 = time.monotonic()
    last_tick = -1
    _emit(status_cb, f"{status_prefix} — 0с / {timeout}с…")
    try:
        while proc.poll() is None:
            if cancel_event and cancel_event.is_set():
                _kill_proc_tree(proc)
                t_out.join(timeout=2)
                t_err.join(timeout=2)
                raise DownloadCancelled()
            elapsed = int(time.monotonic() - t0)
            if elapsed != last_tick:
                last_tick = elapsed
                _emit(status_cb, f"{status_prefix} — {elapsed}с / {timeout}с…")
            if elapsed >= timeout:
                _kill_proc_tree(proc)
                t_out.join(timeout=2)
                t_err.join(timeout=2)
                raise subprocess.TimeoutExpired(cmd, timeout)
            time.sleep(0.2)

        t_out.join(timeout=8)
        t_err.join(timeout=8)
        stdout = chunks_out[0] if chunks_out else ""
        stderr = chunks_err[0] if chunks_err else ""
        return subprocess.CompletedProcess(cmd, proc.returncode or 0, stdout, stderr)
    finally:
        _unregister_child_proc(proc)


# =====================================================================
# 1b. SRT → сегменты → склейка → [mm:ss]
# =====================================================================
_SRT_TIME = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)
_MERGE_GAP_SEC = 1.5
_MERGE_MAX_CHARS = 120
# одно общее слово («в», «и», «на») — слишком часто ложная склейка
_WORD_OVERLAP_MIN = 2
_TRAIL_PUNCT_RE = re.compile(r"[\s.,!?;:…]+$", re.UNICODE)


def _hms_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def format_mmss(seconds: float) -> str:
    """[mm:ss] от начала ролика; mm может быть > 59 на длинных видео."""
    total = max(0, int(seconds))
    mm, ss = divmod(total, 60)
    return f"{mm:02d}:{ss:02d}"


def _clean_cue_text(text: str) -> str:
    text = text.replace("&#39;", "'").replace("&quot;", '"')
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _caption_core(text: str) -> str:
    """Для сравнения prefix: без хвостовой пунктуации, lower."""
    return _TRAIL_PUNCT_RE.sub("", text).casefold()


def parse_srt_segments(content: str) -> list[dict]:
    """Парсит SRT в список {start, end, text}."""
    segments: list[dict] = []
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        # первая строка часто номер; ищем таймкод
        time_idx = None
        match = None
        for i, ln in enumerate(lines):
            match = _SRT_TIME.search(ln)
            if match:
                time_idx = i
                break
        if match is None or time_idx is None:
            continue
        start = _hms_to_seconds(*match.groups()[0:4])
        end = _hms_to_seconds(*match.groups()[4:8])
        raw_text = " ".join(lines[time_idx + 1 :])
        if raw_text.startswith(">>"):
            raw_text = raw_text[2:].strip()
        text = _clean_cue_text(raw_text)
        if not text:
            continue
        segments.append({"start": start, "end": end, "text": text})
    return segments


def _word_overlap_merge(prev: str, nxt: str) -> str | None:
    """
    Склеивает частично перекрывающиеся куски без дубля хвоста/головы.
    «Каждый из нас хоть раз» + «хоть раз в жизни сталкивался»
    → «Каждый из нас хоть раз в жизни сталкивался».
    None — перекрытия нет / слишком короткое (1 слово — часто ложь).
    """
    prev_w = prev.split()
    nxt_w = nxt.split()
    if not prev_w or not nxt_w:
        return None
    max_k = min(len(prev_w), len(nxt_w))
    best = 0
    for k in range(_WORD_OVERLAP_MIN, max_k + 1):
        if prev_w[-k:] == nxt_w[:k]:
            best = k
    if best < _WORD_OVERLAP_MIN:
        return None
    return " ".join(prev_w + nxt_w[best:])


def extend_caption_text(prev: str, nxt: str) -> str | None:
    """
    YouTube auto-subs: «катящееся окно» — соседние cue часто уточняют одну фразу.
    Вернуть итоговый текст, если nxt продолжает/уточняет prev.
    None — независимые фразы (можно клеить пробелом или начать новый сегмент).

    Не трогает намеренный повтор внутри одной строки («нет, нет, нет»).
    """
    if not prev:
        return nxt
    if not nxt:
        return prev
    if prev == nxt:
        return prev
    # nxt — удлинённая версия той же фразы
    if nxt.startswith(prev):
        return nxt
    # prev уже содержит nxt (короткое окно внутри длинного)
    if prev.startswith(nxt):
        return prev
    # то же, но с разной хвостовой пунктуацией («раз,» vs «раз в жизни»)
    prev_c = _caption_core(prev)
    nxt_c = _caption_core(nxt)
    if len(prev_c) >= 3 and nxt_c.startswith(prev_c):
        return nxt if len(nxt) >= len(prev) else prev
    if len(nxt_c) >= 3 and prev_c.startswith(nxt_c):
        return prev
    overlapped = _word_overlap_merge(prev, nxt)
    if overlapped is not None:
        return overlapped
    return None


def _chunk_text_by_words(text: str, max_chars: int) -> list[str]:
    """Режет длинный текст без точек на куски ≲ max_chars по словам."""
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    if not words:
        return [text]
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for word in words:
        add = len(word) + (1 if cur else 0)
        if cur and cur_len + add > max_chars:
            chunks.append(" ".join(cur))
            cur = [word]
            cur_len = len(word)
        else:
            cur.append(word)
            cur_len += add
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def _distribute_time_chunks(
    start: float, end: float, parts: list[str]
) -> list[dict]:
    span = max(end - start, 0.01)
    step = span / max(len(parts), 1)
    t = start
    out: list[dict] = []
    for part in parts:
        out.append({"start": t, "end": t + step, "text": part})
        t += step
    return out


def _split_long_segments(
    segments: list[dict], max_chars: int
) -> list[dict]:
    """Сначала по предложениям, потом по словам — чтобы таймкоды не были простынями."""
    result: list[dict] = []
    for seg in segments:
        text = seg["text"]
        if len(text) <= max_chars:
            result.append(seg)
            continue
        if re.search(r"[.?!…]", text):
            parts = [p.strip() for p in re.split(r"(?<=[.?!…])\s+", text) if p.strip()]
        else:
            parts = [text]
        pieces: list[str] = []
        for part in parts:
            pieces.extend(_chunk_text_by_words(part, max_chars))
        result.extend(_distribute_time_chunks(seg["start"], seg["end"], pieces))
    return result


def merge_segments(
    segments: list[dict],
    gap_sec: float = _MERGE_GAP_SEC,
    max_chars: int = _MERGE_MAX_CHARS,
) -> list[dict]:
    """
    Склеивает только «ту же речь» (YouTube rolling / overlap слов).

    Не склеиваем слепо пробелом любые соседние cue при малой паузе —
    у auto-ASR куски часто мусорные и без точек; склейка даёт кашу
    («воняет мусор надо вым … шашлык …»).
    """
    if not segments:
        return []

    merged: list[dict] = []
    cur = {
        "start": segments[0]["start"],
        "end": segments[0]["end"],
        "text": segments[0]["text"],
    }

    for nxt in segments[1:]:
        gap = nxt["start"] - cur["end"]  # < 0 при перекрытии по времени
        near = gap < gap_sec

        if near:
            extended = extend_caption_text(cur["text"], nxt["text"])
            if extended is not None:
                # rolling может вырасти > max_chars — режем в _split_long_segments
                cur["text"] = extended
                cur["end"] = max(cur["end"], nxt["end"])
                continue

        merged.append(cur)
        cur = {
            "start": nxt["start"],
            "end": nxt["end"],
            "text": nxt["text"],
        }

    merged.append(cur)
    return _split_long_segments(merged, max_chars)


def segments_to_plain_text(segments: list[dict]) -> str:
    """Чистый текст: только соседние полные дубли режем (не set() по всему файлу)."""
    lines: list[str] = []
    prev = None
    for seg in segments:
        text = seg["text"]
        if text == prev:
            continue
        lines.append(text)
        prev = text
    return "\n".join(lines)


def segments_to_timed_text(segments: list[dict]) -> str:
    """Строки вида [mm:ss] фраза (соседние полные дубли пропускаем)."""
    lines = []
    prev = None
    for seg in segments:
        text = seg["text"]
        if text == prev:
            continue
        lines.append(f"[{format_mmss(seg['start'])}] {text}")
        prev = text
    return "\n".join(lines)


def build_texts_from_srt(content: str) -> tuple[str, str, list[dict]]:
    """
    Единая сборка итогов из SRT (для пайплайна и тестов).
    Возвращает (plain, timed, phrases).
    """
    raw = parse_srt_segments(content)
    phrases = merge_segments(raw)
    return segments_to_plain_text(phrases), segments_to_timed_text(phrases), phrases


def write_output_texts(
    folder: str,
    clean_text: str,
    timed_text: str,
    lang_code: str,
    max_chars: int = 150000,
) -> int:
    """
    Пишет 0_/1_/часть_* в folder (режим \"w\" — перезапись, не append).
    Возвращает число частей.
    """
    plain_path = os.path.join(folder, "0_весь_текст_для_буфера.txt")
    timed_path = os.path.join(folder, "1_текст_с_таймкодами.txt")
    with open(plain_path, "w", encoding="utf-8") as f:
        f.write(clean_text)
    with open(timed_path, "w", encoding="utf-8") as f:
        f.write(timed_text)

    parts = [
        clean_text[i : i + max_chars] for i in range(0, len(clean_text), max_chars)
    ] or [""]
    for i, part in enumerate(parts):
        filename = os.path.join(folder, f"часть_{lang_code}_{i + 1}.txt")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(part)
        print(f"{os.path.basename(filename)} ({len(part)} знаков)")
    return len(parts)


# =====================================================================
# 2. ЛОГИКА СКАЧИВАНИЯ (без GUI)
# =====================================================================
def download_and_split(
    url: str,
    lang_code: str,
    max_chars: int = 150000,
    status_cb: StatusCb | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    """
    Весь пайплайн без GUI: meta → скачать субы → plain + таймкоды → части.
    True = ок, False = ошибка (текст в stderr / status_cb).
    Без os.chdir — пишет в default_output_root() (…/dist).
    """
    video_id = get_video_id(url)
    if not video_id:
        sys.stderr.write(
            "Ошибка: Введена неверная ссылка! Не могу распознать ID видео YouTube.\n"
        )
        return False

    creation_flags = 0x08000000 if os.name == "nt" else 0
    timings: dict[str, float] = {}
    work_root = default_output_root()

    # --- 1) метаданные: title + какие субы есть (один сетевой проход) ---
    _emit(status_cb, f"Статус: [1/3] метаданные ({lang_code.upper()})…")
    t0 = time.perf_counter()
    try:
        meta = fetch_video_meta(
            url, creation_flags, status_cb=status_cb, cancel_event=cancel_event
        )
    except DownloadCancelled:
        sys.stderr.write("Отменено пользователем.\n")
        return False
    except FileNotFoundError:
        sys.stderr.write("Ошибка: yt-dlp не установлен или не найден в PATH.\n")
        return False
    except PermissionError as exc:
        sys.stderr.write(
            "Ошибка: Windows запретил запуск yt-dlp (Access denied).\n"
            f"{exc}\n"
            "Обычно это блокировка Scripts\\yt-dlp.exe (Защитник/антивирус).\n"
            "Приложение теперь зовёт python -m yt_dlp — перезапусти и повтори.\n"
            "Если снова: разреши yt-dlp.exe в Защитнике или переустанови: "
            "pip install -U yt-dlp\n"
        )
        return False
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "Ошибка: yt-dlp завис на метаданных (таймаут). "
            "Браузер YouTube открывает, а CLI — нет: TUN/VPN (Hiddify) "
            "часто не гоняет трафик python/yt-dlp так же, как Chrome. "
            "Проверь что VPN connected, режим TUN, потом повтори.\n"
        )
        return False
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            details = _proc_output_text(error.stderr) or _proc_output_text(error.stdout)
        else:
            details = str(error)
        hint = ""
        low = details.lower()
        if (
            "connection reset" in low
            or "10054" in details
            or "10060" in details
            or "connection aborted" in low
            or "unable to download api page" in low
            or "timed out" in low
            or "timeout" in low
        ):
            hint = (
                "\nПодсказка: Chrome жив, yt-dlp нет — это не «запрет в приложении». "
                "TUN/VPN режет TLS у Python. Переподключи VPN (TUN), повтори.\n"
            )
        elif "format is not available" in low or "requested format" in low:
            hint = (
                "\nПодсказка: конфликт cookies и player_client=android. "
                "В новой версии с cookies идёт web/tv. Перезапусти SR и повтори.\n"
            )
        elif "unavailable" in low or "page needs to be reloaded" in low:
            hint = (
                "\nПодсказка: ролик недоступен для этого IP/аккаунта, "
                "или cookies устарели. Обнови экспорт cookies с youtube.com "
                "в ~/.subtitle_ripper/ или попробуй другой VPN / без VPN.\n"
            )
        elif (
            "sign in to confirm" in low
            or "not a bot" in low
            or ("cookies" in low and "authentication" in low)
        ):
            cinfo = _inspect_youtube_cookies(_ytdlp_cookies_file())
            if cinfo.get("path_name") and not cinfo.get("looks_logged_in"):
                hint = (
                    "\nПодсказка: cookies найдены, но без логина YouTube "
                    f"({cinfo.get('rows')} шт., нет LOGIN_INFO/SID). "
                    "Переэкспортируй cookies, будучи залогиненным на youtube.com, "
                    "в ~/.subtitle_ripper/www.youtube.com_cookies.txt\n"
                )
            else:
                hint = (
                    "\nПодсказка: YouTube bot-check (часто IP VPS/Amnezia).\n"
                    "Нужен свежий экспорт cookies (залогиненный аккаунт) в "
                    "~/.subtitle_ripper/www.youtube.com_cookies.txt\n"
                )
        elif (
            "could not copy" in low and "cookie" in low
        ) or ("failed to decrypt" in low and "dpapi" in low):
            hint = (
                "\nПодсказка: читать cookies прямо из Chrome/Edge на Win нельзя "
                "(DPAPI / app-bound). Нужен файл cookies.txt в ~/.subtitle_ripper/\n"
            )
        sys.stderr.write(
            f"Ошибка: не удалось получить метаданные видео.\n{details}\n{hint}"
        )
        return False
    timings["meta"] = time.perf_counter() - t0

    video_title = sanitize_filename((meta.get("title") or "").strip())
    cookie_path = _ytdlp_cookies_file()
    cookie_info = _inspect_youtube_cookies(cookie_path)
    if cookie_path and not cookie_info.get("looks_logged_in"):
        _emit(
            status_cb,
            "Статус: cookies есть, но без логина YouTube (нет LOGIN_INFO/SID) — "
            "часто bot-check. Лучше переэкспортировать, будучи залогиненным.",
        )
    resolved = resolve_subtitle_track_with_fallback(meta, lang_code)
    blind_subs = False
    if resolved is None:
        # Meta часто отдаёт title, но пустые caption maps (YouTube/EJS/VPN).
        # Тогда всё равно пробуем write-auto-subs / write-subs.
        blind_subs = True
        mode = "auto"
        yt_lang = lang_code
        effective_lang = lang_code
        _emit(
            status_cb,
            "Статус: в meta нет списка дорожек → пробую скачать авто/обычные субы вслепую…",
        )
    else:
        mode, yt_lang, effective_lang = resolved
        if effective_lang != lang_code:
            _emit(
                status_cb,
                f"Статус: для '{lang_code}' дорожки нет → беру {effective_lang} "
                f"({'авто' if mode == 'auto' else 'обычные'})",
            )

    folder_name = f"субтитры_{video_title} [{video_id}]"
    folder_path = os.path.join(work_root, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    # --- 2) один скачивающий вызов yt-dlp ---
    mode_label = "авто" if mode == "auto" else "обычные"
    _emit(
        status_cb,
        f"Статус: [2/3] скачиваю {mode_label} {yt_lang}-субтитры…",
    )
    t1 = time.perf_counter()

    out_template = os.path.join(folder_path, "temp_subtitles")
    if blind_subs:
        # en + ru + all auto/manual — что удастся
        sub_langs = f"{lang_code}.*,en.*,ru.*,all"
        cmd = ytdlp_argv(
            "--write-auto-subs",
            "--write-subs",
            "--sub-langs",
            sub_langs,
            "--convert-subs",
            "srt",
            "--skip-download",
            "--ignore-no-formats-error",
            "--socket-timeout",
            "45",
            *_ytdlp_player_client_extra(),
            "-o",
            out_template,
            "--",
            url,
        )
    else:
        write_flag = "--write-auto-subs" if mode == "auto" else "--write-subs"
        # en → en.* чтобы поймать en-US / en-orig; точный ключ из meta тоже передаём
        sub_langs = yt_lang if "-" in yt_lang else f"{yt_lang}.*"
        cmd = ytdlp_argv(
            write_flag,
            "--sub-langs",
            sub_langs,
            "--convert-subs",
            "srt",
            "--skip-download",
            "--ignore-no-formats-error",
            "--socket-timeout",
            "45",
            *_ytdlp_player_client_extra(),
            "-o",
            out_template,
            "--",
            url,
        )
    try:
        result = _run_ytdlp_with_heartbeat(
            cmd,
            creation_flags,
            timeout=180,
            status_cb=status_cb,
            status_prefix=f"Статус: [2/3] скачиваю {mode_label} {yt_lang}-субтитры",
            cancel_event=cancel_event,
        )
    except DownloadCancelled:
        sys.stderr.write("Отменено пользователем.\n")
        return False
    except PermissionError as exc:
        sys.stderr.write(
            "Ошибка: Windows запретил запуск yt-dlp (Access denied).\n"
            f"{exc}\n"
            "Перезапусти приложение — оно зовёт python -m yt_dlp.\n"
        )
        return False
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "Ошибка: yt-dlp завис на скачивании субтитров (таймаут 180с). "
            "VPN/TUN для python часто рвёт TLS, пока браузер ещё жив. Повтори.\n"
        )
        return False
    timings["subs"] = time.perf_counter() - t1

    if result.returncode != 0:
        err = _proc_output_text(result.stderr) or _proc_output_text(result.stdout)
        sys.stderr.write(f"Ошибка yt-dlp: {err}\n")
        return False

    found = _find_srt(folder_path, yt_lang, effective_lang, lang_code, "en", "ru")
    srt_file = _ensure_srt(found) if found else None
    if not srt_file:
        try:
            leftover = ", ".join(os.listdir(folder_path)) or "(пусто)"
        except OSError:
            leftover = "(нет доступа к папке)"
        err_tail = _proc_output_text(result.stderr)
        if blind_subs:
            sys.stderr.write(
                f"Ошибка: субтитры отсутствуют совсем "
                f"(meta пустая и слепое скачивание не дало .srt/.vtt; "
                f"искали '{lang_code}' / en / ru).\n"
                f"В папке: {leftover}\n"
            )
        else:
            sys.stderr.write(
                f"Ошибка: yt-dlp не сохранил .srt/.vtt для языка '{yt_lang}' "
                f"(искали также '{effective_lang}' / '{lang_code}').\n"
                f"В папке: {leftover}\n"
            )
        if err_tail:
            sys.stderr.write(f"{err_tail}\n")
        err_low = (err_tail or "").lower()
        cinfo = _inspect_youtube_cookies(_ytdlp_cookies_file())
        if (
            "sign in to confirm" in err_low
            or "not a bot" in err_low
            or not cinfo.get("looks_logged_in")
        ):
            sys.stderr.write(
                "\nПричина: YouTube bot-check. Файл cookies есть, но это "
                "гостевая/неполная сессия (нет LOGIN_INFO / SID / __Secure-1PSID).\n"
                "Как починить:\n"
                "1) В браузере зайди на youtube.com под аккаунтом (не инкогнито).\n"
                "2) Расширение «Get cookies.txt LOCALLY» → Export для youtube.com.\n"
                "3) Положи файл в %USERPROFILE%\\.subtitle_ripper\\ "
                "как www.youtube.com_cookies.txt (замени старый).\n"
                "4) Если качаешь через Amnezia/VPS — cookies лучше снять с того же "
                "IP (VPN включён) или попробуй без VPN.\n"
            )
        elif not _ytdlp_js_runtime_args():
            sys.stderr.write(
                "Подсказка: нет JS runtime (deno/node) — YouTube часто "
                "не отдаёт субтитры. Node у тебя обычно есть; перезапусти SR.\n"
            )
        return False

    # --- 3) разбор srt → plain + таймкоды / части / буферный файл ---
    _emit(status_cb, "Статус: [3/3] обрабатываю текст…")
    t2 = time.perf_counter()

    with open(srt_file, "r", encoding="utf-8") as f:
        content = f.read()

    clean_text, timed_text, phrases = build_texts_from_srt(content)
    if not phrases:
        sys.stderr.write("Ошибка: в SRT не найдено текстовых сегментов.\n")
        return False

    try:
        os.remove(srt_file)
    except OSError:
        pass

    n_parts = write_output_texts(
        folder_path, clean_text, timed_text, effective_lang, max_chars=max_chars
    )
    try:
        write_player_html(folder_path, video_id)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"Предупреждение: player.html не записался: {exc}\n")
    timings["parse"] = time.perf_counter() - t2
    total = sum(timings.values())
    timing_line = (
        f"Тайминги: meta {timings['meta']:.1f}s | "
        f"subs {timings['subs']:.1f}s | "
        f"parse {timings['parse']:.2f}s | "
        f"всего {total:.1f}s ({mode_label}) | "
        f"+ файл с таймкодами ({len(phrases)} фраз)"
    )
    print(f"Готово. {n_parts} частей. Таймкодов: {len(phrases)}.")
    _emit(status_cb, timing_line)
    return True


def download_audio(
    url: str,
    status_cb: StatusCb | None = None,
    out_dir: str | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[bool, str]:
    """
    Скачивает аудио в MP3 через yt-dlp (как YouTube_DL/download_music.py).
    Возвращает (ok, путь_к_папке_или_текст_ошибки).
    """
    if not get_video_id(url):
        return False, "Не похоже на YouTube-ссылку — проверь URL"

    if shutil.which("ffmpeg") is None:
        _emit(
            status_cb,
            "Предупреждение: ffmpeg не в PATH — MP3 может не получиться",
        )

    creation_flags = 0x08000000 if os.name == "nt" else 0
    target = out_dir or default_audio_output_dir()
    os.makedirs(target, exist_ok=True)

    _emit(status_cb, "Статус: скачиваю аудио (MP3)…")
    cmd = build_audio_ytdlp_cmd(url, target)
    try:
        result = _run_ytdlp_with_heartbeat(
            cmd,
            creation_flags,
            timeout=600,
            status_cb=status_cb,
            status_prefix="Статус: аудио",
            cancel_event=cancel_event,
        )
    except DownloadCancelled:
        return False, "Отменено пользователем"
    except FileNotFoundError:
        return False, "yt-dlp не установлен или не найден в PATH"
    except PermissionError as exc:
        return False, f"Windows запретил запуск yt-dlp: {exc}"
    except subprocess.TimeoutExpired:
        return False, "Таймаут скачивания аудио (600с)"

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        return False, details or f"yt-dlp завершился с кодом {result.returncode}"

    return True, target


# =====================================================================
# 3. GUI — PySide6
# =====================================================================
# Stroke-иконки в стиле оверлея (Slate), для chrome плеера
_UI_SVG_STROKE = "#cbd5e1"
_UI_SVG_ICONS: dict[str, str] = {
    # Сайдбар открыт → свернуть (шеврон вправо / «закрыть панель»)
    "panel_collapse": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_UI_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<rect x="3" y="4" width="18" height="16" rx="2"/>'
        f'<path d="M15 4v16"/><polyline points="10 9 13 12 10 15"/></svg>'
    ),
    # Сайдбар свёрнут → развернуть
    "panel_expand": (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{_UI_SVG_STROKE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<rect x="3" y="4" width="18" height="16" rx="2"/>'
        f'<path d="M9 4v16"/><polyline points="14 9 11 12 14 15"/></svg>'
    ),
}


def _ui_svg_icon(name: str, size: int = 18) -> QIcon:
    svg = _UI_SVG_ICONS.get(name)
    if not svg:
        return QIcon()
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return QIcon(pm)


def apply_primary_glow(btn: QPushButton, *, strong: bool = False) -> None:
    """Лёгкая мягкая тень на primary (Slate A — без зелёного glow)."""
    effect = QGraphicsDropShadowEffect(btn)
    effect.setBlurRadius(18 if strong else 12)
    effect.setOffset(0, 1)
    effect.setColor(QColor(15, 23, 42, 160 if strong else 110))
    btn.setGraphicsEffect(effect)


def make_app_icon() -> QIcon:
    """Эмблема SR (Slate) вместо дефолтной иконки Python/Qt в title bar."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128):
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = max(1, size // 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#334155"))
        painter.drawRoundedRect(
            margin,
            margin,
            size - 2 * margin,
            size - 2 * margin,
            size * 0.22,
            size * 0.22,
        )
        # лёгкий блик сверху
        painter.setBrush(QColor(148, 163, 184, 70))
        painter.drawRoundedRect(
            margin,
            margin,
            size - 2 * margin,
            max(1, (size - 2 * margin) // 2),
            size * 0.22,
            size * 0.22,
        )
        font = QFont("Segoe UI", max(7, int(size * 0.34)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "SR")
        painter.end()
        icon.addPixmap(pm)
    return icon


def configure_qt_theme(app: QApplication) -> None:
    """Тема A — Slate: спокойный тёмный UI главной + плеера (без зелёного accent)."""
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#0f1115"))
    palette.setColor(QPalette.WindowText, QColor("#f1f5f9"))
    palette.setColor(QPalette.Base, QColor("#151a24"))
    palette.setColor(QPalette.AlternateBase, QColor("#1c212b"))
    palette.setColor(QPalette.Text, QColor("#f1f5f9"))
    palette.setColor(QPalette.Button, QColor("#1e293b"))
    palette.setColor(QPalette.ButtonText, QColor("#f1f5f9"))
    palette.setColor(QPalette.Highlight, QColor("#334155"))
    palette.setColor(QPalette.HighlightedText, QColor("#f8fafc"))
    app.setPalette(palette)
    app.setStyleSheet(
        """
        QWidget { background: #0f1115; color: #f1f5f9; font-size: 14px; }
        QLabel[muted="true"] { color: #64748b; }
        QLabel[status_bar="true"] { color: #64748b; font-size: 12px; }
        QLabel[player_title="true"] { color: #e2e8f0; }
        QLabel[brand_mark="true"] {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #475569, stop:1 #1e293b);
            color: #f8fafc;
            border-radius: 9px;
            font-weight: 800;
            font-size: 13px;
        }
        QLineEdit {
            background: #151a24;
            border: 1px solid #2a3548;
            border-radius: 10px;
            padding: 10px 12px;
            color: #cbd5e1;
            selection-background-color: #334155;
        }
        QLineEdit:focus {
            border: 1px solid #475569;
            background: #1a2230;
        }
        QPushButton {
            background: #1e293b;
            color: #f1f5f9;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 10px 14px;
            min-height: 18px;
        }
        QPushButton:hover { background: #334155; border: 1px solid #475569; }
        QPushButton:disabled {
            background: #1c212b;
            color: #64748b;
            border: 1px solid #1c212b;
        }
        QPushButton[fallback="true"] {
            background: #151a24;
            color: #cbd5e1;
            border: 1px solid #2a3548;
        }
        QPushButton[fallback="true"]:hover {
            background: #1a2230;
            border: 1px solid #334155;
        }
        QPushButton[segmented="true"] {
            background: #1c212b;
            color: #94a3b8;
            min-width: 56px;
            padding: 8px 14px;
            border: 1px solid transparent;
        }
        QPushButton[segmented="true"]:hover {
            background: #1a2230;
        }
        QPushButton[segmented="true"][selected="true"] {
            background: #334155;
            color: #f8fafc;
            border: 1px solid #64748b;
        }
        QPushButton[ai_mode="true"] {
            min-width: 96px;
            padding: 8px 16px;
        }
        QPushButton[selected="true"] {
            background: #334155;
            color: #f8fafc;
        }
        QPushButton[mark="true"] {
            text-align: left;
            padding-left: 10px;
            padding-right: 8px;
        }
        QPushButton[compact="true"] {
            padding: 6px 10px;
            min-height: 14px;
            border-radius: 8px;
        }
        QPushButton[sidebar_tab="true"] {
            background: #151a24;
            color: #cbd5e1;
            border: 1px solid #1c1f26;
            border-radius: 8px;
            padding: 6px 4px;
            min-width: 32px;
            max-width: 36px;
        }
        QPushButton[sidebar_tab="true"]:hover {
            background: #1a2230;
            border-color: #2a3548;
        }
        QPushButton[sidebar_tab="true"][selected="true"] {
            background: #334155;
            color: #f8fafc;
        }
        QTextBrowser#ai_summary {
            padding: 8px;
            line-height: 1.45;
            background: #151a24;
            border: 1px solid #1c1f26;
            border-radius: 8px;
            color: #cbd5e1;
        }
        QPushButton[cancel_busy="true"] {
            background: #b91c1c;
            color: white;
            min-width: 96px;
            padding: 8px 14px;
            border-radius: 8px;
            border: 1px solid #991b1b;
        }
        QPushButton[cancel_busy="true"]:hover {
            background: #dc2626;
        }
        QPushButton[motion_busy="true"] {
            background: #b45309;
            border: 1px solid #92400e;
        }
        QPushButton[fallback="true"][motion_busy="true"] {
            background: #b45309;
            border: 1px solid #92400e;
        }
        QFrame[card="true"] {
            background: #0c0e12;
            border: 1px solid #1c1f26;
            border-radius: 12px;
        }
        QScrollArea { border: none; }
        """
    )


class DistFilesDialog(QDialog):
    """IDEA-021: папки dist/субтитры_* → txt внутри приложения → копировать."""

    _TXT_PRIORITY = (
        "0_весь_текст_для_буфера.txt",
        "1_текст_с_таймкодами.txt",
    )

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        prefer_folder: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Файлы dist — субтитры")
        self.resize(900, 560)
        self._prefer_folder = prefer_folder
        self._folder_path: str | None = None
        self._file_path: str | None = None

        root = QVBoxLayout(self)
        root.setSpacing(8)

        self.hint = QLabel(
            "Субтитры YouTube в dist/ (не музыка). Выбери папку → txt → копируй. "
            "Проводник не обязателен."
        )
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:#94a3b8;")
        root.addWidget(self.hint)

        split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.addWidget(QLabel("Папки"))
        self.folder_list = QListWidget()
        self.folder_list.currentItemChanged.connect(self._on_folder_changed)
        left_l.addWidget(self.folder_list, stretch=1)
        split.addWidget(left)

        mid = QWidget()
        mid_l = QVBoxLayout(mid)
        mid_l.setContentsMargins(0, 0, 0, 0)
        mid_l.addWidget(QLabel("Файлы .txt"))
        self.file_list = QListWidget()
        self.file_list.currentItemChanged.connect(self._on_file_changed)
        mid_l.addWidget(self.file_list, stretch=1)
        split.addWidget(mid)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.addWidget(QLabel("Текст"))
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Выбери txt слева…")
        right_l.addWidget(self.text, stretch=1)
        split.addWidget(right)

        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 3)
        split.setSizes([260, 160, 480])
        root.addWidget(split, stretch=1)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#64748b;font-size:12px;")
        root.addWidget(self.status)

        row = QHBoxLayout()
        self.copy_btn = QPushButton("Копировать всё")
        self.copy_btn.setToolTip("Весь текст файла в буфер")
        self.copy_btn.clicked.connect(self._copy_all)
        row.addWidget(self.copy_btn)

        self.copy_sel_btn = QPushButton("Копировать выделенное")
        self.copy_sel_btn.setProperty("fallback", True)
        self.copy_sel_btn.clicked.connect(self._copy_selection)
        row.addWidget(self.copy_sel_btn)

        self.explorer_btn = QPushButton("В проводнике…")
        self.explorer_btn.setProperty("fallback", True)
        self.explorer_btn.setToolTip("На всякий случай — открыть папку снаружи")
        self.explorer_btn.clicked.connect(self._open_folder_explorer)
        row.addWidget(self.explorer_btn)
        row.addStretch()
        root.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.reject)
        root.addWidget(buttons)

        self.reload()

    def reload(self) -> None:
        self.folder_list.clear()
        self.file_list.clear()
        self.text.clear()
        self._folder_path = None
        self._file_path = None
        folders = list_subtitle_folders()
        prefer_norm = None
        if self._prefer_folder:
            try:
                prefer_norm = os.path.normcase(os.path.abspath(self._prefer_folder))
            except OSError:
                prefer_norm = None
        select_row = 0
        for i, path in enumerate(folders):
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.folder_list.addItem(item)
            if prefer_norm:
                try:
                    if os.path.normcase(os.path.abspath(path)) == prefer_norm:
                        select_row = i
                except OSError:
                    pass
        if folders:
            self.folder_list.setCurrentRow(select_row)
            self.status.setText(f"{len(folders)} папок · корень: {default_output_root()}")
        else:
            self.status.setText(f"Пусто · ищем в: {', '.join(_subtitle_search_roots())}")

    def _on_folder_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        self.file_list.clear()
        self.text.clear()
        self._file_path = None
        if current is None:
            self._folder_path = None
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        self._folder_path = str(path) if path else None
        if not self._folder_path or not os.path.isdir(self._folder_path):
            return
        names: list[str] = []
        try:
            for entry in os.scandir(self._folder_path):
                if entry.is_file() and entry.name.lower().endswith(".txt"):
                    names.append(entry.name)
        except OSError as exc:
            self.status.setText(f"Не читается папка: {exc}")
            return
        # Приоритетные файлы сверху, остальные по имени
        prio = {n: i for i, n in enumerate(self._TXT_PRIORITY)}

        def _key(name: str) -> tuple[int, str]:
            return (prio.get(name, 100), name.lower())

        names.sort(key=_key)
        for name in names:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, os.path.join(self._folder_path, name))
            self.file_list.addItem(item)
        if names:
            # По умолчанию — буферный текст, иначе первый
            prefer = self._TXT_PRIORITY[0]
            row = next((i for i, n in enumerate(names) if n == prefer), 0)
            self.file_list.setCurrentRow(row)
            self.status.setText(f"{os.path.basename(self._folder_path)} · {len(names)} txt")
        else:
            self.status.setText(f"{os.path.basename(self._folder_path)} · нет .txt")

    def _on_file_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            self._file_path = None
            self.text.clear()
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        self._file_path = str(path) if path else None
        if not self._file_path or not os.path.isfile(self._file_path):
            self.text.clear()
            return
        try:
            with open(self._file_path, encoding="utf-8", errors="replace") as f:
                body = f.read()
        except OSError as exc:
            self.text.setPlainText(f"Не удалось прочитать:\n{exc}")
            self.status.setText("Ошибка чтения")
            return
        self.text.setPlainText(body)
        self.status.setText(
            f"{os.path.basename(self._file_path)} · {len(body)} символов"
        )

    def _copy_all(self) -> None:
        body = self.text.toPlainText()
        if not body:
            self.status.setText("Нечего копировать")
            return
        QApplication.clipboard().setText(body)
        self.status.setText(f"Скопировано {len(body)} символов")

    def _copy_selection(self) -> None:
        cursor = self.text.textCursor()
        sel = cursor.selectedText().replace("\u2029", "\n")
        if not sel:
            self.status.setText("Выдели фрагмент или жми «Копировать всё»")
            return
        QApplication.clipboard().setText(sel)
        self.status.setText(f"Скопировано выделение ({len(sel)} символов)")

    def _open_folder_explorer(self) -> None:
        path = self._folder_path or default_output_root()
        if self._folder_path is None:
            os.makedirs(path, exist_ok=True)
        open_path_in_explorer(path)
        self.status.setText(f"Проводник: {os.path.basename(path) or path}")


class SubtitleApp(QMainWindow):
    """Qt-окно: скачивание + плеер + закладки."""

    _DOWNLOAD_SIZE = (640, 400)
    _PLAYER_SIZE = (1120, 760)
    # Низкий min — чтобы Win+стрелки / snap к краю работали без борьбы с Qt
    _PLAYER_MIN_SIZE = (360, 280)

    _status_signal: Signal = Signal(str)  # thread-safe статус из фонового потока
    _player_status_signal: Signal = Signal(str)  # статус на экране плеера из фонового потока
    _done_signal: Signal = Signal(bool, str, str, str)  # ok, url, error_text, timing_hint

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Subtitle Ripper Pro")
        self.setWindowIcon(make_app_icon())
        # До любых resize/move: атрибуты + stack ещё нет → guard в _is_download_view_active
        self._window_mode = "download"  # download = fixed · free = плеер/закладки
        self._ignore_size_relock = False

        self._busy = False
        self._lang_code = "ru"
        self._ai_mode = "invest"  # invest | general
        self._current_player_folder: str | None = None
        self._player_http_url: str | None = None
        self._last_ai_analysis: dict | None = None
        self._all_marks: list[dict] = []
        self._player_theater = False
        self._sidebar_collapsed = False
        self._splitter_sizes_normal: list[int] | None = None
        self._splitter_sizes_with_sidebar: list[int] | None = None
        self._player_pending_video_id: str | None = None
        self._player_video_loaded = False
        self._pause_retries_left = 0
        self._pending_seek_seconds: int | None = None
        self._ai_busy = False
        self._player_status_core = "Статус: открой ролик через кнопку «Плеер»."
        self._ai_busy_t0: float | None = None
        self._ai_cancel_event = threading.Event()
        self._ai_job_id = 0
        self._bookmarks = load_bookmarks_items()
        self._cancel_event = threading.Event()
        self._cancel_context = ""  # download | player | player_subs | audio
        # ✨ ИИ без папки: скачать субы текущего URL, затем сразу analyze
        self._pending_ai_after_subs = False
        # IDEA-022: отдельное overlay-окно (не в stack)
        self._overlay_window = None

        # подключаем сигналы: вызов из любого потока → обновление в UI-потоке
        self._status_signal.connect(self._set_status)
        self._player_status_signal.connect(self._set_player_status_core)
        self._done_signal.connect(self._on_download_done)

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack)

        self.download_view = self._build_download_view()
        self.player_view = self._build_player_view()
        self.bookmarks_view = self._build_bookmarks_view()
        self.stack.addWidget(self.download_view)
        self.stack.addWidget(self.player_view)
        self.stack.addWidget(self.bookmarks_view)

        # Слой G: hover/press + пульс busy (ui_motion.py)
        attach_many(
            self.ru_btn,
            self.en_btn,
            self.download_btn,
            self.audio_btn,
            self.overlay_btn,
            self.player_btn,
            self.bookmarks_btn,
            self.clear_btn,
            self.back_btn,
            self.theater_btn,
            self.analyze_btn,
            self.ai_btn,
            self.load_video_btn,
            self.player_audio_btn,
            self.dist_files_btn,
            self.login_btn,
            self.ai_invest_btn,
            self.ai_general_btn,
            self.sidebar_toggle_btn,
            self.bookmarks_back_btn,
            self.bookmarks_open_browser_btn,
        )
        # Glow до BusyPulse: иначе pulse захватит opacity и потом тень его убьёт
        apply_primary_glow(self.download_btn)
        apply_primary_glow(self.player_btn)
        apply_primary_glow(self.ai_btn, strong=True)
        self._pulse_download = BusyPulse(self.download_btn, self)
        self._pulse_ai = BusyPulse(self.ai_btn, self)

        # После stack: иначе resize в lock бьёт AttributeError в move/resizeEvent
        self._lock_download_window_size()

        self._status_core = "Статус: ожидание ссылки…"
        self._busy_t0: float | None = None
        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(400)
        self._busy_timer.timeout.connect(self._refresh_busy_clock)
        self._ai_busy_timer = QTimer(self)
        self._ai_busy_timer.setInterval(400)
        self._ai_busy_timer.timeout.connect(self._refresh_ai_busy_clock)

    def eventFilter(self, obj, event):  # noqa: N802 — Qt API
        # Space на сфокусированной QPushButton НЕ доходит до keyPressEvent окна —
        # ловим на уровне приложения (installEventFilter на QApplication).
        # Глушим Space на кнопках — иначе Qt activate'ит QPushButton.
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space:
            if isinstance(obj, QPushButton):
                return True
        return super().eventFilter(obj, event)

    def _ensure_window_on_screen(self) -> None:
        """После программного resize/showNormal — frame не вылезает за монитор.

        Qt resize растёт от текущего top-left: у края экрана низ/право
        уходят за availableGeometry. Сдвигаем move; при необходимости
        уменьшаем client size. Не трогаем maximized/fullscreen.
        """
        if self.isMaximized() or self.isFullScreen():
            return
        screen = self.screen()
        if screen is None:
            app = QApplication.instance()
            screen = app.primaryScreen() if app is not None else None
        if screen is None:
            return
        avail = screen.availableGeometry()
        frame = self.frameGeometry()
        # Рамка (title bar / borders) — в client size её нет
        chrome_w = max(0, frame.width() - self.width())
        chrome_h = max(0, frame.height() - self.height())
        max_w = max(1, avail.width() - chrome_w)
        max_h = max(1, avail.height() - chrome_h)
        tw = min(self.width(), max_w)
        th = min(self.height(), max_h)
        if tw != self.width() or th != self.height():
            self.resize(tw, th)
            frame = self.frameGeometry()
        x = frame.x()
        y = frame.y()
        if frame.width() <= avail.width():
            x = max(avail.left(), min(x, avail.left() + avail.width() - frame.width()))
        else:
            x = avail.left()
        if frame.height() <= avail.height():
            y = max(avail.top(), min(y, avail.top() + avail.height() - frame.height()))
        else:
            y = avail.top()
        if x != frame.x() or y != frame.y():
            self.move(x, y)

    def _lock_download_window_size(self) -> None:
        """Экран скачивания: soft-lock ~640×400 (не min==max — иначе убивает Aero Snap)."""
        self._window_mode = "download"
        if self.isMaximized() or self.isFullScreen():
            self.showNormal()
        w, h = self._DOWNLOAD_SIZE
        if self.size() != QSize(w, h):
            self.resize(w, h)
        self._ensure_window_on_screen()

    def _is_download_view_active(self) -> bool:
        if not hasattr(self, "stack") or not hasattr(self, "download_view"):
            return False
        return self.stack.currentWidget() is self.download_view

    def _should_lock_download_size(self) -> bool:
        if self._ignore_size_relock:
            return False
        if self._window_mode != "download":
            return False
        return self._is_download_view_active() and not self.isFullScreen()

    def _maybe_relock_download_window_size(self) -> None:
        if self._should_lock_download_size():
            QTimer.singleShot(0, self._lock_download_window_size)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 — Qt API
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._maybe_relock_download_window_size()

    def moveEvent(self, event) -> None:  # noqa: N802 — Qt API
        super().moveEvent(event)
        self._maybe_relock_download_window_size()

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt API
        super().resizeEvent(event)
        self._maybe_relock_download_window_size()
        if hasattr(self, "player_title"):
            self._refresh_player_title_elide()

    def _refresh_player_title_elide(self) -> None:
        """Имя папки по центру: ElideMiddle + полный текст в tooltip."""
        if not hasattr(self, "player_title"):
            return
        full = getattr(self, "_player_title_full", "") or ""
        if not full:
            return
        self.player_title.setToolTip(full)
        w = self.player_title.width() - 8
        if w < 60:
            w = max(100, self.width() - 480)
        elided = QFontMetrics(self.player_title.font()).elidedText(
            full, Qt.TextElideMode.ElideMiddle, w
        )
        self.player_title.setText(elided)

    def _window_looks_like_download_size(self) -> bool:
        """Если плеер открыли, а окно всё ещё «карточка» скачивания — надо раздуть."""
        dw, dh = self._DOWNLOAD_SIZE
        return self.width() <= dw + 48 and self.height() <= dh + 48

    def _apply_player_default_size(self) -> None:
        if self._window_mode != "free":
            return
        if self.isMaximized() or self.isFullScreen():
            return
        w, h = self._PLAYER_SIZE
        if self.size() != QSize(w, h):
            self.resize(w, h)
        self._ensure_window_on_screen()

    def _unlock_player_window_size(self, *, reset_geometry: bool = True) -> None:
        """Плеер/закладки: снять фиксацию — Win-snap и ресайз работают.

        Дефолт плеера: **1120×760** (не размер экрана скачивания).
        """
        self._window_mode = "free"
        self._ignore_size_relock = True
        self.setMinimumSize(*self._PLAYER_MIN_SIZE)
        if reset_geometry or self._window_looks_like_download_size():
            self.resize(*self._PLAYER_SIZE)
            QTimer.singleShot(0, self._apply_player_default_size)
        self._ensure_window_on_screen()
        # отложенно: после WM-рамки frameGeometry точнее; resize/move без lock
        QTimer.singleShot(0, self._ensure_window_on_screen)
        QTimer.singleShot(50, self._clear_size_relock_guard)

    def _clear_size_relock_guard(self) -> None:
        self._ignore_size_relock = False

    def _disable_space_button_activate(self, *buttons) -> None:
        """Пробел не должен жать кнопки. ClickFocus мало: после клика мышью
        фокус остаётся на кнопке → Space снова activate. NoFocus — только мышь."""
        for btn in buttons:
            if btn is None:
                continue
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _build_download_view(self) -> QWidget:
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        mark = QLabel("SR")
        mark.setProperty("brand_mark", True)
        mark.setFixedSize(34, 34)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setToolTip("Subtitle Ripper")
        brand_row.addWidget(mark)
        title = QLabel("YouTube → субтитры")
        title.setFont(QFont("", 19, QFont.Weight.Bold))
        brand_row.addWidget(title)
        brand_row.addStretch(1)
        layout.addLayout(brand_row)

        hint = QLabel("Вставь ссылку, выбери язык, жми «Скачать». Текст уйдёт в буфер.")
        hint.setProperty("muted", True)
        layout.addWidget(hint)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://youtube.com/watch?v=...")
        self.url_input.setMinimumHeight(42)
        layout.addWidget(self.url_input)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Язык:"))
        self.ru_btn = QPushButton("RU")
        self.ru_btn.setProperty("segmented", True)
        self.en_btn = QPushButton("EN")
        self.en_btn.setProperty("segmented", True)
        self.ru_btn.clicked.connect(lambda: self._set_lang("ru"))
        self.en_btn.clicked.connect(lambda: self._set_lang("en"))
        lang_row.addWidget(self.ru_btn)
        lang_row.addWidget(self.en_btn)
        lang_row.addStretch()
        layout.addLayout(lang_row)
        self._set_lang("ru")

        self.download_status = QLabel("Статус: ожидание ссылки…")
        self.download_status.setWordWrap(True)
        self.download_status.setProperty("muted", True)
        self.download_status.setProperty("status_bar", True)
        layout.addWidget(self.download_status)

        self.cancel_busy_btn = QPushButton("✕ Отмена")
        self.cancel_busy_btn.setProperty("fallback", True)
        self.cancel_busy_btn.setToolTip("Остановить скачивание субтитров или аудио")
        self.cancel_busy_btn.clicked.connect(self.on_cancel_download)
        self.cancel_busy_btn.setVisible(False)
        layout.addWidget(self.cancel_busy_btn)

        btn_row = QHBoxLayout()
        self.download_btn = QPushButton("Скачать")
        self.download_btn.clicked.connect(self.on_download)
        apply_primary_glow(self.download_btn)
        btn_row.addWidget(self.download_btn)

        self.audio_btn = QPushButton("🎵 Музыка")
        self.audio_btn.setProperty("fallback", True)
        self.audio_btn.setToolTip("Скачать аудио (MP3) в Music\\YouTube_DL")
        self.audio_btn.clicked.connect(self.on_download_audio)
        btn_row.addWidget(self.audio_btn)

        self.overlay_btn = QPushButton("🎞 Фон")
        self.overlay_btn.setProperty("fallback", True)
        self.overlay_btn.setToolTip(
            "Overlay: каталог музыки/mp4 поверх окон (прозрачность + клики насквозь). Ctrl+Shift+O"
        )
        self.overlay_btn.clicked.connect(self.on_open_overlay)
        btn_row.addWidget(self.overlay_btn)

        self.player_btn = QPushButton("Плеер")
        self.player_btn.clicked.connect(self.on_open_player)
        apply_primary_glow(self.player_btn)
        btn_row.addWidget(self.player_btn)

        self.bookmarks_btn = QPushButton("🔖 Закладки")
        self.bookmarks_btn.setProperty("fallback", True)
        self.bookmarks_btn.setToolTip("Частые сайты (аниме и т.д.)")
        self.bookmarks_btn.clicked.connect(self.show_bookmarks_view)
        btn_row.addWidget(self.bookmarks_btn)

        self.clear_btn = QPushButton("Очистить")
        self.clear_btn.setProperty("fallback", True)
        self.clear_btn.clicked.connect(self.on_clear)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        self._disable_space_button_activate(
            self.ru_btn,
            self.en_btn,
            self.cancel_busy_btn,
            self.download_btn,
            self.audio_btn,
            self.overlay_btn,
            self.player_btn,
            self.bookmarks_btn,
            self.clear_btn,
        )
        return page

    def _build_player_view(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Одна строка chrome; Инвест/Обычный — в шапке сайдбара
        # Обёртка — чтобы в immersive спрятать панель целиком
        self.player_chrome_row1 = QWidget()
        row1 = QHBoxLayout(self.player_chrome_row1)
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)
        self.back_btn = QPushButton("← Назад")
        self.back_btn.setProperty("fallback", True)
        self.back_btn.setToolTip("К экрану скачивания")
        self.back_btn.clicked.connect(self.show_download_view)
        row1.addWidget(self.back_btn)

        self.theater_btn = QPushButton("⛶")
        self.theater_btn.setProperty("fallback", True)
        self.theater_btn.setToolTip(self._theater_btn_tooltip_idle())
        self.theater_btn.clicked.connect(self._toggle_player_theater)
        row1.addWidget(self.theater_btn)

        self.analyze_btn = QPushButton("📥")
        self.analyze_btn.setProperty("fallback", True)
        self.analyze_btn.setToolTip(
            "Скачать / обновить субтитры текущего ролика (без ИИ)"
        )
        self.analyze_btn.clicked.connect(self.on_analyze_current_video)
        row1.addWidget(self.analyze_btn)

        self.player_title = QLabel("Плеер таймкодов")
        self.player_title.setProperty("player_title", True)
        self.player_title.setFont(QFont("", 12, QFont.Weight.DemiBold))
        self.player_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player_title.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._player_title_full = "Плеер таймкодов"
        row1.addWidget(self.player_title, 1)

        self.ai_btn = QPushButton("✨ ИИ")
        self.ai_btn.setToolTip(
            "ИИ-разбор текущего ролика в плеере (по URL WebView)"
        )
        self.ai_btn.clicked.connect(self.on_ai_analyze)
        apply_primary_glow(self.ai_btn, strong=True)
        row1.addWidget(self.ai_btn)

        self.player_audio_btn = QPushButton("🎵")
        self.player_audio_btn.setProperty("fallback", True)
        self.player_audio_btn.setToolTip("Скачать аудио текущего видео (MP3)")
        self.player_audio_btn.clicked.connect(self.on_download_audio_from_player)
        row1.addWidget(self.player_audio_btn)

        self.dist_files_btn = QPushButton("📁")
        self.dist_files_btn.setProperty("fallback", True)
        self.dist_files_btn.setToolTip(
            "Субтитры в dist/: смотреть txt и копировать (без проводника)"
        )
        self.dist_files_btn.clicked.connect(self.on_open_dist_files)
        row1.addWidget(self.dist_files_btn)

        self.player_cancel_btn = QPushButton("✕ Отмена")
        self.player_cancel_btn.setProperty("fallback", True)
        self.player_cancel_btn.setMinimumWidth(96)
        self.player_cancel_btn.setToolTip("Отменить скачивание")
        self.player_cancel_btn.clicked.connect(self.on_cancel_download)
        self.player_cancel_btn.setVisible(False)
        row1.addWidget(self.player_cancel_btn)

        self.login_btn = QPushButton("Войти")
        self.login_btn.setProperty("fallback", True)
        self.login_btn.setToolTip("Войти в YouTube / назад к видео")
        self._login_mode = False  # False=войти, True=назад к видео
        self.login_btn.clicked.connect(self._login_btn_clicked)
        # Кнопка «Войти» убрана из UI (логин через cookies/профиль при необходимости)
        self.login_btn.hide()
        self._refresh_login_btn_visibility()
        layout.addWidget(self.player_chrome_row1)

        self._player_page_layout = layout

        self.player_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.player_splitter.setHandleWidth(6)
        self.player_splitter.setStyleSheet(
            "QSplitter::handle { background: #2a3548; border-radius: 3px; }"
        )

        video_card = QFrame()
        video_card.setProperty("card", True)
        self._player_video_card = video_card
        video_layout = QVBoxLayout(video_card)
        self._player_video_layout = video_layout
        video_layout.setContentsMargins(8, 8, 8, 8)
        # Постоянный профиль — куки YouTube сохраняются между запусками
        profile_path = webengine_profile_dir("yt_profile")
        self._yt_profile = QWebEngineProfile("yt_player", self)
        self._yt_profile.setPersistentStoragePath(profile_path)
        self._yt_profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        settings = self._yt_profile.settings()
        # Не автоплеить при загрузке страницы — только по жесту (▶ / seek / клик).
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, True
        )

        self.web_view = QWebEngineView()
        _SafePage = _make_safe_page_class(_YT_NAV_HOSTS)
        self._yt_page = _SafePage(self._yt_profile, self.web_view)
        self.web_view.setPage(self._yt_page)
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.web_view.loadFinished.connect(self._on_webview_loaded)
        video_layout.addWidget(self.web_view)

        self.load_video_btn = QPushButton("▶ Загрузить видео")
        self.load_video_btn.setProperty("fallback", True)
        self.load_video_btn.setToolTip(
            "YouTube не грузится сам при открытии плеера — только по кнопке"
        )
        self.load_video_btn.clicked.connect(self.on_load_player_video)
        video_layout.addWidget(self.load_video_btn)

        sidebar = QFrame()
        sidebar.setProperty("card", True)
        self.player_sidebar = sidebar
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(6)

        self.ai_mode_bar = QWidget()
        mode_row = QHBoxLayout(self.ai_mode_bar)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(6)
        mode_lbl = QLabel("ИИ:")
        mode_lbl.setProperty("muted", True)
        mode_row.addWidget(mode_lbl)

        self.ai_invest_btn = QPushButton("Инвест")
        self.ai_invest_btn.setProperty("segmented", True)
        self.ai_invest_btn.setProperty("ai_mode", True)
        self.ai_invest_btn.setProperty("selected", True)
        self.ai_invest_btn.setToolTip("Режим ИИ: инвест-фильтр (чекпоинт)")
        self.ai_invest_btn.clicked.connect(lambda: self._set_ai_mode("invest"))
        mode_row.addWidget(self.ai_invest_btn)

        self.ai_general_btn = QPushButton("Обычный")
        self.ai_general_btn.setProperty("segmented", True)
        self.ai_general_btn.setProperty("ai_mode", True)
        self.ai_general_btn.setProperty("selected", False)
        self.ai_general_btn.setToolTip("Режим ИИ: обычный разбор")
        self.ai_general_btn.clicked.connect(lambda: self._set_ai_mode("general"))
        mode_row.addWidget(self.ai_general_btn)
        mode_row.addStretch()
        self.ai_mode_bar.setVisible(False)  # только после «✨ ИИ» / есть разбор
        sidebar_layout.addWidget(self.ai_mode_bar)
        self._ai_mode_lbl = mode_lbl

        # Карточка №3: без вкладок «ИИ-моменты» / «Все» — только текст разбора
        self.ai_summary = QTextBrowser()
        self.ai_summary.setObjectName("ai_summary")
        self.ai_summary.setOpenExternalLinks(False)
        self.ai_summary.setPlaceholderText(
            "Нажми «✨ ИИ» или открой ролик с сохранённым разбором"
        )
        sidebar_layout.addWidget(self.ai_summary, 1)

        self.player_splitter.addWidget(video_card)
        self.player_splitter.addWidget(sidebar)
        self.player_splitter.setStretchFactor(0, 4)
        self.player_splitter.setStretchFactor(1, 1)
        self.player_splitter.setSizes([800, 200])
        self._splitter_sizes_with_sidebar = [800, 200]

        # Справа: свернуть/развернуть панель (SVG, без слова «Разбор»)
        self.sidebar_toggle_btn = QPushButton()
        self.sidebar_toggle_btn.setProperty("sidebar_tab", True)
        self.sidebar_toggle_btn.setProperty("fallback", True)
        self.sidebar_toggle_btn.setToolTip("Панель разбора (R)")
        self.sidebar_toggle_btn.setIcon(_ui_svg_icon("panel_collapse", 18))
        self.sidebar_toggle_btn.setIconSize(QSize(18, 18))
        self.sidebar_toggle_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self.sidebar_toggle_btn.clicked.connect(self._toggle_player_sidebar)

        split_row = QWidget()
        split_row_layout = QHBoxLayout(split_row)
        split_row_layout.setContentsMargins(0, 0, 0, 0)
        split_row_layout.setSpacing(4)
        split_row_layout.addWidget(self.player_splitter, 1)
        split_row_layout.addWidget(self.sidebar_toggle_btn)
        layout.addWidget(split_row, 1)

        self._set_ai_mode("invest")
        self._sync_sidebar_toggle_btn()
        self._disable_space_button_activate(
            self.back_btn,
            self.theater_btn,
            self.analyze_btn,
            self.ai_btn,
            self.load_video_btn,
            self.player_audio_btn,
            self.dist_files_btn,
            self.player_cancel_btn,
            self.login_btn,
            self.ai_invest_btn,
            self.ai_general_btn,
            self.sidebar_toggle_btn,
        )

        self._theater_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), page)
        self._theater_esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._theater_esc.activated.connect(self._on_theater_escape)
        # F = theater (приложение); F11 — то же полномасштабное
        self._theater_f = QShortcut(QKeySequence(Qt.Key.Key_F), page)
        self._theater_f.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._theater_f.activated.connect(self._on_theater_hotkey)
        self._theater_f11 = QShortcut(QKeySequence(Qt.Key.Key_F11), self)
        self._theater_f11.activated.connect(self._toggle_os_fullscreen)
        # R = свернуть/показать правую панель (в окне, не fullscreen)
        self._sidebar_r = QShortcut(QKeySequence(Qt.Key.Key_R), page)
        self._sidebar_r.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sidebar_r.activated.connect(self._on_sidebar_hotkey)

        self.player_status = QLabel("Статус: открой ролик через кнопку «Плеер».")
        self.player_status.setProperty("muted", True)
        self.player_status.setProperty("status_bar", True)
        layout.addWidget(self.player_status)
        self._theater_hide_widgets = (
            self.player_chrome_row1,
            self.sidebar_toggle_btn,
            self.player_status,
        )
        return page

    def _build_bookmarks_view(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.bookmarks_back_btn = QPushButton("← Назад")
        self.bookmarks_back_btn.setProperty("fallback", True)
        self.bookmarks_back_btn.clicked.connect(self.show_download_view)
        top.addWidget(self.bookmarks_back_btn)

        title = QLabel("Закладки")
        title.setFont(QFont("", 14, QFont.Weight.DemiBold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addStretch()
        top.addWidget(title)
        top.addStretch()
        layout.addLayout(top)

        self.bookmarks_tabs = QTabWidget()
        self.bookmarks_tabs.setDocumentMode(True)
        for item in self._bookmarks:
            self.bookmarks_tabs.addTab(QWidget(), item["title"])
        self.bookmarks_tabs.currentChanged.connect(self._on_bookmark_tab_changed)
        layout.addWidget(self.bookmarks_tabs)

        self.bookmarks_content_stack = QStackedWidget()

        web_card = QFrame()
        web_card.setProperty("card", True)
        web_layout = QVBoxLayout(web_card)
        web_layout.setContentsMargins(8, 8, 8, 8)

        profile_path = webengine_profile_dir("bookmarks_profile")
        self._bookmarks_profile = QWebEngineProfile("bookmarks", self)
        self._bookmarks_profile.setPersistentStoragePath(profile_path)
        self._bookmarks_profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self._bookmarks_profile.setHttpUserAgent(_bookmarks_user_agent())
        self._bookmarks_profile.setHttpAcceptLanguage("ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7")
        # Client Hints — Cloudflare часто валит WebEngine из‑за пустых UA-CH
        try:
            hints = self._bookmarks_profile.clientHints()
            hints.setPlatform("Windows")
            hints.setArchitecture("x86")
            hints.setBitness("64")
            hints.setMobile(False)
        except Exception:
            pass
        bm_settings = self._bookmarks_profile.settings()
        for attr, on in (
            (QWebEngineSettings.WebAttribute.JavascriptEnabled, True),
            (QWebEngineSettings.WebAttribute.LocalStorageEnabled, True),
            # Soft-WebGL в Qt часто триггерит Turnstile «Verification failed»
            (QWebEngineSettings.WebAttribute.WebGLEnabled, False),
            (QWebEngineSettings.WebAttribute.PluginsEnabled, True),
            (QWebEngineSettings.WebAttribute.AutoLoadImages, True),
            (QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False),
            (QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True),
            (QWebEngineSettings.WebAttribute.DnsPrefetchEnabled, True),
        ):
            try:
                bm_settings.setAttribute(attr, on)
            except Exception:
                pass

        self.bookmarks_web_view = QWebEngineView()
        _BmSafePage = _make_safe_page_class(bookmark_allowed_hosts(self._bookmarks))
        self._bookmarks_page = _BmSafePage(self._bookmarks_profile, self.bookmarks_web_view)
        self.bookmarks_web_view.setPage(self._bookmarks_page)
        self.bookmarks_web_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.bookmarks_web_view.loadFinished.connect(self._on_bookmarks_web_loaded)
        self.bookmarks_web_view.loadProgress.connect(self._on_bookmarks_load_progress)
        self.bookmarks_web_view.urlChanged.connect(self._on_bookmarks_url_changed)
        web_layout.addWidget(self.bookmarks_web_view)
        self.bookmarks_content_stack.addWidget(web_card)

        self.history_panel = QFrame()
        self.history_panel.setProperty("card", True)
        history_layout = QVBoxLayout(self.history_panel)
        history_layout.setContentsMargins(8, 8, 8, 8)
        hist_hint = QLabel("Недавно открытые страницы (только в закладках WebView)")
        hist_hint.setProperty("muted", True)
        hist_hint.setWordWrap(True)
        history_layout.addWidget(hist_hint)
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_inner = QWidget()
        self.history_layout = QVBoxLayout(self.history_inner)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(6)
        self.history_scroll.setWidget(self.history_inner)
        history_layout.addWidget(self.history_scroll)
        self.bookmarks_content_stack.addWidget(self.history_panel)

        layout.addWidget(self.bookmarks_content_stack, 1)

        self._history_tab_index = self.bookmarks_tabs.addTab(QWidget(), "📜 История")

        status_row = QHBoxLayout()
        self.bookmarks_status = QLabel("Выбери вкладку закладки")
        self.bookmarks_status.setProperty("muted", True)
        status_row.addWidget(self.bookmarks_status, 1)

        self.bookmarks_open_browser_btn = QPushButton("Открыть в Chrome")
        self.bookmarks_open_browser_btn.setProperty("fallback", True)
        self.bookmarks_open_browser_btn.setToolTip(
            "Открыть в Chrome/Edge (окно приложения). "
            "Нужно, если Cloudflare блокирует встроенный браузер."
        )
        self.bookmarks_open_browser_btn.clicked.connect(self._open_bookmark_in_browser)
        status_row.addWidget(self.bookmarks_open_browser_btn)
        layout.addLayout(status_row)

        self._bookmarks_current_url = ""
        if self.bookmarks_tabs.count() > 0:
            self.bookmarks_tabs.setCurrentIndex(0)

        self._disable_space_button_activate(
            self.bookmarks_back_btn,
            self.bookmarks_open_browser_btn,
        )
        return page

    def _set_lang(self, lang_code: str) -> None:
        self._lang_code = lang_code
        self.ru_btn.setProperty("selected", lang_code == "ru")
        self.en_btn.setProperty("selected", lang_code == "en")
        self.ru_btn.style().unpolish(self.ru_btn)
        self.ru_btn.style().polish(self.ru_btn)
        self.en_btn.style().unpolish(self.en_btn)
        self.en_btn.style().polish(self.en_btn)

    def _set_ai_mode(self, mode: str) -> None:
        self._ai_mode = "invest" if mode == "invest" else "general"
        self.ai_invest_btn.setProperty("selected", self._ai_mode == "invest")
        self.ai_general_btn.setProperty("selected", self._ai_mode == "general")
        for btn in (self.ai_invest_btn, self.ai_general_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

    def _set_ai_mode_bar_visible(self, visible: bool) -> None:
        """Инвест/Обычный — только когда идёт/есть разбор, иначе пустой сайдбар."""
        if hasattr(self, "ai_mode_bar"):
            self.ai_mode_bar.setVisible(bool(visible))

    def _polish_btn(self, btn: QPushButton) -> None:
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn.update()

    def _sync_cancel_buttons(self) -> None:
        """Показать ✕ Отмена при скачивании или ИИ; стиль/tooltip по контексту."""
        show = self._busy or self._ai_busy
        ai_ctx = self._ai_busy and not self._busy

        if hasattr(self, "cancel_busy_btn"):
            self.cancel_busy_btn.setVisible(show)
            if show:
                tip = (
                    "Отменить ИИ-разбор"
                    if ai_ctx
                    else "Остановить скачивание субтитров или аудио"
                )
                self.cancel_busy_btn.setToolTip(tip)
                self.cancel_busy_btn.setProperty("cancel_busy", ai_ctx or self._busy)
                self._polish_btn(self.cancel_busy_btn)

        if hasattr(self, "player_cancel_btn"):
            self.player_cancel_btn.setVisible(show)
            if show:
                self.player_cancel_btn.setText("✕ Отмена")
                self.player_cancel_btn.setMinimumWidth(96)
                self.player_cancel_btn.setProperty("compact", False)
                self.player_cancel_btn.setProperty("cancel_busy", True)
                tip = (
                    "Отменить ИИ-разбор"
                    if ai_ctx
                    else "Отменить скачивание"
                )
                self.player_cancel_btn.setToolTip(tip)
                self._polish_btn(self.player_cancel_btn)
            else:
                self.player_cancel_btn.setProperty("cancel_busy", False)
                self.player_cancel_btn.setProperty("compact", True)
                self.player_cancel_btn.setToolTip("Отменить скачивание")
                self._polish_btn(self.player_cancel_btn)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (
            self.download_btn,
            self.audio_btn,
            self.player_btn,
            self.bookmarks_btn,
            self.clear_btn,
            self.ru_btn,
            self.en_btn,
        ):
            widget.setDisabled(busy)
        if hasattr(self, "player_audio_btn"):
            self.player_audio_btn.setDisabled(busy)
        if hasattr(self, "analyze_btn"):
            self.analyze_btn.setDisabled(busy)
        self.url_input.setDisabled(busy)
        self.download_btn.setProperty("motion_busy", busy)
        self._polish_btn(self.download_btn)
        self._sync_cancel_buttons()
        if busy:
            self._cancel_event.clear()
            self._busy_t0 = time.monotonic()
            self._busy_timer.start()
            self._pulse_download.start()
        else:
            self._busy_timer.stop()
            self._busy_t0 = None
            self._cancel_context = ""
            self._pulse_download.stop()
            self._paint_download_status()

    def _begin_download_task(self, context: str) -> None:
        """context: download | player_subs | audio | audio_player"""
        self._cancel_context = context
        self._cancel_event.clear()

    def on_cancel_download(self) -> None:
        """Единая отмена: ИИ (если _ai_busy) иначе скачивание (если _busy)."""
        if self._ai_busy:
            self._ai_cancel_event.set()
            self._ai_job_id += 1  # инвалидация позднего ответа
            self._set_player_status_core("ИИ: отмена…")
            return
        if not self._busy:
            return
        self._cancel_event.set()
        msg = "Отмена…"
        if self._cancel_context.startswith("audio"):
            if "player" in self._cancel_context:
                self._set_player_status_core(msg)
            else:
                self._set_status(msg)
        elif self._cancel_context == "player_subs":
            self._set_player_status_core(msg)
        else:
            self._set_status(msg)

    def _set_status(self, text: str) -> None:
        self._status_core = text
        self._paint_download_status()

    def _paint_download_status(self) -> None:
        extra = ""
        if self._busy and self._busy_t0 is not None:
            extra = f"\n⏱ {int(time.monotonic() - self._busy_t0)}с"
        self.download_status.setText(self._status_core + extra)

    def _refresh_busy_clock(self) -> None:
        self._paint_download_status()

    def _set_player_status(self, text: str) -> None:
        self._set_player_status_core(text)

    def _set_player_status_core(self, text: str) -> None:
        self._player_status_core = text
        self._paint_player_status()

    def _paint_player_status(self) -> None:
        extra = ""
        if self._ai_busy and self._ai_busy_t0 is not None:
            extra = f"\n⏱ {int(time.monotonic() - self._ai_busy_t0)}с"
        self.player_status.setText(self._player_status_core + extra)

    def _refresh_ai_busy_clock(self) -> None:
        self._paint_player_status()

    def _set_ai_busy(self, busy: bool) -> None:
        self._ai_busy = busy
        self.ai_btn.setDisabled(busy)
        self.ai_btn.setProperty("motion_busy", busy)
        self._polish_btn(self.ai_btn)
        if hasattr(self, "analyze_btn"):
            self.analyze_btn.setDisabled(busy or self._busy)
        if busy:
            self.ai_btn.setText("ИИ…")
            self._ai_busy_t0 = time.monotonic()
            self._ai_busy_timer.start()
            self._pulse_ai.start()
        else:
            self.ai_btn.setText("✨ ИИ")
            self._ai_busy_timer.stop()
            self._ai_busy_t0 = None
            self._pulse_ai.stop()
            self._paint_player_status()
        self._sync_cancel_buttons()

    def _toggle_player_theater(self) -> None:
        """Полномасштабный режим: весь монитор + без панелей (⛶ / F)."""
        if self.isFullScreen() or self._player_theater:
            self._exit_immersive_playback()
        else:
            self._enter_immersive_playback()

    def _on_theater_hotkey(self) -> None:
        """F — immersive fullscreen; только на экране плеера."""
        if self.stack.currentWidget() is not self.player_view:
            return
        self._toggle_player_theater()

    def _on_sidebar_hotkey(self) -> None:
        """R — свернуть/показать панель разбора; только на экране плеера, не в theater."""
        if self.stack.currentWidget() is not self.player_view:
            return
        if self._player_theater or self.isFullScreen():
            return
        self._toggle_player_sidebar()

    def _toggle_player_sidebar(self) -> None:
        """В окне: спрятать/вернуть правую панель (видео шире), не theater."""
        if self._player_theater or self.isFullScreen():
            return
        if self.stack.currentWidget() is not self.player_view:
            return
        if self._sidebar_collapsed:
            self._set_sidebar_collapsed(False)
        else:
            self._set_sidebar_collapsed(True)

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            sizes = self.player_splitter.sizes()
            if len(sizes) >= 2 and sizes[1] > 40:
                self._splitter_sizes_with_sidebar = sizes
            # maximumWidth(0) надёжнее hide: QSplitter иначе «держит» дыру
            self.player_sidebar.setMinimumWidth(0)
            self.player_sidebar.setMaximumWidth(0)
            self.player_sidebar.hide()
            self._sidebar_collapsed = True
        else:
            self.player_sidebar.setMaximumWidth(16777215)
            self.player_sidebar.setMinimumWidth(0)
            self.player_sidebar.show()
            self._sidebar_collapsed = False
            restore = self._splitter_sizes_with_sidebar or [800, 200]
            self.player_splitter.setSizes(restore)
        self._sync_sidebar_toggle_btn()
        # Chromium WebView часто не подхватывает ширину с первого кадра
        self._nudge_player_split_layout()
        QTimer.singleShot(0, self._nudge_player_split_layout)
        QTimer.singleShot(40, self._nudge_player_split_layout)
        QTimer.singleShot(120, self._nudge_player_split_layout)

    def _nudge_player_split_layout(self) -> None:
        """Заставить splitter + WebEngine пересчитать геометрию."""
        if not hasattr(self, "player_splitter"):
            return
        sp = self.player_splitter
        total = max(sp.width(), 1)
        if self._sidebar_collapsed:
            sp.setSizes([total, 0])
        elif self.player_sidebar.isVisible():
            cur = sp.sizes()
            if len(cur) >= 2 and cur[1] < 40:
                restore = self._splitter_sizes_with_sidebar or [800, 200]
                s0, s1 = restore[0], restore[1]
                ratio = s0 / max(s0 + s1, 1)
                left = max(1, int(total * ratio))
                sp.setSizes([left, max(1, total - left)])
        if hasattr(self, "web_view"):
            w = self.web_view
            s = w.size()
            if s.width() > 0 and s.height() > 0:
                w.resize(s.width() + 1, s.height())
                w.resize(s)
            w.updateGeometry()
            w.update()
        sp.updateGeometry()
        sp.update()

    def _sync_sidebar_toggle_btn(self) -> None:
        if not hasattr(self, "sidebar_toggle_btn"):
            return
        if self._sidebar_collapsed:
            self.sidebar_toggle_btn.setIcon(_ui_svg_icon("panel_expand", 18))
            self.sidebar_toggle_btn.setToolTip("Показать панель разбора (R)")
        else:
            self.sidebar_toggle_btn.setIcon(_ui_svg_icon("panel_collapse", 18))
            self.sidebar_toggle_btn.setToolTip("Свернуть панель разбора (R)")
        self.sidebar_toggle_btn.setIconSize(QSize(18, 18))
        self.sidebar_toggle_btn.setText("")

    def _theater_btn_tooltip_idle(self) -> str:
        return (
            "Полный экран (F / ⛶) — видео на весь монитор · Esc — выход · "
            "F11 — то же"
        )

    def _set_immersive_chrome(self, on: bool) -> None:
        """Убрать/вернуть отступы и панели — чтобы WebView был edge-to-edge."""
        root_layout = self.centralWidget().layout() if self.centralWidget() else None
        if on:
            if root_layout is not None:
                root_layout.setContentsMargins(0, 0, 0, 0)
            if hasattr(self, "_player_page_layout"):
                self._player_page_layout.setContentsMargins(0, 0, 0, 0)
                self._player_page_layout.setSpacing(0)
            if hasattr(self, "_player_video_layout"):
                self._player_video_layout.setContentsMargins(0, 0, 0, 0)
            if hasattr(self, "_player_video_card"):
                self._player_video_card.setProperty("card", False)
                self._player_video_card.setStyleSheet(
                    "QFrame { background: #000; border: none; border-radius: 0; }"
                )
        else:
            if root_layout is not None:
                root_layout.setContentsMargins(16, 16, 16, 16)
            if hasattr(self, "_player_page_layout"):
                self._player_page_layout.setContentsMargins(0, 0, 0, 0)
                self._player_page_layout.setSpacing(8)
            if hasattr(self, "_player_video_layout"):
                self._player_video_layout.setContentsMargins(8, 8, 8, 8)
            if hasattr(self, "_player_video_card"):
                self._player_video_card.setProperty("card", True)
                self._player_video_card.setStyleSheet("")
                self._player_video_card.style().unpolish(self._player_video_card)
                self._player_video_card.style().polish(self._player_video_card)

    def _enter_immersive_playback(self) -> None:
        if self._player_theater and self.isFullScreen():
            return
        if self.stack.currentWidget() is not self.player_view:
            return
        if not self._player_theater:
            # Сохранить ширины до theater; не затирать «с сайдбаром», если уже свёрнут
            sizes = self.player_splitter.sizes()
            self._splitter_sizes_normal = sizes
            if not self._sidebar_collapsed and len(sizes) >= 2 and sizes[1] > 40:
                self._splitter_sizes_with_sidebar = sizes
            self.player_sidebar.setVisible(False)
            for widget in self._theater_hide_widgets:
                widget.setVisible(False)
            self._player_theater = True
        self._set_immersive_chrome(True)
        self.theater_btn.setToolTip("Выйти из полного экрана (Esc / F / F11)")
        if not self.isFullScreen():
            self.showFullScreen()
        # Best-effort: HTML5 video fullscreen внутри Chromium
        QTimer.singleShot(200, self._try_html_video_fullscreen)

    def _try_html_video_fullscreen(self) -> None:
        if not self._player_theater or not hasattr(self, "web_view"):
            return
        self.web_view.page().runJavaScript(
            """
            (function(){
              try {
                var v = document.querySelector('video');
                if (!v) return 'no-video';
                if (document.fullscreenElement) return 'already';
                var req = v.requestFullscreen || v.webkitRequestFullscreen;
                if (req) { req.call(v); return 'ok'; }
                return 'no-api';
              } catch (e) { return 'err:' + e; }
            })();
            """
        )

    def _exit_html_video_fullscreen(self) -> None:
        if not hasattr(self, "web_view"):
            return
        self.web_view.page().runJavaScript(
            """
            (function(){
              try {
                if (document.fullscreenElement) {
                  var ex = document.exitFullscreen || document.webkitExitFullscreen;
                  if (ex) ex.call(document);
                }
              } catch (e) {}
            })();
            """
        )

    def _enter_player_theater(self) -> None:
        """Совместимость: театр = immersive fullscreen."""
        self._enter_immersive_playback()

    def _exit_player_theater(self, *, force: bool = False) -> None:
        if not self._player_theater and not force:
            return
        self._exit_html_video_fullscreen()
        if self.isFullScreen():
            self.showNormal()
            self._ensure_window_on_screen()
            QTimer.singleShot(0, self._ensure_window_on_screen)
        self._set_immersive_chrome(False)
        for widget in self._theater_hide_widgets:
            widget.setVisible(True)
        # Уважаем свёрнутый сайдбар: не форсим панель обратно
        if self._sidebar_collapsed:
            self.player_sidebar.setMinimumWidth(0)
            self.player_sidebar.setMaximumWidth(0)
            self.player_sidebar.setVisible(False)
            total = sum(self._splitter_sizes_normal or [1000, 0]) or 1000
            self.player_splitter.setSizes([total, 0])
        else:
            self.player_sidebar.setMaximumWidth(16777215)
            self.player_sidebar.setMinimumWidth(0)
            self.player_sidebar.setVisible(True)
            restore = (
                self._splitter_sizes_with_sidebar
                or self._splitter_sizes_normal
                or [800, 200]
            )
            self.player_splitter.setSizes(restore)
        self._sync_sidebar_toggle_btn()
        self._nudge_player_split_layout()
        QTimer.singleShot(40, self._nudge_player_split_layout)
        self._player_theater = False
        self.theater_btn.setToolTip(self._theater_btn_tooltip_idle())

    def _exit_immersive_playback(self) -> None:
        self._exit_player_theater(force=True)

    def _on_theater_escape(self) -> None:
        if self.isFullScreen() or self._player_theater:
            self._exit_immersive_playback()

    def _toggle_os_fullscreen(self) -> None:
        """F11 — тот же полномасштабный режим, что ⛶ / F."""
        if self.stack.currentWidget() is not self.player_view:
            return
        self._toggle_player_theater()

    def _build_ai_summary_html(self, analysis: dict) -> str:
        """HTML разбора для сайдбара плеера."""
        mode = analysis.get("mode") or "general"
        kind = analysis.get("content_kind") or mode
        e = html.escape
        verdict = e(str(analysis.get("verdict_1_line") or "").strip())
        summary = e(str(analysis.get("summary") or "").strip())
        action = e(str(analysis.get("action") or "").strip())
        fit = e(str(analysis.get("checkpoint_fit") or "").strip())
        link = e(str(analysis.get("portfolio_link") or "").strip())
        facts = analysis.get("facts_usable") or []
        ignore = analysis.get("opinions_ignore") or []
        flags = analysis.get("red_flags_seen") or []
        verify = analysis.get("verify_list") or analysis.get("verify") or []
        assets = analysis.get("assets") or []
        claims = analysis.get("claims") or []
        takeaways = analysis.get("takeaways") or []
        holds_up = e(str(analysis.get("holds_up") or "").strip())
        framing = e(str(analysis.get("framing") or "").strip())
        thinking = e(str(analysis.get("what_it_changes_in_thinking") or "").strip())

        def _ul(title: str, items: list) -> str:
            if not items:
                return ""
            bullets = "".join(f"<li>{e(str(t))}</li>" for t in items)
            return f"<b>{title}</b><ul>{bullets}</ul>"

        parts: list[str] = []
        if mode == "invest":
            kind_ru = "образовалка" if kind == "educational" else "инвест/сигналы"
            parts.append(f"<b>Инвест-фильтр</b> · {kind_ru}")
            if verdict:
                parts.append(f"<b>Вердикт</b><br/>{verdict}")
            meta = []
            if action:
                meta.append(f"action: <b>{action}</b>")
            if fit:
                meta.append(f"checkpoint: {fit}")
            if link:
                meta.append(f"portfolio: {link}")
            if meta:
                parts.append(" · ".join(meta))
            if assets:
                parts.append(
                    "<b>Активы из текста</b><br/>"
                    + ", ".join(e(str(a)) for a in assets)
                )
            for title, items in (
                ("Факты (usable)", facts),
                ("Тезисы автора", claims),
                ("Красные флаги", flags),
                ("Игнор", ignore),
                ("Сверить в первичке", verify),
                ("Takeaways", takeaways),
            ):
                block = _ul(title, items)
                if block:
                    parts.append(block)
            if kind == "educational":
                if holds_up:
                    parts.append(f"<b>Держится ли рамка</b><br/>{holds_up}")
                if framing:
                    parts.append(f"<b>Рамка</b><br/>{framing}")
                if thinking:
                    parts.append(f"<b>На что влияет мышление</b><br/>{thinking}")
        else:
            parts.append("<b>Обычный разбор</b>")
            if verdict:
                parts.append(f"<b>Вердикт</b><br/>{verdict}")
            if summary and summary != verdict:
                parts.append(f"<b>Вывод</b><br/>{summary.replace(chr(10), '<br/>')}")
            block = _ul("Что уяснить", takeaways)
            if block:
                parts.append(block)
            block = _ul("Игнор", ignore)
            if block:
                parts.append(block)

        body = "<br/><br/>".join(parts) if parts else "<i>Пустой ответ ИИ</i>"
        return f'<div style="line-height:1.45;">{body}</div>'

    def _apply_ai_analysis(self, analysis: dict) -> None:
        """Показывает текст разбора в сайдбаре (без вкладок моментов)."""
        self._last_ai_analysis = analysis
        mode = analysis.get("mode")
        if mode in ("invest", "general"):
            self._set_ai_mode(str(mode))
        self._set_ai_mode_bar_visible(True)
        self.ai_summary.setHtml(self._build_ai_summary_html(analysis))

    def _fill_ai_analysis(self, analysis: dict) -> None:
        """Показывает вывод ИИ (после API)."""
        self._apply_ai_analysis(analysis)

    def on_clear(self) -> None:
        if self._busy:
            return
        self.url_input.clear()
        self._set_status("Статус: ожидание ссылки…")

    def _unload_player(self) -> None:
        """Гасит WebView: стоп видео/сеть. Куки в yt_profile остаются."""
        if not hasattr(self, "web_view"):
            return
        # Быстро глушим звук до blank — иначе Chromium может ещё секунду играть
        try:
            self.web_view.page().runJavaScript(
                "try{var v=document.querySelector('video');"
                "if(v){v.pause();v.src='';v.load();}"
                "window.stop();}catch(e){}"
            )
        except Exception:
            pass
        self.web_view.setUrl(QUrl("about:blank"))
        self._player_video_loaded = False
        self._pending_seek_seconds = None
        if hasattr(self, "load_video_btn"):
            self.load_video_btn.setVisible(True)
            self.load_video_btn.setEnabled(True)
            self.load_video_btn.setText("▶ Загрузить видео")
        self._login_mode = False
        if hasattr(self, "login_btn"):
            self.login_btn.setText("Войти")
            self.login_btn.setToolTip("Войти в YouTube")
            self._refresh_login_btn_visibility()

    def show_download_view(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        self._exit_player_theater(force=True)
        self._unload_player()
        # Закладки не гасим — иначе каждый возврат = полная перезагрузка сайта
        self.stack.setCurrentWidget(self.download_view)
        self._lock_download_window_size()

    def show_player_view(self) -> None:
        from_download = self._is_download_view_active()
        # Закладки не гасим: иначе Aniwaves каждый раз заново ловит Cloudflare
        # Сначала переключить stack — иначе resize→moveEvent снова залочит download
        self.stack.setCurrentWidget(self.player_view)
        self._unlock_player_window_size(reset_geometry=from_download)
        self._refresh_login_btn_visibility()
        # Фокус в WebView — пробел = play/pause YouTube, не клик по кнопкам
        QTimer.singleShot(0, lambda: self.web_view.setFocus())

    def show_bookmarks_view(self) -> None:
        if self._busy:
            return
        if self.isFullScreen():
            self.showNormal()
            self._ensure_window_on_screen()
        from_download = self._is_download_view_active()
        self._exit_player_theater(force=True)
        self._unload_player()
        self.stack.setCurrentWidget(self.bookmarks_view)
        self._unlock_player_window_size(reset_geometry=from_download)
        if self.bookmarks_tabs.count() <= 1:
            self.bookmarks_status.setText("Нет закладок — добавь URL в bookmarks.json")
            return
        idx = self.bookmarks_tabs.currentIndex()
        if idx < 0:
            self.bookmarks_tabs.setCurrentIndex(0)
            idx = 0
        if idx >= len(self._bookmarks):
            self.bookmarks_content_stack.setCurrentWidget(self.history_panel)
            self._refresh_history_list()
            return
        self.bookmarks_content_stack.setCurrentWidget(
            self.bookmarks_content_stack.widget(0)
        )
        cur = self.bookmarks_web_view.url().toString()
        if cur in ("", "about:blank"):
            self._load_bookmark_at_index(idx)
        else:
            title = self._bookmarks[idx].get("title") or "закладку"
            self.bookmarks_status.setText(f"Загружено: {title} (из кэша)")

    def _on_bookmark_tab_changed(self, index: int) -> None:
        if index >= len(self._bookmarks):
            self.bookmarks_content_stack.setCurrentWidget(self.history_panel)
            self._refresh_history_list()
            return
        self.bookmarks_content_stack.setCurrentWidget(
            self.bookmarks_content_stack.widget(0)
        )
        item = self._bookmarks[index]
        want = str(item.get("url") or "")
        cur = self.bookmarks_web_view.url().toString()
        # Не дёргать CF заново, если уже на этом сайте (в т.ч. глубокая страница)
        if want and self._bookmark_same_site(cur, want):
            title = item.get("title") or "закладку"
            if not self._bookmarks_current_url or self._bookmarks_current_url.startswith(
                "about:"
            ):
                self._bookmarks_current_url = cur if cur and not cur.startswith("about:") else want
            self.bookmarks_status.setText(f"Загружено: {title}")
            return
        self._load_bookmark_at_index(index)

    @staticmethod
    def _bookmark_same_site(current: str, bookmark: str) -> bool:
        if not current or current.startswith("about:"):
            return False
        ch = (QUrl(current).host() or "").lower()
        bh = (QUrl(bookmark).host() or "").lower()
        if not ch or not bh:
            return False
        return ch == bh or ch.endswith("." + bh) or bh.endswith("." + ch)

    def _current_bookmark_open_url(self) -> str:
        """URL для «Открыть в Chrome»: текущая страница сайта, не CF-challenge."""
        idx = self.bookmarks_tabs.currentIndex()
        configured = ""
        if 0 <= idx < len(self._bookmarks):
            configured = str(self._bookmarks[idx].get("url") or "").strip()
        cur = (self._bookmarks_current_url or "").strip()
        if cur and not cur.startswith("about:"):
            host = (QUrl(cur).host() or "").lower()
            if "cloudflare" in host:
                return configured
            if configured:
                cfg_host = (QUrl(configured).host() or "").lower()
                if host and cfg_host and (
                    host == cfg_host
                    or host.endswith("." + cfg_host)
                    or cfg_host.endswith("." + host)
                ):
                    return cur
            # История / уже разрешённый URL
            return cur
        return configured

    def _on_bookmarks_load_progress(self, progress: int) -> None:
        if self.bookmarks_content_stack.currentWidget() is not self.bookmarks_content_stack.widget(0):
            return
        idx = self.bookmarks_tabs.currentIndex()
        if idx < 0 or idx >= len(self._bookmarks):
            return
        title = self._bookmarks[idx].get("title") or "страницу"
        if progress < 100:
            self.bookmarks_status.setText(f"Загружаю: {title} — {progress}%")
        elif progress == 100:
            self.bookmarks_status.setText(f"Загружаю: {title} — отрисовка…")

    def _on_bookmarks_url_changed(self, url: QUrl) -> None:
        s = url.toString()
        if s and not s.startswith("about:"):
            self._bookmarks_current_url = s

    def _record_bookmarks_history(self) -> None:
        url = self.bookmarks_web_view.url().toString()
        if not url or url.startswith("about:"):
            return

        def _save(title: str) -> None:
            append_bookmarks_history(url, str(title or url))
            if (
                self.bookmarks_tabs.currentIndex() >= len(self._bookmarks)
                and self.bookmarks_content_stack.currentWidget() is self.history_panel
            ):
                self._refresh_history_list()

        self.bookmarks_web_view.page().runJavaScript(
            "document.title || ''", _save
        )

    def _refresh_history_list(self) -> None:
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        items = load_bookmarks_history()
        if not items:
            empty = QLabel("Пока пусто — открой сайт во вкладке закладки")
            empty.setProperty("muted", True)
            empty.setWordWrap(True)
            self.history_layout.addWidget(empty)
            self.history_layout.addStretch()
            return
        for entry in items:
            url = str(entry.get("url") or "")
            title = str(entry.get("title") or url)
            ts = entry.get("ts")
            when = ""
            if isinstance(ts, (int, float)):
                when = time.strftime(" %d.%m %H:%M", time.localtime(ts))
            btn = QPushButton(f"{title}{when}")
            btn.setProperty("mark", True)
            btn.setToolTip(url)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.clicked.connect(lambda _=False, u=url: self._open_history_url(u))
            self.history_layout.addWidget(btn)
        self.history_layout.addStretch()

    def _open_history_url(self, url: str) -> None:
        if not url:
            return
        host = QUrl(url).host()
        allowed = bookmark_allowed_hosts(self._bookmarks)
        if not _nav_host_allowed(host, allowed):
            self.bookmarks_status.setText(
                f"Домен {host} не в whitelist — открой в Chrome"
            )
            return
        self.bookmarks_content_stack.setCurrentWidget(
            self.bookmarks_content_stack.widget(0)
        )
        for i, item in enumerate(self._bookmarks):
            if QUrl(str(item.get("url") or "")).host().lower() == host.lower():
                self.bookmarks_tabs.setCurrentIndex(i)
                break
        self._bookmarks_current_url = url
        self.bookmarks_status.setText(f"Загружаю из истории…")
        self.bookmarks_web_view.setUrl(QUrl(url))

    def _load_bookmark_at_index(self, index: int) -> None:
        if index < 0 or index >= len(self._bookmarks):
            return
        item = self._bookmarks[index]
        url = item.get("url") or ""
        if not url:
            return
        self._bookmarks_current_url = url
        self.bookmarks_status.setText(f"Загружаю: {item.get('title') or url}")
        self.bookmarks_web_view.setUrl(QUrl(url))

    def _on_bookmarks_web_loaded(self, ok: bool) -> None:
        idx = self.bookmarks_tabs.currentIndex()
        if ok:
            self._record_bookmarks_history()
            # Turnstile рисует fail с задержкой — проверяем сразу и ещё раз через пару секунд
            QTimer.singleShot(300, self._probe_bookmarks_cloudflare)
            QTimer.singleShot(2500, self._probe_bookmarks_cloudflare)
        if idx < 0 or idx >= len(self._bookmarks):
            if ok:
                self.bookmarks_status.setText("Загружено")
            else:
                self.bookmarks_status.setText(
                    "Не удалось загрузить — попробуй «Открыть в Chrome» или VPN"
                )
            return
        title = self._bookmarks[idx].get("title") or "закладку"
        if ok:
            self.bookmarks_status.setText(f"Загружено: {title}")
        else:
            self.bookmarks_status.setText(
                f"Не удалось загрузить {title} — попробуй «Открыть в Chrome» или VPN"
            )

    def _probe_bookmarks_cloudflare(self) -> None:
        if not hasattr(self, "bookmarks_web_view"):
            return
        if self.stack.currentWidget() is not self.bookmarks_view:
            return
        self.bookmarks_web_view.page().runJavaScript(
            """
            (function(){
              var t = (document.body && document.body.innerText) || '';
              var html = document.documentElement ? document.documentElement.innerHTML : '';
              var fail = /Verification failed/i.test(t) || /Verification failed/i.test(html);
              var blocked = /Sorry, you have been blocked|Attention Required!/i.test(t);
              return {ok: true, fail: !!fail, blocked: !!blocked};
            })();
            """,
            self._on_bookmarks_cf_probe,
        )

    def _on_bookmarks_cf_probe(self, result) -> None:
        if not isinstance(result, dict):
            return
        if not (result.get("fail") or result.get("blocked")):
            return
        self.bookmarks_status.setText(
            "Cloudflare блокирует встроенный браузер → жми «Открыть в Chrome» "
            "(отдельное окно без вкладок; CF там обычно проходит)"
        )

    def _open_bookmark_in_browser(self) -> None:
        url = self._current_bookmark_open_url()
        if not url:
            self.bookmarks_status.setText("Нет URL — выбери закладку")
            return
        chrome = _find_chrome_or_edge()
        if chrome:
            try:
                # --app= отдельное окно без панели вкладок — ближе к «в приложении»
                subprocess.Popen(
                    [chrome, f"--app={url}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.bookmarks_status.setText(
                    "Открыто в Chrome/Edge (окно приложения) — Cloudflare там обычно проходит"
                )
                return
            except OSError:
                pass
        QDesktopServices.openUrl(QUrl(url))
        self.bookmarks_status.setText("Открыто во внешнем браузере")

    def on_open_player(self) -> None:
        if self._busy:
            return
        url = self.url_input.text().strip()
        folder_name, id_for_write = resolve_player_target(url)
        if not folder_name:
            self._set_status("Статус: нет папки субтитров — сначала скачай")
            return

        if self._apply_player_folder_state(folder_name, id_for_write) is None:
            return

        # Не грузим YouTube сразу: пустой webview, ▶ по желанию.
        video_id = id_for_write or _extract_id_from_folder(folder_name)
        self._player_pending_video_id = video_id
        self._player_video_loaded = False
        self._unload_player_page_only()
        if hasattr(self, "load_video_btn"):
            self.load_video_btn.setVisible(True)
            self.load_video_btn.setText("▶ Загрузить видео")
        if video_id:
            self._set_player_status(
                "Статус: плеер готов · видео не загружено — нажми ▶"
            )
        else:
            self._set_player_status("Статус: не удалось определить video ID")
        self.show_player_view()

    def on_load_player_video(self) -> None:
        """Явная загрузка YouTube (без автоплея при открытии плеера)."""
        vid = self._player_pending_video_id
        if not vid and self._current_player_folder:
            vid = _extract_id_from_folder(self._current_player_folder)
            self._player_pending_video_id = vid
        if not vid:
            self._set_player_status("Статус: нет video ID — открой плеер из папки с субами")
            return
        self._set_player_status("Статус: загружаю YouTube…")
        if hasattr(self, "load_video_btn"):
            self.load_video_btn.setText("⏳ Загрузка…")
            self.load_video_btn.setEnabled(False)
        self.web_view.setUrl(QUrl(f"https://www.youtube.com/watch?v={vid}"))

    def _unload_player_page_only(self) -> None:
        """Сбросить WebView без сноса папки/меток."""
        if not hasattr(self, "web_view"):
            return
        try:
            self.web_view.page().runJavaScript(
                "try{var v=document.querySelector('video');"
                "if(v){v.pause();v.removeAttribute('src');v.load();}}catch(e){}"
            )
        except Exception:  # noqa: BLE001
            pass
        self.web_view.setUrl(QUrl("about:blank"))
        self._player_video_loaded = False

    def _force_pause_youtube(self) -> None:
        """YouTube часто сам жмёт play — гасим несколько раз после load."""
        script = (
            "(function(){try{var v=document.querySelector('video');"
            "if(!v)return 'no';v.pause();v.autoplay=false;return 'ok';}"
            "catch(e){return 'err';}})();"
        )

        def _done(result) -> None:
            if result == "ok":
                return
            if self._pause_retries_left > 0:
                self._pause_retries_left -= 1
                QTimer.singleShot(350, self._force_pause_youtube)

        self.web_view.page().runJavaScript(script, _done)

    def _apply_player_folder_state(
        self, folder_name: str, id_for_write: str | None
    ) -> bool | None:
        """None — ошибка. True/False — ok, есть/нет сохранённого ИИ-разбора."""
        try:
            payload = load_player_data(folder_name, id_for_write)
            write_player_html(folder_name, id_for_write)
            self._player_http_url = ensure_player_http_url(folder_name)
        except (OSError, ValueError) as exc:
            self._set_status(f"Статус: встроенный плеер не подготовился: {exc}")
            self._set_player_status(f"Ошибка подготовки: {exc}")
            return None

        self._current_player_folder = folder_name
        short = os.path.basename(folder_name)
        self._player_title_full = short
        self.player_title.setToolTip(short)
        self._refresh_player_title_elide()

        if hasattr(self, "ai_summary"):
            self.ai_summary.clear()

        self._all_marks = list(payload["marks"])
        self._last_ai_analysis = None

        saved = load_saved_analysis(folder_name)
        if saved:
            self._apply_ai_analysis(saved)
            action = saved.get("action") or "—"
            verdict = (saved.get("verdict_1_line") or "")[:80]
            n_h = len(saved.get("highlights") or [])
            self._set_player_status_core(
                f"ИИ: сохранённый разбор · {action} · {n_h} моментов"
                + (f" · {verdict}" if verdict else "")
            )
            return True

        self._set_ai_mode_bar_visible(False)
        self.ai_summary.setHtml(
            "<i>Нажми «✨ ИИ» для разбора субтитров</i>"
        )
        return False

    def _get_current_youtube_url(self, callback: Callable[[str], None]) -> None:
        script = (
            "(function(){try{return window.location.href||'';}catch(e){return '';}})();"
        )
        self.web_view.page().runJavaScript(script, callback)

    def on_analyze_current_video(self) -> None:
        """Только субтитры текущего ролика / refresh marks — без автозапуска ИИ."""
        if self._busy or self._ai_busy:
            return

        def _on_href(href: str) -> None:
            url = (href or "").strip()
            video_id = get_video_id(url)
            if not video_id:
                self._set_player_status_core(
                    "Статус: открой ролик YouTube — ссылка не распознана"
                )
                return

            self.url_input.setText(url)
            folder_name = find_output_folder(video_id)
            if folder_name:
                result = self._apply_player_folder_state(folder_name, video_id)
                if result is None:
                    return
                n = len(self._all_marks)
                if result:
                    self._set_player_status_core(
                        f"Статус: субтитры · {n} таймкодов · загружен сохранённый ИИ"
                    )
                else:
                    self._set_player_status_core(
                        f"Статус: субтитры · {n} таймкодов · ИИ нет — жми «✨ ИИ»"
                    )
                return

            self._pending_ai_after_subs = False  # 📥 ≠ цепочка ИИ
            self._set_player_status_core(
                f"Статус: скачиваю субтитры ({self._lang_code.upper()})…"
            )
            self._begin_download_task("player_subs")
            self._set_busy(True)
            threading.Thread(
                target=self._player_subs_download_worker,
                args=(url, self._lang_code),
                daemon=True,
            ).start()

        self._get_current_youtube_url(_on_href)

    @staticmethod
    def _folder_has_subtitle_files(folder: str) -> bool:
        return os.path.isfile(
            os.path.join(folder, "1_текст_с_таймкодами.txt")
        ) or os.path.isfile(
            os.path.join(folder, "0_весь_текст_для_буфера.txt")
        )

    def on_ai_analyze(self) -> None:
        """ИИ по ролику из WebView (не stale `_current_player_folder`).

        Первый клик только показывает Инвест/Обычный — выбор режима.
        Второй клик (когда полоска уже видна) — запуск разбора.
        """
        if self._ai_busy or self._busy:
            return
        if not hasattr(self, "ai_mode_bar") or not self.ai_mode_bar.isVisible():
            self._set_ai_mode_bar_visible(True)
            self._set_player_status_core(
                "ИИ: выбери Инвест или Обычный, потом снова «✨ ИИ»"
            )
            return

        def _on_href(href: str) -> None:
            if self._ai_busy or self._busy:
                return
            url = (href or "").strip()
            video_id = get_video_id(url)
            if not video_id:
                self._set_player_status_core(
                    "Статус: открой ролик YouTube — ссылка не распознана"
                )
                return

            self.url_input.setText(url)
            folder_name = find_output_folder(video_id)
            if folder_name and self._folder_has_subtitle_files(folder_name):
                same = (
                    self._current_player_folder
                    and os.path.normpath(self._current_player_folder)
                    == os.path.normpath(folder_name)
                )
                if not same:
                    if self._apply_player_folder_state(folder_name, video_id) is None:
                        return
                self._start_ai_analyze_folder(folder_name)
                return

            # Папки нет / пустая → скачать субы текущего id, затем ИИ
            self._pending_ai_after_subs = True
            self._set_player_status_core(
                f"ИИ: скачиваю субтитры ({self._lang_code.upper()})…"
            )
            self._begin_download_task("player_subs")
            self._set_busy(True)
            threading.Thread(
                target=self._player_subs_download_worker,
                args=(url, self._lang_code),
                daemon=True,
            ).start()

        self._get_current_youtube_url(_on_href)

    def _start_ai_analyze_folder(self, folder: str) -> None:
        """DeepSeek по конкретной папке dist (после sync id из WebView)."""
        if self._ai_busy or self._busy:
            return
        if not folder or not self._folder_has_subtitle_files(folder):
            self._set_player_status_core(
                "ИИ: нет файлов субтитров в папке ролика"
            )
            return
        mode = self._ai_mode
        mode_label = "инвест" if mode == "invest" else "обычный"
        self._ai_cancel_event.clear()
        self._ai_job_id += 1
        job_id = self._ai_job_id
        self._set_player_status_core(f"ИИ: отправляю запрос ({mode_label})…")
        self._set_ai_busy(True)

        def _worker():
            try:
                analysis = analyze_subtitles(
                    folder,
                    status_cb=lambda m: self._player_status_signal.emit(m),
                    mode=mode,
                    cancel_event=self._ai_cancel_event,
                )
                if (
                    self._ai_cancel_event.is_set()
                    or job_id != self._ai_job_id
                ):
                    self._done_signal.emit(
                        False, "__ai__", "__cancelled__", str(job_id)
                    )
                    return
                self._done_signal.emit(
                    True,
                    f"__ai__{folder}",
                    json.dumps(analysis, ensure_ascii=False),
                    str(job_id),
                )
            except AnalyzeCancelled:
                self._done_signal.emit(
                    False, "__ai__", "__cancelled__", str(job_id)
                )
            except Exception as exc:
                self._done_signal.emit(False, "__ai__", str(exc), str(job_id))

        threading.Thread(target=_worker, daemon=True).start()

    def _cookies_look_logged_in(self) -> bool:
        """True, если залогинены cookies для yt-dlp и/или WebView-профиля."""
        if _inspect_youtube_cookies(_ytdlp_cookies_file()).get("looks_logged_in"):
            return True
        return _yt_profile_looks_logged_in()

    def _refresh_login_btn_visibility(self) -> None:
        """Кнопка «Войти» скрыта из UI (оставлена в коде на случай возврата)."""
        if not hasattr(self, "login_btn"):
            return
        self.login_btn.hide()
        self._login_mode = False

    def _login_btn_clicked(self) -> None:
        # UI-кнопки нет; логика сохранена на случай ручного вызова
        if not self._login_mode:
            # → открыть страницу входа
            self.web_view.setUrl(QUrl("https://accounts.google.com/signin/v2/identifier?service=youtube"))
            self._set_player_status("Статус: войди в аккаунт (кнопка Войти скрыта — логин через cookies)")
            self.login_btn.setText("Назад")
            self.login_btn.setToolTip("Назад к видео")
            self._login_mode = True
            self.login_btn.hide()
        else:
            # → вернуться на видео
            self.login_btn.setText("Войти")
            self.login_btn.setToolTip("Войти в YouTube")
            self._login_mode = False
            self._refresh_login_btn_visibility()
            if self._current_player_folder:
                vid = _extract_id_from_folder(self._current_player_folder)
                if vid:
                    self._player_pending_video_id = vid
                    self.on_load_player_video()
                    return
            self._set_player_status("Статус: нет video ID для возврата")

    def seek_in_player(self, seconds: int) -> None:
        # Если видео ещё не грузили — сначала ▶, потом seek после load
        if not self._player_video_loaded:
            self._pending_seek_seconds = int(seconds)
            self.on_load_player_video()
            self._set_player_status(
                f"Статус: гружу видео, затем прыжок на {format_mmss(seconds)}…"
            )
            return
        self._seek_in_player_now(int(seconds))

    def _seek_in_player_now(self, seconds: int) -> None:
        script = f"""
        (function() {{
            try {{
                var video = document.querySelector('video');
                if (video) {{
                    video.currentTime = {int(seconds)};
                    var p = video.play();
                    if (p && p.catch) p.catch(function(){{}});
                    return 'seek';
                }}
                return false;
            }} catch(e) {{ return 'err:' + e.message; }}
        }})();
        """

        def _done(result):
            if result and result != 'false' and not str(result).startswith('err'):
                self._set_player_status(f"Статус: прыжок на {format_mmss(seconds)}")
            else:
                self._set_player_status("Статус: видео ещё не загружено, подожди")

        self.web_view.page().runJavaScript(script, _done)

    def _on_webview_loaded(self, ok: bool) -> None:
        url = ""
        try:
            url = self.web_view.url().toString()
        except Exception:  # noqa: BLE001
            url = ""
        is_yt = "youtube.com" in url or "youtu.be" in url
        if ok and is_yt:
            self._player_video_loaded = True
            if hasattr(self, "load_video_btn"):
                self.load_video_btn.setVisible(False)
                self.load_video_btn.setEnabled(True)
                self.load_video_btn.setText("▶ Загрузить видео")
            # Пауза по умолчанию (YT любит сам стартовать)
            self._pause_retries_left = 8
            QTimer.singleShot(200, self._force_pause_youtube)
            QTimer.singleShot(800, self._force_pause_youtube)
            QTimer.singleShot(1600, self._force_pause_youtube)
            pending = getattr(self, "_pending_seek_seconds", None)
            if pending is not None:
                self._pending_seek_seconds = None
                QTimer.singleShot(900, lambda s=pending: self._seek_in_player_now(s))
                self._set_player_status(
                    f"Статус: видео загружено · прыжок на {format_mmss(pending)}…"
                )
            else:
                self._set_player_status("Статус: видео загружено · на паузе")
            return
        if ok:
            self._set_player_status("Статус: встроенный плеер готов")
        else:
            if hasattr(self, "load_video_btn"):
                self.load_video_btn.setEnabled(True)
                self.load_video_btn.setText("▶ Загрузить видео")
                self.load_video_btn.setVisible(True)
            self._set_player_status(
                "Статус: встроенный плеер не загрузился — проверь VPN/сеть или Войти."
            )

    def on_download(self) -> None:
        if self._busy:
            return

        url = self.url_input.text().strip()
        if not url:
            self._set_status("Статус: вставь ссылку")
            return

        if not get_video_id(url):
            self._set_status("Статус: не похоже на YouTube-ссылку — проверь URL")
            return

        self._set_status(f"Статус: старт ({self._lang_code.upper()})…")
        self._begin_download_task("download")
        self._set_busy(True)
        # на экране скачивания плеер не должен жить в фоне
        self._unload_player()

        thread = threading.Thread(
            target=self._download_worker,
            args=(url, self._lang_code),
            daemon=True,
        )
        thread.start()

    def on_download_audio(self) -> None:
        if self._busy:
            return
        url = self.url_input.text().strip()
        if not url:
            self._set_status("Статус: вставь ссылку")
            return
        if not get_video_id(url):
            self._set_status("Статус: не похоже на YouTube-ссылку — проверь URL")
            return
        self._start_audio_download(url, from_player=False)

    def on_open_overlay(self) -> None:
        """IDEA-022: overlay с каталогом Music/YouTube_DL (обычное окно)."""
        win = open_overlay_player(start_dir=default_audio_output_dir(), parent=self)
        if win is None:
            return
        self._overlay_window = win
        try:
            win.closed.disconnect(self._on_overlay_closed)
        except (TypeError, RuntimeError):
            pass
        win.closed.connect(self._on_overlay_closed)
        # Ctrl+Shift+O только прячет Фон — Translator не поднимаем (фокус в Cursor и т.п.)
        self.hide()
        self._set_status(
            "Статус: overlay «Фон» открыт (← Назад / крестик — сюда; Ctrl+O — сквозь; Ctrl+Shift+O — скрыть Фон)"
        )

    def on_open_dist_files(self) -> None:
        """IDEA-021: txt из dist/ внутри приложения + копировать."""
        prefer = self._current_player_folder
        dlg = DistFilesDialog(self, prefer_folder=prefer)
        dlg.exec()

    def _on_overlay_hidden(self) -> None:
        """Раньше поднимал Translator при Ctrl+Shift+O — больше не вызывается."""
        return

    def _on_overlay_closed(self) -> None:
        self._overlay_window = None
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        # 1) отмена фоновых задач → 2) дети yt-dlp → 3) overlay/http/webview
        try:
            self._ai_cancel_event.set()
            self._ai_job_id += 1
        except Exception:
            pass
        try:
            self._cancel_event.set()
        except Exception:
            pass
        kill_active_child_processes()
        try:
            close_overlay_player()
        except Exception:
            pass
        self._overlay_window = None
        try:
            self._unload_player()
        except Exception:
            pass
        if hasattr(self, "bookmarks_web_view"):
            try:
                self.bookmarks_web_view.setUrl(QUrl("about:blank"))
            except Exception:
                pass
        shutdown_player_httpd()
        super().closeEvent(event)

    def on_download_audio_from_player(self) -> None:
        if self._busy:
            return
        url = self.url_input.text().strip()
        if not url and self._current_player_folder:
            vid = _extract_id_from_folder(self._current_player_folder)
            if vid:
                url = f"https://www.youtube.com/watch?v={vid}"
        if not url or not get_video_id(url):
            self._set_player_status_core("Статус: нет ссылки на видео для аудио")
            return
        self._start_audio_download(url, from_player=True)

    def _start_audio_download(self, url: str, *, from_player: bool) -> None:
        if from_player:
            self._set_player_status_core("Статус: старт скачивания аудио…")
        else:
            self._set_status("Статус: старт скачивания аудио…")
        self._begin_download_task("audio_player" if from_player else "audio")
        self._set_busy(True)
        threading.Thread(
            target=self._audio_download_worker,
            args=(url, from_player),
            daemon=True,
        ).start()

    def _audio_download_worker(self, url: str, from_player: bool) -> None:
        err_buf = io.StringIO()
        last_status = "Статус: работаю…"
        result_path = ""

        def status_cb(message: str) -> None:
            nonlocal last_status
            last_status = message
            if from_player:
                self._player_status_signal.emit(message)
            else:
                self._status_signal.emit(message)

        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(err_buf):
                ok, result_path = download_audio(
                    url,
                    status_cb=status_cb,
                    cancel_event=self._cancel_event,
                )
        except Exception as exc:  # noqa: BLE001
            ok = False
            err_buf.write(str(exc))

        if self._cancel_event.is_set():
            self._done_signal.emit(False, "__cancelled__", self._cancel_context, "")
            return

        marker = f"__audio__{'player' if from_player else 'download'}"
        payload = result_path if ok else err_buf.getvalue()
        self._done_signal.emit(ok, marker, payload, last_status)

    def _download_worker(self, url: str, lang_code: str) -> None:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        last_status = "Статус: работаю…"

        def status_cb(message: str) -> None:
            nonlocal last_status
            last_status = message
            self._status_signal.emit(message)

        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                ok = download_and_split(
                    url,
                    lang_code,
                    status_cb=status_cb,
                    cancel_event=self._cancel_event,
                )
        except Exception as exc:  # noqa: BLE001 — показать в UI
            ok = False
            err_buf.write(str(exc))

        if self._cancel_event.is_set():
            self._done_signal.emit(False, "__cancelled__", self._cancel_context, "")
            return

        timing_hint = ""
        for line in out_buf.getvalue().splitlines():
            if line.startswith("Тайминги:"):
                timing_hint = line
                break

        self._done_signal.emit(ok, url, err_buf.getvalue(), timing_hint or last_status)

    def _player_subs_download_worker(self, url: str, lang_code: str) -> None:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        last_status = "Статус: работаю…"

        def status_cb(message: str) -> None:
            nonlocal last_status
            last_status = message
            self._player_status_signal.emit(message)

        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                ok = download_and_split(
                    url,
                    lang_code,
                    status_cb=status_cb,
                    cancel_event=self._cancel_event,
                )
        except Exception as exc:  # noqa: BLE001
            ok = False
            err_buf.write(str(exc))

        if self._cancel_event.is_set():
            self._done_signal.emit(False, "__cancelled__", self._cancel_context, "")
            return

        timing_hint = ""
        for line in out_buf.getvalue().splitlines():
            if line.startswith("Тайминги:"):
                timing_hint = line
                break

        self._done_signal.emit(
            ok, f"__player_subs__{url}", err_buf.getvalue(), timing_hint or last_status
        )

    def _on_download_done(
        self, ok: bool, url: str, error_text: str, timing_hint: str
    ) -> None:
        self._set_busy(False)

        if url == "__cancelled__":
            self._pending_ai_after_subs = False
            ctx = error_text or ""
            msg = "Статус: скачивание отменено"
            if ctx.startswith("audio"):
                if "player" in ctx:
                    self._set_player_status_core(msg)
                else:
                    self._set_status(msg)
            elif ctx == "player_subs":
                self._set_player_status_core(msg)
            else:
                self._set_status(msg)
            return

        # ── аудио ──────────────────────────────────────────────────────────
        if url.startswith("__audio__"):
            from_player = url == "__audio__player"
            if not ok:
                msg = (error_text or "").strip() or "Неизвестная ошибка yt-dlp"
                if from_player:
                    self._set_player_status_core(f"Аудио: ошибка — {msg}")
                else:
                    self._set_status(f"Ошибка аудио:\n{msg}")
                return
            out_dir = error_text
            done_msg = f"Аудио готово! MP3 в:\n{out_dir}\n{timing_hint}"
            if from_player:
                self._set_player_status_core(done_msg)
            else:
                self._set_status(done_msg)
            return
        # ───────────────────────────────────────────────────────────────────

        # ── ИИ-анализ ──────────────────────────────────────────────────────
        if url.startswith("__ai__"):
            # job_id в timing_hint: поздний/отменённый ответ не применяем
            try:
                done_job = int(timing_hint) if timing_hint.strip() else None
            except ValueError:
                done_job = None
            cancelled = (not ok and error_text == "__cancelled__") or (
                done_job is not None and done_job != self._ai_job_id
            )
            if cancelled:
                self._set_ai_busy(False)
                self._set_player_status_core("ИИ: отменено")
                return
            self._set_ai_busy(False)
            if not ok:
                self._set_player_status_core(f"ИИ: ошибка — {error_text}")
                return
            try:
                analysis = json.loads(error_text)
            except Exception:
                analysis = {"summary": "", "takeaways": [], "highlights": []}
            action = analysis.get("action") or "—"
            verdict = (analysis.get("verdict_1_line") or "")[:80]
            n_h = len(analysis.get("highlights") or [])
            self._set_player_status_core(
                f"ИИ: {action} · {n_h} моментов"
                + (f" · {verdict}" if verdict else "")
            )
            self._fill_ai_analysis(analysis)
            return
        # ───────────────────────────────────────────────────────────────────

        # ── субтитры из плеера ─────────────────────────────────────────────
        if url.startswith("__player_subs__"):
            actual_url = url.removeprefix("__player_subs__")
            pending_ai = self._pending_ai_after_subs
            self._pending_ai_after_subs = False
            if not ok:
                msg = (error_text or "").strip() or "Неизвестная ошибка yt-dlp"
                prefix = "ИИ: не скачал субы — " if pending_ai else "Субтитры: ошибка — "
                self._set_player_status_core(f"{prefix}{msg}")
                return
            video_id = get_video_id(actual_url)
            folder_name = find_output_folder(video_id) if video_id else None
            if not folder_name:
                self._set_player_status_core(
                    "ИИ: папка не найдена после скачивания"
                    if pending_ai
                    else "Субтитры: папка не найдена после скачивания"
                )
                return
            has_ai = self._apply_player_folder_state(folder_name, video_id)
            if has_ai is None:
                self._set_player_status_core(
                    "ИИ: не удалось загрузить таймкоды"
                    if pending_ai
                    else "Субтитры: не удалось загрузить таймкоды"
                )
                return
            if pending_ai:
                self._start_ai_analyze_folder(folder_name)
                return
            n = len(self._all_marks)
            if has_ai:
                self._set_player_status_core(
                    f"Субтитры готовы · {n} таймкодов · загружен сохранённый ИИ"
                )
            else:
                self._set_player_status_core(
                    f"Субтитры готовы · {n} таймкодов · ИИ нет — жми «✨ ИИ»"
                )
            return
        # ───────────────────────────────────────────────────────────────────

        if not ok:
            msg = (error_text or "").strip() or "Неизвестная ошибка yt-dlp или ссылки."
            self._set_status(f"Ошибка:\n{msg}")
            return

        video_id = get_video_id(url)
        # base_dir=None → ищет в _subtitle_search_roots() (включает dist/)
        folder_name = find_output_folder(video_id) if video_id else None
        full_text_path = (
            os.path.join(folder_name, "0_весь_текст_для_буфера.txt")
            if folder_name
            else None
        )

        clipboard_msg = ""
        if full_text_path and os.path.exists(full_text_path):
            try:
                with open(full_text_path, "r", encoding="utf-8") as f:
                    text_for_buffer = f.read()
                QApplication.clipboard().setText(text_for_buffer)
                clipboard_msg = "\nТекст уже в буфере — Ctrl+V в нейросеть."
            except OSError as exc:
                clipboard_msg = f"\n(Буфер не скопировался: {exc})"

        shown = folder_name or "папка с субтитрами"
        timed_note = ""
        if folder_name and os.path.exists(
            os.path.join(folder_name, "1_текст_с_таймкодами.txt")
        ):
            timed_note = "\n+ файл с таймкодами: 1_текст_с_таймкодами.txt"
        if folder_name and os.path.exists(os.path.join(folder_name, PLAYER_FILENAME)):
            timed_note += f"\n+ плеер: {PLAYER_FILENAME}"
        self._set_status(
            f"Готово! Папка: {shown}{clipboard_msg}{timed_note}\n{timing_hint}"
        )


# =====================================================================
# 4. ТОЧКА ВХОДА
# =====================================================================

# AUMID ярлыка Desktop «Subtitle Ripper Pro.lnk» — иначе taskbar = иконка pythonw
_SR_AUMID = "Random2079.SubtitleRipperPro.1"


def _apply_sr_aumid() -> None:
    if os.name != "nt":
        return
    import ctypes

    try:
        set_aumid = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_aumid.argtypes = [ctypes.c_wchar_p]
        set_aumid.restype = ctypes.HRESULT
        try:
            set_aumid.errcheck = None  # type: ignore[attr-defined]
        except Exception:
            pass
        set_aumid(_SR_AUMID)
    except Exception:
        pass


def _configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure") and sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure") and sys.stderr is not None:
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _find_sr_hwnd() -> int:
    """HWND главного окна SR (видимое, свёрнутое или временно скрытое)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, "Subtitle Ripper Pro")
    if hwnd:
        return int(hwnd)

    found = ctypes.c_void_p(0)
    EnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
    )

    @EnumProc
    def _enum(h, _lp):  # type: ignore[misc]
        # Не фильтруем IsWindowVisible — иначе второй ярлык может
        # не найти окно и убить живой процесс как «зомби».
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(h, buf, 512)
        title = buf.value or ""
        if title == "Subtitle Ripper Pro" or title.startswith("Subtitle Ripper"):
            found.value = h
            return False
        return True

    user32.EnumWindows(_enum, 0)
    return int(found.value or 0)


def _live_sr_pids() -> list[int]:
    """PID других python* с Subtitle_App.py (кроме текущего)."""
    me = os.getpid()
    pids: list[int] = []
    try:
        import psutil
    except ImportError:
        return pids

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = proc.info.get("pid")
            if pid == me:
                continue
            name = (proc.info.get("name") or "").lower()
            if name not in ("python.exe", "pythonw.exe"):
                continue
            cmd = " ".join(proc.info.get("cmdline") or []).lower().replace("\\", "/")
            if "subtitle_app.py" not in cmd:
                continue
            pids.append(int(pid))
        except (psutil.Error, OSError, ProcessLookupError, TypeError, ValueError):
            continue
    return pids


def _kill_orphan_sr_processes() -> int:
    """Убивает python/pythonw с Subtitle_App.py этого проекта. Возвращает число."""
    root = os.path.abspath(os.path.dirname(__file__)).lower()
    killed = 0
    try:
        import psutil
    except ImportError:
        psutil = None  # type: ignore[assignment]

    if psutil is not None:
        me = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info.get("pid") == me:
                    continue
                name = (proc.info.get("name") or "").lower()
                if name not in ("python.exe", "pythonw.exe"):
                    continue
                cmd = " ".join(proc.info.get("cmdline") or []).lower()
                if "subtitle_app.py" not in cmd.replace("\\", "/"):
                    continue
                # тот же проект или любой Subtitle_App — для зомби ок
                proc.kill()
                killed += 1
            except (psutil.Error, OSError, ProcessLookupError):
                continue
        return killed

    # без psutil: WMI через PowerShell — один раз
    import subprocess

    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -match 'Subtitle_App\\.py' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            errors="replace",
            timeout=15,
            creationflags=(0x08000000 if os.name == "nt" else 0),
        )
        killed = len([ln for ln in out.splitlines() if ln.strip().isdigit()])
    except (OSError, subprocess.SubprocessError):
        killed = 0
    return killed


def _bring_sr_to_front(hwnd: int) -> None:
    """Показать / развернуть уже запущенный SR."""
    import ctypes

    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)


def _ensure_single_instance() -> object | None:
    """
    Именованный мьютекс Windows.
    Второй запуск: поднимает окно и выходит — живой процесс НЕ убиваем.
    Kill orphans — только если мьютекс занят, окна нет и нет живого Subtitle_App.
    """
    if os.name != "nt":
        return None
    import ctypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, True, "SubtitleRipperPro_Mutex")
    if kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return mutex

    hwnd = _find_sr_hwnd()
    if hwnd:
        _bring_sr_to_front(hwnd)
        return None

    live = _live_sr_pids()
    if live:
        # Окно не нашли, но процесс жив — не kill (это и был «краш» на 2-м ярлыке).
        user32.MessageBoxW(
            0,
            "Subtitle Ripper уже запущен (PID: "
            + ", ".join(str(p) for p in live[:5])
            + ").\n"
            "Окно не нашлось автоматически — Alt+Tab.\n"
            "Второй экземпляр не открываю.",
            "Уже запущено",
            0x40,
        )
        return None

    # Мьютекс-призрак без процесса — пробуем снять и забрать запуск
    n = _kill_orphan_sr_processes()
    import time

    time.sleep(0.35)
    kernel32.CloseHandle(mutex)
    mutex2 = kernel32.CreateMutexW(None, True, "SubtitleRipperPro_Mutex")
    if kernel32.GetLastError() == 183:
        user32.MessageBoxW(
            0,
            "Не смог снять старый мьютекс (убито попыток: "
            f"{n}).\n"
            "Диспетчер → pythonw.exe → Снять задачу, потом снова ярлык.",
            "Уже запущено",
            0x30,
        )
        return None
    return mutex2


if __name__ == "__main__":
    _configure_stdio()

    if len(sys.argv) > 1 and not str(sys.argv[1]).startswith("-"):
        video_url = sys.argv[1]
        lang = (
            sys.argv[2]
            if len(sys.argv) > 2 and sys.argv[2] in ("ru", "en")
            else "ru"
        )
        sys.exit(0 if download_and_split(video_url, lang) else 1)

    _mutex_handle = _ensure_single_instance()
    if _mutex_handle is None and os.name == "nt":
        sys.exit(0)

    _apply_sr_aumid()
    # Профили/dist вне индекса Search; миграция yt_profile с OneDrive при первом старте
    try:
        default_output_root()
        webengine_profile_dir("yt_profile")
        webengine_profile_dir("bookmarks_profile")
    except OSError:
        pass
    app = QApplication(sys.argv)
    app.setWindowIcon(make_app_icon())
    configure_qt_theme(app)
    window = SubtitleApp()
    app.installEventFilter(window)
    window.show()
    window.raise_()
    window.activateWindow()
    window._ensure_window_on_screen()
    QTimer.singleShot(0, window._ensure_window_on_screen)
    app._sr_mutex_handle = _mutex_handle  # type: ignore[attr-defined]
    sys.exit(app.exec())
