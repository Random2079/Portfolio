import subprocess                     # запуск внешних программ (yt-dlp и т.п.)
import os                              # работа с файловой системой и путями
import time                            # время для логов
import sys                             # доступ к sys.path и аргументам
from concurrent.futures import ThreadPoolExecutor, as_completed
                                      # потоковый пул и итератор завершённых задач
import re                              # регулярные выражения (очистка названий)

# ===== НАСТРОЙКА ПУТИ =====
current_dir = os.path.dirname(os.path.abspath(__file__))  # полный путь к текущему файлу
parent_dir = os.path.dirname(current_dir)                 # родительская папка
youtube_dir = os.path.join(parent_dir, "YouTube_Transletor")  # ожидаемая папка с модулем
if youtube_dir not in sys.path:                           # если папки нет в путях импорта
    sys.path.insert(0, youtube_dir)                       # — добавляем её в начало sys.path

# Импортируем функцию из Subtitle_Ripper.py (ожидается в youtube_dir)
from Subtitle_Ripper import download_and_split

# ===== УТИЛИТА ДЛЯ БЕЗОПАСНОГО ВЫЗОВА SUBPROCESS =====
def safe_run(cmd, timeout=None):
    """Запуск внешней команды с обработкой ошибок — возвращает (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return -1, "", f"TimeoutExpired: {e}"   # таймаут выполнения
    except FileNotFoundError as e:
        return -2, "", f"NotFound: {e}"         # команда (yt-dlp) не найдена
    except Exception as e:
        return -3, "", f"SubprocessError: {e}"  # прочие ошибки

# ===== ФУНКЦИЯ 1: Получить все видео с канала =====
def get_video_urls(channel_url):
    cmd = ["yt-dlp", "--flat-playlist", "--get-url", channel_url]  # команда yt-dlp для списка URL
    rc, out, err = safe_run(cmd)                                   # безопасный запуск
    if rc != 0:
        print(f"Ошибка получения списка видео: {err}")              # лог ошибки
        return []                                                  # возвращаем пустой список
    urls = [u for u in out.strip().splitlines() if u.startswith('http')]
                                                                  # фильтруем валидные URL
    return urls

# ===== ФУНКЦИЯ 2: Получить название видео =====
def get_video_title(url):
    cmd = ["yt-dlp", "--get-title", url]            # команда yt-dlp для получения заголовка
    rc, out, err = safe_run(cmd, timeout=10)        # ограничение по времени
    if rc != 0 or not out:
        # fallback: безопасная короткая метка из параметра v в URL или "untitled"
        fallback = re.sub(r'[<>:"/\\|?*]', '', url.split("v=")[-1])[:100]
        return fallback or "untitled"
    title = re.sub(r'[<>:"/\\|?*]', '', out.strip())  # удаляем запрещённые символы для папок
    return title[:100]                                # ограничиваем длину до 100

# ===== ФУНКЦИЯ 3: Обработать одно видео =====
def process_single_video(url, original_dir, lang='ru', max_chars=70000):
    """Обрабатывает одно видео, гарантируя возврат cwd и логирование."""
    title = url           # дефолт — если заголовок получить не удалось
    status = "❌"         # статус по умолчанию — ошибка
    error = None          # текст ошибки (если будет)
    video_dir = None      # путь к папке видео (определим ниже)

    try:
        title = get_video_title(url)                      # получаем читаемое название
        video_dir = os.path.join(original_dir, title)     # папка для этого видео
        os.makedirs(video_dir, exist_ok=True)             # создаём папку, если нужно

        original_cwd = os.getcwd()                        # запоминаем текущую рабочую директорию
        try:
            os.chdir(video_dir)                           # переходим в папку видео
            download_and_split(url, lang_code=lang, max_chars=max_chars)
                                                         # вызываем внешний модуль для субтитров
            status = "✅"                                 # если дошли сюда — успешно
        finally:
            os.chdir(original_cwd)                        # гарантируем возврат в исходный cwd

    except Exception as e:
        error = str(e)                                    # сохраняем текст ошибки

    # Записываем статус в лог-файл в папке видео (не ломаем основной поток при ошибках)
    try:
        if video_dir and os.path.isdir(video_dir):
            with open(os.path.join(video_dir, "status.log"), "a", encoding="utf-8") as f:
                f.write(f"{time.ctime()}: {title} {status} {error or ''}\n")
    except Exception:
        pass  # игнорируем ошибки логирования

    return (title, status, error)                         # возвращаем результат для внешнего цикла

# ===== ФУНКЦИЯ 4: Обработать весь канал параллельно =====
def process_channel(channel_url, lang='ru', max_chars=70000, workers=3):
    video_urls = get_video_urls(channel_url)             # получаем список URL с канала
    original_dir = os.getcwd()                           # запоминаем стартовый каталог

    print(f"Найдено {len(video_urls)} видео.\n")         # вывод количества видео

    if not video_urls:
        print("Нет видео для обработки.")
        return

    completed = 0                                        # инициализируем счётчик завершённых задач
    # создаём пул потоков, ограничивая одновременные задачи workers
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # создаём futures: запускаем process_single_video для каждого URL
        futures = {executor.submit(process_single_video, url, original_dir, lang, max_chars): url
                   for url in video_urls}

        # проходим по задачам по мере их завершения (as_completed)
        for future in as_completed(futures):
            completed += 1
            try:
                title, status, error = future.result()  # получаем результат задачи
            except Exception as e:
                title, status, error = ("<future-failed>", "❌", str(e))
            if error:
                print(f"[{completed}/{len(video_urls)}] {title} {status} ({error})")
            else:
                print(f"[{completed}/{len(video_urls)}] {title} {status}")

    print("\nГотово. Все доступные видео обработаны.")     # финальное сообщение

# ===== ТОЧКА ВХОДА (запуск программы) =====
if __name__ == '__main__':
    channel_link = input("Ссылка на канал: ").strip()   # просим ссылку на канал у пользователя
    workers = input("Сколько видео скачивать одновременно? (по умолчанию 3): ").strip()
    workers = int(workers) if workers.isdigit() and int(workers) > 0 else 3
                                                       # безопасно парсим число воркеров
    process_channel(channel_link, workers=workers)     # запускаем обработку канала
