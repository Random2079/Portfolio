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
  3.  SubtitleApp                  — окно, кнопки, поток, буфер
  4.  __main__                     — GUI или CLI: python Subtitle_App.py URL lang

Функции: не учить «как внутри». Достаточно docstring «что делает».
Имена с _ в начале — внутренние хелперы, в UI не зовутся.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import customtkinter as ctk

from timecode_player import PLAYER_FILENAME, write_player_html

StatusCb = Callable[[str], None]

# Локальный HTTP для player.html (YouTube API с file:// часто молчит)
_player_httpd: ThreadingHTTPServer | None = None
_player_httpd_lock = threading.Lock()


def bind_clipboard_any_layout(entry: ctk.CTkEntry) -> None:
    """
    Tk/CTk на Windows: Ctrl+V при русской раскладке не срабатывает
    (биндинг ждёт латинскую 'v', а клавиша даёт 'м').
    Фикс: ловим физическую клавишу по keycode (V/C/X/A).
    """

    def on_ctrl_key(event):
        # Windows virtual-key: A=65, C=67, V=86, X=88
        if event.keycode == 86:
            event.widget.event_generate("<<Paste>>")
            return "break"
        if event.keycode == 67:
            event.widget.event_generate("<<Copy>>")
            return "break"
        if event.keycode == 88:
            event.widget.event_generate("<<Cut>>")
            return "break"
        if event.keycode == 65:
            event.widget.select_range(0, "end")
            event.widget.icursor("end")
            return "break"
        return None

    entry.bind("<Control-KeyPress>", on_ctrl_key)


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
    Приоритет: сначала auto, иначе manual.
    """
    auto_key = resolve_lang_key(meta.get("automatic_captions"), lang_code)
    if auto_key:
        return "auto", auto_key
    manual_key = resolve_lang_key(meta.get("subtitles"), lang_code)
    if manual_key:
        return "manual", manual_key
    return None


def pick_subtitle_mode(meta: dict, lang_code: str) -> str | None:
    """Обратная совместимость: только mode (auto/manual/None)."""
    resolved = resolve_subtitle_track(meta, lang_code)
    return resolved[0] if resolved else None


def build_meta_yt_dlp_cmd(url: str, extra: list[str] | None = None) -> list[str]:
    """Аргументы yt-dlp для meta (для пайплайна и тестов)."""
    return [
        "yt-dlp",
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        *(extra or []),
        "--",
        url,
    ]


def fetch_video_meta(
    url: str,
    creation_flags: int,
    status_cb: StatusCb | None = None,
) -> dict:
    """Один проход yt-dlp: title + список субтитров (JSON UTF-8).

    При ConnectionReset / сбое API — до 3 попыток с разными player_client.
    Жёсткий timeout процесса не крутим повторно: TLS/сеть всё равно мертвы.
    """
    attempts: list[list[str]] = [
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
    ]
    last_exc: BaseException | None = None
    # на попытку: socket-timeout + запас; суммарно не раздувать до 5 минут
    process_timeout = 55

    for attempt_i, extra in enumerate(attempts, start=1):
        _emit(
            status_cb,
            f"Статус: [1/3] метаданные — попытка {attempt_i}/{len(attempts)}…",
        )
        cmd = build_meta_yt_dlp_cmd(url, extra)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                creationflags=creation_flags,
                timeout=process_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            # зависание handshake/API — другие player_client обычно не спасают
            last_exc = exc
            break
        except (subprocess.CalledProcessError, OSError) as exc:
            last_exc = exc
            continue

        raw = result.stdout.decode("utf-8", errors="replace").strip()
        if not raw:
            last_exc = ValueError("yt-dlp вернул пустой JSON метаданных")
            continue
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue

    assert last_exc is not None
    raise last_exc


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
    roots = [base_dir] if base_dir is not None else _subtitle_search_roots()
    folders: list[str] = []
    for root in roots:
        try:
            for entry in os.scandir(root):
                if entry.is_dir() and entry.name.startswith("субтитры_"):
                    folders.append(entry.path)
        except OSError:
            continue
    return max(folders, key=os.path.getmtime) if folders else None


def app_install_dir() -> str:
    """Корень приложения: рядом с .exe (PyInstaller) или с Subtitle_App.py."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


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
    _add(os.path.join(here, "dist"))
    return roots


def default_output_root() -> str:
    """Куда писать новые прогоны: <app>/dist/ (создаёт при необходимости)."""
    dist = os.path.join(app_install_dir(), "dist")
    os.makedirs(dist, exist_ok=True)
    return dist


def open_player_http(folder: str) -> str:
    """
    Открывает player.html через http://127.0.0.1 — иначе YouTube IFrame API
    часто не сикает с file://. Возвращает URL.
    """
    global _player_httpd
    folder = os.path.abspath(folder)

    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=folder, **kwargs)

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

    with _player_httpd_lock:
        if _player_httpd is not None:
            try:
                _player_httpd.shutdown()
            except Exception:  # noqa: BLE001
                pass
            _player_httpd = None
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        _player_httpd = httpd
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]

    url = f"http://127.0.0.1:{port}/{PLAYER_FILENAME}"
    webbrowser.open(url)
    return url


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
    """Ищем .srt в папке: точный язык из meta, затем короткий код (ru / en)."""
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
    for lang in ordered:
        suffix = f".{lang}.srt"
        for name in names:
            if name.endswith(suffix):
                return os.path.join(folder, name)
    for lang in ordered:
        needle = f".{lang}."
        for name in names:
            if name.endswith(".srt") and needle in name:
                return os.path.join(folder, name)
    return None


def _emit(status_cb: StatusCb | None, message: str) -> None:
    print(message)
    if status_cb:
        status_cb(message)


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
        meta = fetch_video_meta(url, creation_flags, status_cb=status_cb)
    except FileNotFoundError:
        sys.stderr.write("Ошибка: yt-dlp не установлен или не найден в PATH.\n")
        return False
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "Ошибка: yt-dlp завис на метаданных (таймаут). "
            "Часто стратегия zapret пропускает браузер (QUIC), а CLI/TLS — нет. "
            "Смени метод/стратегию zapret (напр. FAKE TLS AUTO) или VPN, потом повтори.\n"
        )
        return False
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            details = (error.stderr or b"").decode("utf-8", errors="replace").strip()
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
                "\nПодсказка: до YouTube из yt-dlp/Python соединение рвут "
                "(браузер через zapret может жить, а CLI — нет). "
                "Не обязательно выключать zapret: смени стратегию "
                "(FAKE TLS AUTO / ALT…), проверь что YouTube в hostlist; "
                "или дай yt-dlp локальный SOCKS/VPN. Ретраи в приложении уже включены.\n"
            )
        sys.stderr.write(
            f"Ошибка: не удалось получить метаданные видео.\n{details}\n{hint}"
        )
        return False
    timings["meta"] = time.perf_counter() - t0

    video_title = sanitize_filename((meta.get("title") or "").strip())
    resolved = resolve_subtitle_track(meta, lang_code)
    if resolved is None:
        sys.stderr.write(
            f"Ошибка: субтитры на языке '{lang_code}' отсутствуют "
            f"(ни авто, ни обычные).\n"
        )
        return False
    mode, yt_lang = resolved

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

    write_flag = "--write-auto-subs" if mode == "auto" else "--write-subs"
    out_template = os.path.join(folder_path, "temp_subtitles")
    cmd = [
        "yt-dlp",
        write_flag,
        "--sub-lang",
        yt_lang,
        "--convert-subs",
        "srt",
        "--skip-download",
        "--socket-timeout",
        "30",
        "-o",
        out_template,
        "--",
        url,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=creation_flags,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "Ошибка: yt-dlp завис на скачивании субтитров (таймаут). "
            "Проверь сеть/стратегию zapret и повтори.\n"
        )
        return False
    timings["subs"] = time.perf_counter() - t1

    if result.returncode != 0:
        sys.stderr.write(f"Ошибка yt-dlp: {result.stderr}\n")
        return False

    srt_file = _find_srt(folder_path, yt_lang, lang_code)
    if not srt_file:
        sys.stderr.write(
            f"Ошибка: yt-dlp не сохранил .srt для языка '{yt_lang}' "
            f"(искали также '{lang_code}').\n"
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
        folder_path, clean_text, timed_text, lang_code, max_chars=max_chars
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


# =====================================================================
# 3. GUI — CustomTkinter
# =====================================================================
class SubtitleApp(ctk.CTk):
    """Окно: поле ссылки, RU/EN, Скачать; качает в фоне, текст в буфер."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Subtitle Ripper Pro")
        self.geometry("560x340")
        self.minsize(480, 300)

        self._busy = False

        title = ctk.CTkLabel(
            self,
            text="YouTube → субтитры",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(padx=20, pady=(20, 4), anchor="w")

        hint = ctk.CTkLabel(
            self,
            text="Вставь ссылку, выбери язык, жми «Скачать». Текст уйдёт в буфер.",
            text_color="gray70",
        )
        hint.pack(padx=20, pady=(0, 12), anchor="w")

        self.url_input = ctk.CTkEntry(
            self,
            placeholder_text="https://youtube.com/watch?v=...",
            height=36,
        )
        self.url_input.pack(fill="x", padx=20, pady=4)
        bind_clipboard_any_layout(self.url_input)

        lang_row = ctk.CTkFrame(self, fg_color="transparent")
        lang_row.pack(fill="x", padx=20, pady=(12, 4))

        ctk.CTkLabel(lang_row, text="Язык:").pack(side="left", padx=(0, 8))
        self.lang_seg = ctk.CTkSegmentedButton(
            lang_row,
            values=["RU", "EN"],
            width=140,
        )
        self.lang_seg.set("RU")
        self.lang_seg.pack(side="left")

        self.theme_seg = ctk.CTkSegmentedButton(
            lang_row,
            values=["dark", "light"],
            command=lambda m: ctk.set_appearance_mode(m),
            width=140,
        )
        self.theme_seg.set("dark")
        self.theme_seg.pack(side="right")

        self.status = ctk.CTkLabel(
            self,
            text="Статус: ожидание ссылки…",
            anchor="w",
            justify="left",
            wraplength=500,
        )
        self.status.pack(fill="x", padx=20, pady=(16, 4))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=16)

        self.download_btn = ctk.CTkButton(
            btn_row, text="Скачать", command=self.on_download, width=120
        )
        self.download_btn.pack(side="left", padx=(0, 8))

        self.player_btn = ctk.CTkButton(
            btn_row, text="Плеер", command=self.on_open_player, width=100
        )
        self.player_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Очистить",
            command=self.on_clear,
            width=100,
            fg_color="gray35",
        ).pack(side="left")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.download_btn.configure(state=state)
        self.player_btn.configure(state=state)
        self.lang_seg.configure(state=state)
        self.url_input.configure(state=state)

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def on_clear(self) -> None:
        if self._busy:
            return
        self.url_input.delete(0, "end")
        self._set_status("Статус: ожидание ссылки…")

    def on_open_player(self) -> None:
        if self._busy:
            return
        url = self.url_input.get().strip()
        folder_name, id_for_write = resolve_player_target(url)
        if not folder_name:
            self._set_status("Статус: нет папки субтитров — сначала скачай")
            return

        # Всегда пересобираем: иначе stale HTML (чужой id / старые метки)
        try:
            write_player_html(folder_name, id_for_write)
        except (OSError, ValueError) as exc:
            self._set_status(
                f"Статус: нет {PLAYER_FILENAME}, пересобрать не вышло: {exc}"
            )
            return
        player_path = os.path.join(folder_name, PLAYER_FILENAME)
        if not os.path.isfile(player_path):
            self._set_status(f"Статус: нет {PLAYER_FILENAME}")
            return

        short = os.path.basename(folder_name)
        if len(short) > 42:
            short = short[:39] + "…"
        try:
            open_player_http(folder_name)
        except OSError as exc:
            try:
                os.startfile(player_path)  # type: ignore[attr-defined]
            except OSError as exc2:
                self._set_status(f"Статус: не открылся плеер: {exc}; {exc2}")
                return
            self._set_status(f"Статус: плеер (file) · {short}")
            return
        self._set_status(f"Статус: плеер · {short}")

    def on_download(self) -> None:
        if self._busy:
            return

        url = self.url_input.get().strip()
        if not url:
            self._set_status("Статус: вставь ссылку")
            return

        lang_code = "en" if self.lang_seg.get() == "EN" else "ru"
        self._set_status(f"Статус: старт ({lang_code.upper()})…")
        self._set_busy(True)

        thread = threading.Thread(
            target=self._download_worker,
            args=(url, lang_code),
            daemon=True,
        )
        thread.start()

    def _download_worker(self, url: str, lang_code: str) -> None:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        last_status = "Статус: работаю…"

        def status_cb(message: str) -> None:
            nonlocal last_status
            last_status = message
            self.after(0, lambda m=message: self._set_status(m))

        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                ok = download_and_split(url, lang_code, status_cb=status_cb)
        except Exception as exc:  # noqa: BLE001 — показать в UI
            ok = False
            err_buf.write(str(exc))

        timing_hint = ""
        for line in out_buf.getvalue().splitlines():
            if line.startswith("Тайминги:"):
                timing_hint = line
                break

        self.after(
            0,
            lambda: self._on_download_done(
                ok, url, err_buf.getvalue(), timing_hint or last_status
            ),
        )

    def _on_download_done(
        self, ok: bool, url: str, error_text: str, timing_hint: str
    ) -> None:
        self._set_busy(False)

        if not ok:
            msg = (error_text or "").strip() or "Неизвестная ошибка yt-dlp или ссылки."
            self._set_status(f"Ошибка:\n{msg}")
            return

        video_id = get_video_id(url)
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
                self.clipboard_clear()
                self.clipboard_append(text_for_buffer)
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


if __name__ == "__main__":
    _configure_stdio()

    if len(sys.argv) > 1:
        video_url = sys.argv[1]
        lang = (
            sys.argv[2]
            if len(sys.argv) > 2 and sys.argv[2] in ("ru", "en")
            else "ru"
        )
        sys.exit(0 if download_and_split(video_url, lang) else 1)

    app = SubtitleApp()
    app.mainloop()
