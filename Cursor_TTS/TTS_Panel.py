"""
Панель настроек Cursor TTS (PyQt5).
Управляет теми же файлами, что хук и AHK: TTS_OFF, tts_config.json, pid.
Запуск: python TTS_Panel.py
Горячие клавиши AHK остаются как есть.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDesktopWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent
OFF_FLAG = ROOT / "TTS_OFF"
CONFIG_FILE = ROOT / "tts_config.json"
PID_FILE = ROOT / "tts_speech.pid"
SPEAK_EDGE = ROOT / "speak_edge.py"

VOICES_EDGE = [
    ("ru-RU-DmitryNeural", "Дмитрий (мужской)"),
    ("ru-RU-SvetlanaNeural", "Светлана (женский)"),
]
VOICES_LOCAL = [
    ("xenia", "Ксения (жен.)"),
    ("baya", "Бая (жен.)"),
    ("kseniya", "Ксения-2 (жен.)"),
    ("aidar", "Айдар (муж.)"),
    ("eugene", "Евгений (муж.)"),
]
DEFAULT_VOICE = VOICES_EDGE[0][0]
DEFAULT_LOCAL_SPEAKER = "xenia"
DEFAULT_VOLUME = 45
DEFAULT_ENGINE = "edge"
DEFAULT_PAUSE_MS = 350
TEST_PHRASE = "Привет. Это проверка голоса Cursor TTS. Режим локальный или интернет."


def load_config() -> dict:
    data = {
        "engine": DEFAULT_ENGINE,
        "voice": DEFAULT_VOICE,
        "local_speaker": DEFAULT_LOCAL_SPEAKER,
        "volume": DEFAULT_VOLUME,
        "interrupt_on_new": False,
        "pause_ms": DEFAULT_PAUSE_MS,
    }
    if CONFIG_FILE.is_file():
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
        except (json.JSONDecodeError, OSError):
            pass

    engine = str(data.get("engine", DEFAULT_ENGINE)).strip().lower()
    data["engine"] = engine if engine in {"edge", "local"} else DEFAULT_ENGINE

    voice = str(data.get("voice", DEFAULT_VOICE)).strip()
    known_edge = {code for code, _ in VOICES_EDGE}
    if voice not in known_edge:
        voice = DEFAULT_VOICE
    data["voice"] = voice

    local_speaker = str(data.get("local_speaker", DEFAULT_LOCAL_SPEAKER)).strip()
    known_local = {code for code, _ in VOICES_LOCAL}
    if local_speaker not in known_local:
        local_speaker = DEFAULT_LOCAL_SPEAKER
    data["local_speaker"] = local_speaker

    try:
        volume = int(data.get("volume", DEFAULT_VOLUME))
    except (TypeError, ValueError):
        volume = DEFAULT_VOLUME
    data["volume"] = max(10, min(100, volume))
    data["interrupt_on_new"] = bool(data.get("interrupt_on_new", False))
    try:
        data["pause_ms"] = max(0, min(1500, int(data.get("pause_ms", DEFAULT_PAUSE_MS))))
    except (TypeError, ValueError):
        data["pause_ms"] = DEFAULT_PAUSE_MS
    return data


def save_config(
    *,
    engine: str | None = None,
    voice: str | None = None,
    local_speaker: str | None = None,
    volume: int | None = None,
    interrupt_on_new: bool | None = None,
    pause_ms: int | None = None,
) -> None:
    data = load_config()
    if engine is not None:
        data["engine"] = engine
    if voice is not None:
        data["voice"] = voice
    if local_speaker is not None:
        data["local_speaker"] = local_speaker
    if volume is not None:
        data["volume"] = max(10, min(100, volume))
    if interrupt_on_new is not None:
        data["interrupt_on_new"] = interrupt_on_new
    if pause_ms is not None:
        data["pause_ms"] = max(0, min(1500, pause_ms))
    CONFIG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_auto_on() -> bool:
    return not OFF_FLAG.exists()


def set_auto_on(enabled: bool) -> None:
    if enabled:
        OFF_FLAG.unlink(missing_ok=True)
    else:
        OFF_FLAG.write_text("", encoding="utf-8")


DAEMON_PID_FILE = ROOT / "tts_daemon.pid"
AHK_SCRIPT = ROOT / "hotkey_tts.ahk"


def find_ahk_v1() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU64.exe"),
        Path(r"C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU32.exe"),
        Path(r"C:\Program Files\AutoHotkey\AutoHotkeyU64.exe"),
        Path(r"C:\Program Files\AutoHotkey\AutoHotkey.exe"),
        Path(r"C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe"),
        Path(r"C:\Program Files\AutoHotkey\UX\AutoHotkeyUX.exe"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def ahk_running() -> bool:
    flags = 0x08000000 if sys.platform == "win32" else 0
    result = subprocess.run(
        ["tasklist"],
        capture_output=True,
        text=True,
        creationflags=flags,
    )
    out = result.stdout.lower()
    return "autohotkey" in out


def ensure_hotkeys() -> str:
    """Поднять hotkey_tts.ahk, если AutoHotkey ещё не в процессах."""
    if not AHK_SCRIPT.is_file():
        return "missing_script"
    if ahk_running():
        return "already_running"
    ahk = find_ahk_v1()
    flags = 0x08000000 if sys.platform == "win32" else 0
    try:
        if ahk is not None:
            subprocess.Popen(
                [str(ahk), str(AHK_SCRIPT)],
                cwd=str(ROOT),
                creationflags=flags,
            )
            return f"started:{ahk.name}"
        # Assoc .ahk — UX launcher + #Requires v1.1
        os.startfile(str(AHK_SCRIPT))  # type: ignore[attr-defined]
        return "started:assoc"
    except OSError as exc:
        return f"fail:{exc}"


def stop_speech() -> None:
    # #region agent log
    try:
        _dbg = ROOT.parent / "debug-45ab72.log"
        with _dbg.open("a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "45ab72",
                        "hypothesisId": "C",
                        "location": "TTS_Panel.py:stop_speech",
                        "message": "panel stop_speech called",
                        "data": {},
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass
    # #endregion
    flags = 0x08000000 if sys.platform == "win32" else 0
    if SPEAK_EDGE.is_file():
        subprocess.run(
            [sys.executable, str(SPEAK_EDGE), "--stop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    if PID_FILE.is_file():
        try:
            pid = PID_FILE.read_text(encoding="ascii").strip()
        except OSError:
            pid = ""
        if pid:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", pid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        PID_FILE.unlink(missing_ok=True)


def is_speaking() -> bool:
    # Демон жив — не значит, что сейчас говорит; для статуса хватает «демон запущен».
    if not DAEMON_PID_FILE.is_file():
        return False
    try:
        pid = DAEMON_PID_FILE.read_text(encoding="ascii").strip()
    except OSError:
        return False
    if not pid.isdigit():
        return False
    flags = 0x08000000 if sys.platform == "win32" else 0
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"],
        capture_output=True,
        text=True,
        creationflags=flags,
    )
    return pid in result.stdout


class TTSPanel(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cursor TTS")
        self.resize(420, 380)
        self._center()
        self._updating = False

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.auto_checkbox = QCheckBox("Авто-озвучка ответов Agent", self)
        self.auto_checkbox.toggled.connect(self._on_auto_toggled)
        layout.addWidget(self.auto_checkbox)

        self.interrupt_checkbox = QCheckBox(
            "Новый ответ обрывает старый (выкл = очередь)", self
        )
        self.interrupt_checkbox.toggled.connect(self._on_interrupt_toggled)
        layout.addWidget(self.interrupt_checkbox)

        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Движок:", self))
        self.engine_combo = QComboBox(self)
        self.engine_combo.addItem("Интернет (edge)", "edge")
        self.engine_combo.addItem("Локальный (Silero)", "local")
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        engine_row.addWidget(self.engine_combo, stretch=1)
        layout.addLayout(engine_row)

        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Голос:", self))
        self.voice_combo = QComboBox(self)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        voice_row.addWidget(self.voice_combo, stretch=1)
        layout.addLayout(voice_row)

        volume_row = QHBoxLayout()
        volume_row.addWidget(QLabel("Громкость:", self))
        self.volume_slider = QSlider(Qt.Horizontal, self)
        self.volume_slider.setRange(10, 100)
        self.volume_slider.setTickInterval(10)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_row.addWidget(self.volume_slider, stretch=1)
        self.volume_label = QLabel("", self)
        self.volume_label.setMinimumWidth(42)
        volume_row.addWidget(self.volume_label)
        layout.addLayout(volume_row)

        pause_row = QHBoxLayout()
        pause_row.addWidget(QLabel("Пауза:", self))
        self.pause_slider = QSlider(Qt.Horizontal, self)
        self.pause_slider.setRange(0, 1000)
        self.pause_slider.setSingleStep(50)
        self.pause_slider.setTickInterval(100)
        self.pause_slider.valueChanged.connect(self._on_pause_changed)
        pause_row.addWidget(self.pause_slider, stretch=1)
        self.pause_label = QLabel("", self)
        self.pause_label.setMinimumWidth(56)
        pause_row.addWidget(self.pause_label)
        layout.addLayout(pause_row)

        buttons = QHBoxLayout()
        self.test_button = QPushButton("Прослушать", self)
        self.test_button.clicked.connect(self._on_test)
        self.stop_button = QPushButton("Стоп", self)
        self.stop_button.clicked.connect(self._on_stop)
        buttons.addWidget(self.test_button)
        buttons.addWidget(self.stop_button)
        layout.addLayout(buttons)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(
            QLabel(
                "Хоткеи: Ctrl+Shift+T авто · Ctrl+Shift+X стоп · Ctrl+Shift+S выделение",
                self,
            )
        )

        self._reload_from_disk()
        self._refresh_status()

        # #region agent log
        try:
            _dbg = ROOT.parent / "debug-45ab72.log"
            _ensure = ensure_hotkeys()
            with _dbg.open("a", encoding="utf-8") as _f:
                _f.write(
                    json.dumps(
                        {
                            "sessionId": "45ab72",
                            "hypothesisId": "A",
                            "location": "TTS_Panel.py:init",
                            "message": "panel start AHK probe",
                            "data": {
                                "ensure_hotkeys": _ensure,
                                "ahk_running_after": ahk_running(),
                                "ahk_exe": str(find_ahk_v1()),
                                "paths_exist": {
                                    str(p): p.is_file()
                                    for p in [
                                        Path(
                                            r"C:\Program Files\AutoHotkey\AutoHotkey.exe"
                                        ),
                                        Path(
                                            r"C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU64.exe"
                                        ),
                                    ]
                                },
                            },
                            "timestamp": int(time.time() * 1000),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError:
            pass
        # #endregion

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_disk)
        self.timer.start(1000)

    def _center(self) -> None:
        frame = self.frameGeometry()
        center = QDesktopWidget().availableGeometry().center()
        frame.moveCenter(center)
        self.move(frame.topLeft())

    def _fill_voices(self, engine: str, selected: str | None = None) -> None:
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        items = VOICES_LOCAL if engine == "local" else VOICES_EDGE
        for code, label in items:
            self.voice_combo.addItem(label, code)
        if selected:
            index = self.voice_combo.findData(selected)
            if index >= 0:
                self.voice_combo.setCurrentIndex(index)
        self.voice_combo.blockSignals(False)

    def _reload_from_disk(self) -> None:
        self._updating = True
        cfg = load_config()
        self.auto_checkbox.setChecked(is_auto_on())
        self.interrupt_checkbox.setChecked(bool(cfg.get("interrupt_on_new", False)))
        engine_index = self.engine_combo.findData(cfg["engine"])
        if engine_index >= 0:
            self.engine_combo.setCurrentIndex(engine_index)
        selected = (
            cfg["local_speaker"] if cfg["engine"] == "local" else cfg["voice"]
        )
        self._fill_voices(cfg["engine"], selected)
        self.volume_slider.setValue(cfg["volume"])
        self.volume_label.setText(f"{cfg['volume']}%")
        self.pause_slider.setValue(int(cfg.get("pause_ms", DEFAULT_PAUSE_MS)))
        self.pause_label.setText(f"{int(cfg.get('pause_ms', DEFAULT_PAUSE_MS))} ms")
        self._updating = False

    def _poll_disk(self) -> None:
        # AHK мог включить/выключить авто — подтягиваем галочку.
        want = is_auto_on()
        if self.auto_checkbox.isChecked() != want:
            self._updating = True
            self.auto_checkbox.setChecked(want)
            self._updating = False
        self._refresh_status()

    def _refresh_status(self) -> None:
        auto = "ON" if is_auto_on() else "OFF"
        speaking = "демон ON" if is_speaking() else "демон OFF"
        engine = self.engine_combo.currentText()
        voice_label = self.voice_combo.currentText()
        volume = self.volume_slider.value()
        self.status_label.setText(
            f"Авто: {auto} · {engine} · {voice_label} · "
            f"{volume}% · {speaking}"
        )

    def _on_auto_toggled(self, checked: bool) -> None:
        if self._updating:
            return
        set_auto_on(checked)
        if not checked:
            stop_speech()
        self._refresh_status()

    def _on_interrupt_toggled(self, checked: bool) -> None:
        if self._updating:
            return
        save_config(interrupt_on_new=checked)
        self.status_label.setText(
            "Режим: новый ответ обрывает старый."
            if checked
            else "Режим: очередь — дочитывает, потом следующий."
        )
        self._refresh_status()

    def _on_engine_changed(self, _index: int) -> None:
        if self._updating:
            return
        engine = str(self.engine_combo.currentData() or "edge")
        cfg = load_config()
        selected = (
            cfg["local_speaker"] if engine == "local" else cfg["voice"]
        )
        self._fill_voices(engine, selected)
        save_config(engine=engine)
        # Смена движка — лучше перезапустить демон при следующем speak
        self.status_label.setText(
            "Движок сохранён. Первый local-запуск скачает модель (нужен интернет один раз)."
            if engine == "local"
            else "Движок: интернет (edge)."
        )
        self._refresh_status()

    def _on_voice_changed(self, _index: int) -> None:
        if self._updating:
            return
        code = self.voice_combo.currentData()
        if not code:
            return
        engine = str(self.engine_combo.currentData() or "edge")
        if engine == "local":
            save_config(local_speaker=str(code))
        else:
            save_config(voice=str(code))
        self._refresh_status()

    def _on_volume_changed(self, value: int) -> None:
        self.volume_label.setText(f"{value}%")
        if self._updating:
            return
        save_config(volume=value)
        self._refresh_status()

    def _on_pause_changed(self, value: int) -> None:
        # snap to 50ms
        value = int(round(value / 50) * 50)
        if self.pause_slider.value() != value:
            self.pause_slider.blockSignals(True)
            self.pause_slider.setValue(value)
            self.pause_slider.blockSignals(False)
        self.pause_label.setText(f"{value} ms")
        if self._updating:
            return
        save_config(pause_ms=value)
        self._refresh_status()

    def _on_test(self) -> None:
        if not SPEAK_EDGE.is_file():
            self.status_label.setText("Ошибка: не найден speak_edge.py")
            return

        stop_speech()
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        ) as tmp:
            tmp.write(TEST_PHRASE)
            tmp_path = tmp.name

        flags = 0x08000000 if sys.platform == "win32" else 0
        subprocess.Popen(
            [sys.executable, str(SPEAK_EDGE), tmp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        self.status_label.setText(
            "Проигрываю тест… (local: первый раз может долго качать модель)"
            if load_config()["engine"] == "local"
            else "Проигрываю тестовую фразу…"
        )

    def _on_stop(self) -> None:
        stop_speech()
        self.status_label.setText("Остановлено.")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Cursor TTS")

    from PyQt5.QtCore import QSharedMemory
    from PyQt5.QtWidgets import QMessageBox

    guard = QSharedMemory("CursorTTS_Panel_SingleInstance")
    if guard.attach():
        QMessageBox.information(
            None,
            "Cursor TTS",
            "Панель уже открыта.\nНайди окно «Cursor TTS» на панели задач.",
        )
        return 0
    if not guard.create(1):
        guard.detach()
        if not guard.create(1):
            QMessageBox.warning(
                None,
                "Cursor TTS",
                "Не удалось запустить панель.\n"
                "Закрой pythonw в диспетчере задач и попробуй снова.",
            )
            return 1

    window = TTSPanel()
    window.show()
    window.raise_()
    window.activateWindow()
    return app.exec_()


def _show_fatal_error(message: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Cursor TTS", 0x10)
    except OSError:
        pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        log_path = Path(tempfile.gettempdir()) / "cursor_tts_panel.log"
        log_path.write_text(
            f"{type(error).__name__}: {error}\n",
            encoding="utf-8",
        )
        _show_fatal_error(
            f"Ошибка запуска:\n{error}\n\nЛог: {log_path}"
        )
        raise SystemExit(1)
