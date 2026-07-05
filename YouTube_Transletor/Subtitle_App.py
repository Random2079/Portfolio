import sys
import os
import subprocess
import re
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel, QLineEdit, QVBoxLayout, QWidget, QDesktopWidget
)
from PyQt5.QtCore import QProcess

# =====================================================================
# 1. ВАЛИДАТОР ССЫЛОК
# =====================================================================
def get_video_id(url):
    match = re.search(r'(?:v=|\/shorts\/|\/live\/|\/embed\/|youtu\.be\/)([^&\n?#]+)', url)
    return match.group(1) if match else None


# =====================================================================
# 2. ЛОГИКА СКАЧИВАНИЯ И ОБРАБОТКИ
# =====================================================================
def download_and_split(url, lang_code, max_chars=150000):
    video_id = get_video_id(url)
    if not video_id:
        sys.stderr.write("Ошибка: Введена неверная ссылка! Не могу распознать ID видео YouTube.\n")
        return False

    folder_name = f"субтитры_{video_id}"
    os.makedirs(folder_name, exist_ok=True)
    
    old_cwd = os.getcwd()
    os.chdir(folder_name)

    try:
        print(f"🎯 Ищу авто {lang_code}-субтитры: {url}")
        
        # Магический флаг для Windows, который полностью запрещает рисовать черное окно консоли
        creation_flags = 0x08000000 if os.name == 'nt' else 0

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

        self.status_label.setText("Скачиваю субтитры...")
        self.download_button.setEnabled(False)
        
        # Простой и надежный запуск. QProcess сам правильно расставит все кавычки.
        if getattr(sys, 'frozen', False):
            # Запуск внутри готового .exe
            self.process.start(sys.executable, [url])
        else:
            # Запуск из VS Code
            self.process.start(sys.executable, [os.path.abspath(__file__), url])

    def on_process_finished(self, exit_code):
        self.download_button.setEnabled(True)
        
        if exit_code == 0:
            url = self.url_input.text().strip()
            video_id = get_video_id(url)
            folder_name = f"субтитры_{video_id}"
            full_text_path = os.path.join(folder_name, "0_весь_текст_для_буфера.txt")
            
            clipboard_msg = ""
            if os.path.exists(full_text_path):
                try:
                    with open(full_text_path, 'r', encoding='utf-8') as f:
                        text_for_buffer = f.read()
                    QApplication.clipboard().setText(text_for_buffer)
                    clipboard_msg = "\n🔥 ТЕКСТ УЖЕ В БУФЕРЕ! Просто жми Ctrl+V в нейросети."
                except Exception as e:
                    clipboard_msg = f"\n(Не удалось скопировать в буфер: {e})"

            self.status_label.setText(f"Готово! Создана папка: {folder_name}{clipboard_msg}")
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
        
        if download_and_split(video_url, 'ru'):
            sys.exit(0)
        elif download_and_split(video_url, 'en'):
            sys.exit(0)
        else:
            sys.exit(1)
        
    else:
        app = QApplication(sys.argv) 
        window = SubtitleWindow() 
        window.show() 
        sys.exit(app.exec_())