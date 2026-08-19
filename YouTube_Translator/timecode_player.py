"""Сборка player.html: iframe YouTube + кнопки таймкодов (IDEA-016)."""
from __future__ import annotations

import html
import json
import os
import re
from typing import Any

TIMED_FILENAME = "1_текст_с_таймкодами.txt"
PLAYER_FILENAME = "player.html"
HIGHLIGHTS_TXT = "метки.txt"
HIGHLIGHTS_JSON = "highlights.json"
MIN_GAP_SEC = 25
LABEL_MAX = 60

_TIMED_RE = re.compile(r"^\[(\d{1,3}):(\d{2})\]\s*(.*)$")
_MMSS_RE = re.compile(r"^(\d{1,3}):(\d{2})$")
_FOLDER_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]\s*$")


def mmss_to_seconds(mmss: str) -> int | None:
    m = _MMSS_RE.match(mmss.strip())
    if not m:
        return None
    minutes, seconds = int(m.group(1)), int(m.group(2))
    if seconds >= 60:
        return None
    return minutes * 60 + seconds


def seconds_to_mmss(total: int) -> str:
    total = max(0, int(total))
    return f"{total // 60:02d}:{total % 60:02d}"


def video_id_from_folder_name(name: str) -> str | None:
    m = _FOLDER_ID_RE.search(os.path.basename(name.rstrip("\\/")))
    return m.group(1) if m else None


def parse_timed_lines(text: str) -> list[dict[str, Any]]:
    marks: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _TIMED_RE.match(line)
        if not m:
            continue
        minutes, seconds = int(m.group(1)), int(m.group(2))
        if seconds >= 60:
            continue
        phrase = m.group(3).strip()
        marks.append(
            {
                "seconds": minutes * 60 + seconds,
                "label": phrase,
            }
        )
    return marks


def _clip_label(text: str, max_len: int = LABEL_MAX) -> str:
    t = " ".join(text.split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def thin_marks(
    marks: list[dict[str, Any]], min_gap: int = MIN_GAP_SEC
) -> list[dict[str, Any]]:
    if not marks:
        return []
    out: list[dict[str, Any]] = []
    last_t = -min_gap
    for mark in marks:
        t = int(mark["seconds"])
        if not out or t >= last_t + min_gap:
            out.append(
                {
                    "seconds": t,
                    "label": _clip_label(str(mark.get("label") or "")),
                }
            )
            last_t = t
    return out


def parse_highlights_text(text: str) -> list[dict[str, Any]]:
    marks: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            left, right = line.split("|", 1)
        else:
            left, right = line, ""
        sec = mmss_to_seconds(left)
        if sec is None:
            continue
        title = right.strip() or seconds_to_mmss(sec)
        marks.append({"seconds": sec, "label": _clip_label(title)})
    return marks


def parse_highlights_json(raw: str) -> list[dict[str, Any]]:
    data = json.loads(raw)
    if not isinstance(data, list):
        return []
    marks: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        t = item.get("t") or item.get("time") or item.get("mmss")
        title = item.get("title") or item.get("label") or ""
        if not isinstance(t, str):
            continue
        sec = mmss_to_seconds(t)
        if sec is None:
            continue
        marks.append(
            {
                "seconds": sec,
                "label": _clip_label(str(title) or seconds_to_mmss(sec)),
            }
        )
    return marks


def parse_highlights(folder: str) -> list[dict[str, Any]]:
    """Сначала highlights.json; при битом/нечитаемом JSON — fallback на метки.txt."""
    json_path = os.path.join(folder, HIGHLIGHTS_JSON)
    txt_path = os.path.join(folder, HIGHLIGHTS_TXT)
    if os.path.isfile(json_path):
        try:
            with open(json_path, encoding="utf-8") as f:
                return parse_highlights_json(f.read())
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass  # не глотаем txt из‑за битого json
    if os.path.isfile(txt_path):
        try:
            with open(txt_path, encoding="utf-8") as f:
                return parse_highlights_text(f.read())
        except OSError:
            return []
    return []


def _btn_html(mark: dict[str, Any]) -> str:
    sec = int(mark["seconds"])
    label = html.escape(_clip_label(str(mark.get("label") or "")), quote=True)
    stamp = seconds_to_mmss(sec)
    return (
        f'<button type="button" class="mark" data-t="{sec}">'
        f"<span class=\"t\">{stamp}</span> {label}</button>"
    )


def build_player_html(
    video_id: str,
    marks: list[dict[str, Any]],
    highlights: list[dict[str, Any]] | None = None,
) -> str:
    highlights = highlights or []
    hi_block = ""
    if highlights:
        btns = "\n".join(_btn_html(m) for m in highlights)
        hi_block = f'<section class="hi"><h2>Полезные</h2>\n{btns}\n</section>'
    mark_btns = "\n".join(_btn_html(m) for m in marks) or (
        "<p class=\"empty\">Нет меток — проверь 1_текст_с_таймкодами.txt</p>"
    )
    vid = html.escape(video_id, quote=True)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Плеер таймкодов — {vid}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; font-family: Segoe UI, system-ui, sans-serif; background: #111; color: #eee; }}
  .wrap {{ display: flex; flex-wrap: wrap; min-height: 100vh; }}
  .player {{ flex: 1 1 420px; background: #000; }}
  .player iframe, #yt {{ width: 100%; height: min(56vw, 70vh); min-height: 240px; border: 0; }}
  .side {{ flex: 1 1 280px; max-height: 100vh; overflow: auto; padding: 12px 16px 24px; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: #aaa; margin: 8px 0; }}
  .mark {{ display: block; width: 100%; text-align: left; margin: 0 0 6px; padding: 8px 10px;
           border: 0; border-radius: 6px; background: #1e1e1e; color: #eee; cursor: pointer; }}
  .mark:hover {{ background: #2a3a55; }}
  .mark .t {{ color: #8ab4ff; font-variant-numeric: tabular-nums; margin-right: 8px; }}
  .empty {{ color: #888; }}
  .hint {{ font-size: 12px; color: #888; margin-top: 16px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="player"><div id="yt"></div></div>
  <div class="side">
    {hi_block}
    <section>
      <h2>Таймкоды</h2>
      {mark_btns}
    </section>
    <p class="hint">Если плеер не прыгает с file:// — в этой папке: python -m http.server</p>
  </div>
</div>
<script>
  var VIDEO_ID = {json.dumps(video_id)};
  var player;
  function onYouTubeIframeAPIReady() {{
    player = new YT.Player('yt', {{
      videoId: VIDEO_ID,
      playerVars: {{ rel: 0 }},
      events: {{ onReady: onPlayerReady }}
    }});
  }}
  function onPlayerReady() {{
    document.querySelectorAll('.mark').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        var t = parseInt(btn.getAttribute('data-t'), 10);
        if (isNaN(t) || !player) return;
        player.seekTo(t, true);
        player.playVideo();
      }});
    }});
  }}
</script>
<script src="https://www.youtube.com/iframe_api"></script>
</body>
</html>
"""


def write_player_html(folder: str, video_id: str | None = None) -> str:
    """Пишет player.html в folder. video_id можно взять из имени папки."""
    vid = video_id or video_id_from_folder_name(folder)
    if not vid:
        raise ValueError("Нет YouTube id: передай video_id или имя папки [...id]")

    timed_path = os.path.join(folder, TIMED_FILENAME)
    timed_text = ""
    if os.path.isfile(timed_path):
        with open(timed_path, encoding="utf-8") as f:
            timed_text = f.read()

    marks = thin_marks(parse_timed_lines(timed_text))
    highlights = parse_highlights(folder)
    html_text = build_player_html(vid, marks, highlights)
    out = os.path.join(folder, PLAYER_FILENAME)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_text)
    return out
