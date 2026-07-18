import os
import re
import subprocess


def sanitize_filename(filename: str) -> str:
    """Очищает строку от символов, запрещенных в именах файлов."""
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()

def rip_subtitles(video_url: str, output_folder: str = "subtitles"):
    # Проверяем, есть ли папка, и создаем её при необходимости
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    print(f"📂 Папка '{output_folder}' проверена и готова.")
    
    print(f"ℹ️ Получаем название видео...")
    info_cmd = ["yt-dlp", "--get-title", video_url]

    # Запускаем системную команду
    result = subprocess.run(
        info_cmd, capture_output=True, text=True, encoding="utf-8"
    )

    # Очищаем имя и выводим в консоль
    video_title = sanitize_filename(result.stdout.strip())
    print(f"🎥 Название видео: {video_title}")
    
    # Формируем итоговый путь для сохранения
    output_path = os.path.join(output_folder, video_title)

    # Собираем команду для скачивания субтитров
    download_cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-lang",
        "ru",
        "--convert-subs",
        "srt",
        "-o",
        f"{output_path}.%(ext)s",
        video_url,
    ]

    print(f"⏳ Скачиваем субтитры...")
    subprocess.run(download_cmd, check=True)
    print(f"🎉 Готово! Субтитры сохранены в папку '{output_folder}'")
