import subprocess
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def download_and_split(url, lang_code, max_chars=150000):
    """
    Главная функция без зависимости от Chrome cookies
    """
    if not url:
        print("ОШИБКА: URL пуст.")
        return False

    # === ПОПЫТКА 1: Авто-субтитры ===
    print(f"🎯 Ищу авто {lang_code}-субтитры: {url}")
    cmd_auto = [
        "yt-dlp", 
        "--write-auto-subs", 
        "--sub-lang", 
        lang_code,
        "--convert-subs", 
        "srt", 
        "--skip-download",
        "-o", 
        "temp_subtitles", 
        url
    ]
    
    result = subprocess.run(cmd_auto, capture_output=True, text=True)
    
    # === ПОПЫТКА 2: Обычные субтитры ===
    if result.returncode != 0 or not any(f.endswith(f'.{lang_code}.srt') for f in os.listdir('.')):
        print(f"⚙️ Авто-субтитров нет. Пробую обычные {lang_code}-субтитры...")
        cmd_manual = [
            "yt-dlp", 
            "--write-subs", 
            "--sub-lang", 
            lang_code, 
            "--convert-subs", 
            "srt", 
            "--skip-download", 
            "-o", 
            "temp_subtitles", 
            url                      
        ]
        result = subprocess.run(cmd_manual, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Ошибка yt-dlp: {result.stderr}")
        return False

    # === Находим скачанный файл ===
    srt_file = None
    for f in os.listdir('.'):
        if f.endswith(f'.{lang_code}.srt'):
            srt_file = f
            break
    
    if not srt_file:
        print(f"❌ Файл субтитров не найден.")
        return False

    # === Чистим текст от мусора ===
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

    # === Режем на части ===
    parts = [clean_text[i:i+max_chars] for i in range(0, len(clean_text), max_chars)]
    for i, part in enumerate(parts):
        filename = f'часть_{lang_code}_{i+1}.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(part)
        print(f'✅ {filename} ({len(part)} знаков)')
    
    print(f'Готово. {len(parts)} частей.')
    return True

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Если запустили из интерфейса — берем ссылку из аргументов,
        # а язык по умолчанию ставим русский (скрипт сам переключится на 'en', если 'ru' не найдется)
        video_url = sys.argv[1]
        lang_code = 'ru'
    else:
        # Если запустили вручную в консоли — гоняем старые добрые input()
        video_url = input("Ссылка на YouTube: ").strip()
        while True:
            lang_choice = input("Язык субтитров (1 - Русский, 2 - Английский): ").strip()
            if lang_choice == '1':
                lang_code = 'ru'
                break
            elif lang_choice == '2':
                lang_code = 'en'
                break
            else:
                print("Неверный выбор. Введи 1 или 2.")
    
    # Дальше твоя стандартная логика запуска
    if not download_and_split(video_url, lang_code):
        if lang_code != 'en':
            print("🔄 Пробую английские субтитры...")
            download_and_split(video_url, 'en')
        else:
            print("❌ Вообще ничего не найдено. Видео без субтитров.")