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
import threading
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
PAUSE_FLAG = ROOT / "TTS_PAUSED"
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
# code = относительный путь к .onnx от Cursor_TTS/
VOICES_PIPER = [
    ("models/ru_RU-dmitri-medium.onnx", "Дмитрий (medium)"),
    ("models/ru_RU-irina-medium.onnx", "Ирина (medium)"),
    ("models/ru_RU-ruslan-medium.onnx", "Руслан (medium)"),
    ("models/ru_RU-denis-medium.onnx", "Денис (medium)"),
]
DEFAULT_VOICE = VOICES_EDGE[0][0]
DEFAULT_LOCAL_SPEAKER = "xenia"
DEFAULT_PIPER_MODEL = VOICES_PIPER[0][0]
DEFAULT_PIPER_MODEL_EN = "models/en_US-ryan-medium.onnx"
DEFAULT_HYBRID_MODE = "dict_only"
DEFAULT_VOLUME = 45
DEFAULT_ENGINE = "edge"
DEFAULT_PAUSE_MS = 350
_ENGINES = {"edge", "local", "piper"}
_HYBRID_MODES = {"off", "dict_only", "dict_and_en"}
HYBRID_ITEMS = [
    ("off", "Как написано (без словаря)"),
    ("dict_only", "Словарь IT (fallback → фэлбэк)"),
    ("dict_and_en", "Словарь + EN-голос (Piper)"),
]
TEST_PHRASE = "Привет. Это проверка голоса Cursor TTS. Режим локальный или интернет."


def load_config() -> dict:
    data = {
        "engine": DEFAULT_ENGINE,
        "voice": DEFAULT_VOICE,
        "local_speaker": DEFAULT_LOCAL_SPEAKER,
        "piper_model": DEFAULT_PIPER_MODEL,
        "piper_model_en": DEFAULT_PIPER_MODEL_EN,
        "hybrid_mode": DEFAULT_HYBRID_MODE,
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
    data["engine"] = engine if engine in _ENGINES else DEFAULT_ENGINE

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

    piper_model = str(data.get("piper_model", DEFAULT_PIPER_MODEL)).strip()
    known_piper = {code for code, _ in VOICES_PIPER}
    if piper_model not in known_piper:
        piper_model = DEFAULT_PIPER_MODEL
    data["piper_model"] = piper_model
    piper_en = str(data.get("piper_model_en", DEFAULT_PIPER_MODEL_EN)).strip()
    data["piper_model_en"] = piper_en or DEFAULT_PIPER_MODEL_EN
    hybrid = str(data.get("hybrid_mode", DEFAULT_HYBRID_MODE)).strip().lower()
    data["hybrid_mode"] = hybrid if hybrid in _HYBRID_MODES else DEFAULT_HYBRID_MODE

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
    piper_model: str | None = None,
    hybrid_mode: str | None = None,
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
    if piper_model is not None:
        data["piper_model"] = piper_model
    if hybrid_mode is not None:
        mode = str(hybrid_mode).strip().lower()
        data["hybrid_mode"] = mode if mode in _HYBRID_MODES else DEFAULT_HYBRID_MODE
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
    flags = 0x08000000 if sys.platform == "win32" else 0
    if SPEAK_EDGE.is_file():
        subprocess.run(
            [sys.executable, str(SPEAK_EDGE), "--stop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )


def is_paused_flag() -> bool:
    return PAUSE_FLAG.is_file()


def pause_toggle_speech() -> bool:
    """Toggle pause. Возвращает True если после команды на паузе."""
    flags = 0x08000000 if sys.platform == "win32" else 0
    if not SPEAK_EDGE.is_file():
        return is_paused_flag()
    try:
        result = subprocess.run(
            [sys.executable, str(SPEAK_EDGE), "--pause-toggle"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
            timeout=5,
        )
        out = (result.stdout or "").strip().upper()
        if "PAUSED" in out:
            return True
        if "PLAYING" in out:
            return False
    except (OSError, subprocess.TimeoutExpired):
        pass
    return is_paused_flag()


def warmup_tts_backend() -> None:
    """Убить старый демон (иначе код паузы не подхватится) + прогреть модель."""
    if not SPEAK_EDGE.is_file():
        return
    flags = 0x08000000 if sys.platform == "win32" else 0

    def run() -> None:
        try:
            subprocess.run(
                [sys.executable, str(SPEAK_EDGE), "--restart-daemon", "--warmup"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                timeout=200,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    threading.Thread(target=run, name="tts-panel-warmup", daemon=True).start()


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
        self.engine_combo.addItem("Локальный (Piper)", "piper")
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        engine_row.addWidget(self.engine_combo, stretch=1)
        layout.addLayout(engine_row)

        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Голос:", self))
        self.voice_combo = QComboBox(self)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        voice_row.addWidget(self.voice_combo, stretch=1)
        layout.addLayout(voice_row)

        hybrid_row = QHBoxLayout()
        hybrid_row.addWidget(QLabel("Текст:", self))
        self.hybrid_combo = QComboBox(self)
        for code, label in HYBRID_ITEMS:
            self.hybrid_combo.addItem(label, code)
        self.hybrid_combo.currentIndexChanged.connect(self._on_hybrid_changed)
        hybrid_row.addWidget(self.hybrid_combo, stretch=1)
        layout.addLayout(hybrid_row)

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
        self.pause_button = QPushButton("Пауза", self)
        self.pause_button.clicked.connect(self._on_pause_toggle)
        self.stop_button = QPushButton("Стоп", self)
        self.stop_button.clicked.connect(self._on_stop)
        buttons.addWidget(self.test_button)
        buttons.addWidget(self.pause_button)
        buttons.addWidget(self.stop_button)
        layout.addLayout(buttons)

        self.pause_state_label = QLabel("Состояние: ▶ играет / готово", self)
        self.pause_state_label.setWordWrap(True)
        layout.addWidget(self.pause_state_label)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(
            QLabel(
                "Хоткеи: Ctrl+Shift+T авто · P пауза · X стоп · S выделение",
                self,
            )
        )

        # OFF через TTS_OFF не должен переживать рестарт панели (дефолт = авто ON).
        if OFF_FLAG.exists():
            set_auto_on(True)

        self._reload_from_disk()
        self._refresh_status()
        ensure_hotkeys()

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
        if engine == "local":
            items = VOICES_LOCAL
        elif engine == "piper":
            items = VOICES_PIPER
        else:
            items = VOICES_EDGE
        for code, label in items:
            self.voice_combo.addItem(label, code)
        if selected:
            index = self.voice_combo.findData(selected)
            if index >= 0:
                self.voice_combo.setCurrentIndex(index)
        self.voice_combo.blockSignals(False)

    @staticmethod
    def _selected_voice_for_engine(cfg: dict, engine: str) -> str:
        if engine == "local":
            return cfg["local_speaker"]
        if engine == "piper":
            return cfg.get("piper_model", DEFAULT_PIPER_MODEL)
        return cfg["voice"]

    def _reload_from_disk(self) -> None:
        self._updating = True
        cfg = load_config()
        self.auto_checkbox.setChecked(is_auto_on())
        self.interrupt_checkbox.setChecked(bool(cfg.get("interrupt_on_new", False)))
        engine_index = self.engine_combo.findData(cfg["engine"])
        if engine_index >= 0:
            self.engine_combo.setCurrentIndex(engine_index)
        selected = self._selected_voice_for_engine(cfg, cfg["engine"])
        self._fill_voices(cfg["engine"], selected)
        self.volume_slider.setValue(cfg["volume"])
        self.volume_label.setText(f"{cfg['volume']}%")
        self.pause_slider.setValue(int(cfg.get("pause_ms", DEFAULT_PAUSE_MS)))
        self.pause_label.setText(f"{int(cfg.get('pause_ms', DEFAULT_PAUSE_MS))} ms")
        hybrid_index = self.hybrid_combo.findData(
            cfg.get("hybrid_mode", DEFAULT_HYBRID_MODE)
        )
        if hybrid_index >= 0:
            self.hybrid_combo.setCurrentIndex(hybrid_index)
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
        paused = is_paused_flag()
        pause_txt = "ПАУЗА" if paused else "играет"
        self.status_label.setText(
            f"Авто: {auto} · {engine} · {voice_label} · "
            f"{volume}% · {speaking} · {pause_txt}"
        )
        self._apply_pause_ui(paused)

    def _apply_pause_ui(self, paused: bool) -> None:
        if paused:
            self.pause_button.setText("НА ПАУЗЕ — жми = продолжить")
            self.pause_button.setStyleSheet(
                "background-color: #c0392b; color: white; font-weight: bold;"
            )
            self.pause_state_label.setText(
                "⏸ ПАУЗА: звук заморожен на месте (тот же слог). "
                "Кнопка или Ctrl+Shift+P = продолжить. "
                "Стоп (X) = сбросить всё."
            )
            self.pause_state_label.setStyleSheet("color: #c0392b; font-weight: bold;")
        else:
            self.pause_button.setText("Пауза")
            self.pause_button.setStyleSheet("")
            self.pause_state_label.setText("Состояние: ▶ играет / готово")
            self.pause_state_label.setStyleSheet("")

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
        selected = self._selected_voice_for_engine(cfg, engine)
        self._fill_voices(engine, selected)
        save_config(engine=engine)
        if engine == "local":
            msg = "Движок: Silero. Первый запуск скачает модель (нужен интернет один раз)."
        elif engine == "piper":
            msg = (
                "Движок: Piper. Нужны onnx в Cursor_TTS/models/ "
                "(см. README: download_piper_voice)."
            )
        else:
            msg = "Движок: интернет (edge)."
        self.status_label.setText(msg)
        self._refresh_status()

    def _on_hybrid_changed(self, _index: int) -> None:
        if self._updating:
            return
        mode = str(self.hybrid_combo.currentData() or DEFAULT_HYBRID_MODE)
        save_config(hybrid_mode=mode)
        if mode == "off":
            msg = "Текст: как написано, без словаря."
        elif mode == "dict_and_en":
            msg = (
                "Текст: словарь + английские фразы другим голосом (нужен Piper EN onnx)."
            )
        else:
            msg = "Текст: словарь IT (fallback → фэлбэк). Пауза продолжает тот же слог."
        self.status_label.setText(msg)
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
        elif engine == "piper":
            save_config(piper_model=str(code))
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
        engine = load_config()["engine"]
        if engine == "local":
            tip = "Проигрываю тест… (Silero: первый раз может долго качать модель)"
        elif engine == "piper":
            tip = "Проигрываю тест… (Piper: нужен .onnx в models/)"
        else:
            tip = "Проигрываю тестовую фразу…"
        self.status_label.setText(tip)

    def _on_pause_toggle(self) -> None:
        paused = pause_toggle_speech()
        self._apply_pause_ui(paused)
        if paused:
            self.status_label.setText("⏸ Сейчас НА ПАУЗЕ. Ещё раз Пауза / Ctrl+Shift+P = продолжить.")
        else:
            self.status_label.setText("▶ Снял паузу — играет / готово.")

    def _on_stop(self) -> None:
        stop_speech()
        # стоп снимает паузу в демоне
        self._apply_pause_ui(False)
        self.status_label.setText("Остановлено (очередь сброшена, пауза снята).")

    def closeEvent(self, event) -> None:  # noqa: N802
        # Закрытие панели не должно оставлять TTS_OFF навсегда:
        # авто по умолчанию снова ON (иначе хук молчит до ручного включения).
        if OFF_FLAG.exists():
            set_auto_on(True)
        super().closeEvent(event)


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
    # Холодный старт Silero — в фоне, чтобы первая фраза из чата не ждала torch
    QTimer.singleShot(300, warmup_tts_backend)
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
