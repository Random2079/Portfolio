# Старый код (Old code) с пометками о различиях с новым (New_code)
import subprocess
import os
# В новом коде добавлен import sys (чтобы брать ссылку из командной строки)

def download_and_split(url, lang='ru', max_chars=70000):
    """
    Старая версия: язык передаётся как 'ru' или 'en', но мог быть введён
    с ошибкой (например 'ру' кириллицей). В новом коде параметр переименован
    в lang_code и всегда строго 'ru' или 'en'.
    """
    if not url:
        print("ОШИБКА: URL пуст.")
        return False

    # 1. Сначала пробуем скачать ОБЫЧНЫЕ (встроенные) субтитры
    print(f"🎯 Ищу обычные {lang}-субтитры: {url}")
    cmd_manual = [
        "yt-dlp", "--write-subs", f"--sub-lang", lang,  # f-строка здесь лишняя, в новом коде убрана
        "--convert-subs", "srt", "--skip-download",
        "-o", "temp_subtitles", url
    ]
    
    result = subprocess.run(cmd_manual, capture_output=True, text=True)
    
    # 2. Если обычных нет — пробуем АВТОМАТИЧЕСКИЕ
    if result.returncode != 0 or not any(f.endswith(f'.{lang}.srt') for f in os.listdir('.')):
        print(f"⚙️ Обычных нет. Пробую авто {lang}-субтитры...")
        cmd_auto = [
            "yt-dlp", "--write-auto-subs", f"--sub-lang", lang,  # та же история с f-строкой
            "--convert-subs", "srt", "--skip-download",
            "-o", "temp_subtitles", url
        ]
        result = subprocess.run(cmd_auto, capture_output=True, text=True)

    # Если и авто нет — всё, приехали
    if result.returncode != 0:
        print(f"❌ Ошибка yt-dlp: {result.stderr}")
        return False

    # 3. Ищем скачанный .srt (как раньше)
    srt_file = None
    for f in os.listdir('.'):
        if f.endswith(f'.{lang}.srt'):  # если lang='ру', то будет искать '.ру.srt', что неверно
            srt_file = f
            break
    
    if not srt_file:
        print(f"❌ Файл субтитров не найден.")
        return False

    # 4. Чистим и режем (без изменений, этот блок и в новом коде такой же)
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

    parts = [clean_text[i:i+max_chars] for i in range(0, len(clean_text), max_chars)]
    for i, part in enumerate(parts):
        filename = f'часть_{lang}_{i+1}.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(part)
        print(f'✅ {filename} ({len(part)} знаков)')
    
    print(f'Готово. {len(parts)} частей.')
    return True

if __name__ == '__main__':
    url = input("Ссылка на YouTube: ").strip()
    lang = input("Язык (Enter для ru, или en): ").strip().lower() or 'ru'
    # В новом коде здесь выбор цифрами (1 или 2), чтобы исключить опечатки вроде 'ру'
    
if not download_and_split(url, lang):
    if lang != 'en':
        print("🔄 Пробую английские субтитры...")
        download_and_split(url, 'en')
    else:
        print("❌ Вообще ничего не найдено. Видео без субтитров.")