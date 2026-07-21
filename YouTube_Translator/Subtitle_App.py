import sys
import os
import subprocess
import re
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel, QLineEdit, QVBoxLayout,
    QHBoxLayout, QWidget, QDesktopWidget, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import QProcess

# =====================================================================
# 1. ВАЛИДАТОР ССЫЛОК
# =====================================================================
def get_video_id(url):
    match = re.search(r'(?:v=|\/shorts\/|\/live\/|\/embed\/|youtu\.be\/)([^&\n?#]+)', url)
    return match.group(1) if match else None


def sanitize_filename(name):
    """Убирает из названия символы, запрещённые Windows."""
    name = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", name)
    name = re.sub(r'\s+', " ", name).strip(" .")
    return name[:120] or "Без названия"


def get_video_title(url, creation_flags):
    """Получает название ролика через yt-dlp."""
    result = subprocess.run(
        ["yt-dlp", "--get-title", url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        creationflags=creation_flags,
    )
    return sanitize_filename(result.stdout.strip())


def find_output_folder(video_id):
    """Находит созданную папку по уникальному ID видео."""
    suffix = f" [{video_id}]"
    folders = [
        entry.path
        for entry in os.scandir(".")
        if entry.is_dir()
        and entry.name.startswith("субтитры_")
        and entry.name.endswith(suffix)
    ]
    return max(folders, key=os.path.getmtime) if folders else None


# =====================================================================
# 2. ЛОГИКА СКАЧИВАНИЯ И ОБРАБОТКИ
# =====================================================================
def download_and_split(url, lang_code, max_chars=150000):
    video_id = get_video_id(url)
    if not video_id:
        sys.stderr.write("Ошибка: Введена неверная ссылка! Не могу распознать ID видео YouTube.\n")
        return False

    # На Windows запрещаем вспомогательному процессу yt-dlp показывать чёрное окно.
    creation_flags = 0x08000000 if os.name == 'nt' else 0

    try:
        video_title = get_video_title(url, creation_flags)
    except FileNotFoundError:
        sys.stderr.write("Ошибка: yt-dlp не установлен или не найден в PATH.\n")
        return False
    except subprocess.CalledProcessError as error:
        details = (error.stderr or "").strip()
        sys.stderr.write(f"Ошибка: не удалось получить название видео.\n{details}\n")
        return False

    folder_name = f"субтитры_{video_title} [{video_id}]"
    os.makedirs(folder_name, exist_ok=True)
    
    old_cwd = os.getcwd()
    os.chdir(folder_name)

    try:
        print(f"🎯 Ищу авто {lang_code}-субтитры: {url}")
        
        cmd_auto = [
            "yt-dlp", "--write-auto-subs", "--sub-lang", lang_code,
            "--convert-subs", "srt", "--skip-download", "-o", "temp_subtitles", url
        ]
        # Передаем creation_flags сюда
        result = subprocess.run(cmd_auto, capture_output=True, text=True, creationflags=creation_flags)
        
        if result.returncode != 0 or not any(f.endswith(f'.{lang_code}.srt') for f in os.listdir('.')):
            print(f"⚙️ Авто-субтитров нет. Пробую обычные {lang_code}-субтитры...")
            cmd_manual = [
                "yt-dlp", "--write-subs", "--sub-lang", lang_code,
                "--convert-subs", "srt", "--skip-download", "-o", "temp_subtitles", url                      
            ]
            # И сюда тоже
            result = subprocess.run(cmd_manual, capture_output=True, text=True, creationflags=creation_flags)

        if result.returncode != 0:
            sys.stderr.write(f"Ошибка yt-dlp: {result.stderr}\n")
            return False
            
        srt_file = None
        for f in os.listdir('.'):
            if f.endswith(f'.{lang_code}.srt'):
                srt_file = f
                break
        
        if not srt_file:
            sys.stderr.write(f"Ошибка: Субтитры на языке '{lang_code}' отсутствуют.\n")
            return False

        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        text_lines = []
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.isdigit() or '-->' in line or line.startswith('>>'):
                continue
            line = line.replace('&#39;', "'").replace('&quot;', '"')
            text_lines.append(line)
        
        clean_lines = list(dict.fromkeys(text_lines))
        clean_text = '\n'.join(clean_lines)
        os.remove(srt_file)

        with open("0_весь_текст_для_буфера.txt", "w", encoding="utf-8") as f:
            f.write(clean_text)

        parts = [clean_text[i:i+max_chars] for i in range(0, len(clean_text), max_chars)]
        for i, part in enumerate(parts):
            filename = f'часть_{lang_code}_{i+1}.txt'
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(part)
            print(f'✅ {filename} ({len(part)} знаков)')
        
        print(f'Готово. {len(parts)} частей.')
        return True

    finally:
        os.chdir(old_cwd)


# =====================================================================
# 3. ГРАФИЧЕСКОЕ ОКНО ИНТЕРФЕЙСА
# =====================================================================
class SubtitleWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Subtitle Ripper Pro")
        self.resize(500, 200)
        self.center() 

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("Вставь ссылку на YouTube...")
        layout.addWidget(self.url_input)

        language_layout = QHBoxLayout()
        language_label = QLabel("Язык субтитров:", self)
        self.ru_button = QRadioButton("Русский (RU)", self)
        self.en_button = QRadioButton("English (EN)", self)
        self.ru_button.setChecked(True)

        self.language_group = QButtonGroup(self)
        self.language_group.addButton(self.ru_button)
        self.language_group.addButton(self.en_button)

        language_layout.addWidget(language_label)
        language_layout.addWidget(self.ru_button)
        language_layout.addWidget(self.en_button)
        language_layout.addStretch()
        layout.addLayout(language_layout)

        self.download_button = QPushButton("Скачать субтитры", self)
        self.download_button.clicked.connect(self.on_download_clicked)
        layout.addWidget(self.download_button)

        self.status_label = QLabel("Ожидание ссылки...", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.process = QProcess()
        self.process.finished.connect(self.on_process_finished)

    def center(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def on_download_clicked(self):
        url = self.url_input.text().strip()
        if not url:
            self.status_label.setText("Ошибка: введи ссылку!")
            return

        lang_code = "en" if self.en_button.isChecked() else "ru"
        self.status_label.setText(f"Скачиваю субтитры ({lang_code.upper()})...")
        self.download_button.setEnabled(False)
        self.ru_button.setEnabled(False)
        self.en_button.setEnabled(False)
        
        # Простой и надежный запуск. QProcess сам правильно расставит все кавычки.
        if getattr(sys, 'frozen', False):
            # Запуск внутри готового .exe
            self.process.start(sys.executable, [url, lang_code])
        else:
            # Запуск из VS Code
            self.process.start(sys.executable, [os.path.abspath(__file__), url, lang_code])

    def on_process_finished(self, exit_code):
        self.download_button.setEnabled(True)
        self.ru_button.setEnabled(True)
        self.en_button.setEnabled(True)
        
        if exit_code == 0:
            url = self.url_input.text().strip()
            video_id = get_video_id(url)
            folder_name = find_output_folder(video_id)
            full_text_path = (
                os.path.join(folder_name, "0_весь_текст_для_буфера.txt")
                if folder_name else None
            )
            
            clipboard_msg = ""
            if full_text_path and os.path.exists(full_text_path):
                try:
                    with open(full_text_path, 'r', encoding='utf-8') as f:
                        text_for_buffer = f.read()
                    QApplication.clipboard().setText(text_for_buffer)
                    clipboard_msg = "\n🔥 ТЕКСТ УЖЕ В БУФЕРЕ! Просто жми Ctrl+V в нейросети."
                except Exception as e:
                    clipboard_msg = f"\n(Не удалось скопировать в буфер: {e})"

            shown_folder = folder_name or "папка с субтитрами"
            self.status_label.setText(f"Готово! Создана папка: {shown_folder}{clipboard_msg}")
        else:
            err_bytes = self.process.readAllStandardError()
            out_bytes = self.process.readAllStandardOutput()
            try:
                error_text = err_bytes.data().decode('utf-8')
                if not error_text.strip():
                    error_text = out_bytes.data().decode('utf-8')
            except:
                error_text = err_bytes.data().decode('cp1251', errors='ignore')
            
            if not error_text.strip():
                error_text = "Неизвестная ошибка yt-dlp или неверный формат ссылки."
                
            self.status_label.setText(f"❌ Ошибка при скачивании:\n{error_text.strip()}")


# =====================================================================
# 4. БЕЗОПАСНАЯ ТОЧКА ВХОДА ДЛЯ PYINSTALLER
# =====================================================================
if __name__ == '__main__':
    # Проверяем наличие метода reconfigure, чтобы exe без консоли не падал
    if hasattr(sys.stdout, 'reconfigure') and sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    if hasattr(sys.stderr, 'reconfigure') and sys.stderr is not None:
        try:
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    if len(sys.argv) > 1:
        video_url = sys.argv[1]
        lang_code = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ('ru', 'en') else 'ru'
        sys.exit(0 if download_and_split(video_url, lang_code) else 1)
        
    else:
        app = QApplication(sys.argv) 
        window = SubtitleWindow() 
        window.show() 
        sys.exit(app.exec_())