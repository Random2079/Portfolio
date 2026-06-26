# 1. Импорт библиотек
import asyncio            # Чтобы скрипт не зависал, ожидая ответ от сервера
import os                 # Для работы с файлами и переменными окружения
import random             # Для генерации случайной паузы при перегрузке сервера
from openai import OpenAI # Библиотека для общения с API DeepSeek
from dotenv import load_dotenv  # Чтобы загрузить секретный ключ из файла .env

# 2. Загружаем секретный ключ из файла .env
load_dotenv()  # Читает файл .env и добавляет переменные в окружение

# 3. Конфигурация (какую модель используем и откуда)
MODEL = "deepseek-v4-flash"           # Модель, которую будем использовать
BASE_URL = "https://api.deepseek.com"  # Адрес API DeepSeek
API_KEY = os.getenv("DEEPSEEK_API_KEY")  # Достаём ключ из переменной окружения

# 4. Проверяем, что ключ на месте, иначе скрипт останавливается
if not API_KEY:
    raise RuntimeError(
        "❌ Не найден DEEPSEEK_API_KEY.\n"
        "   Создай файл .env в папке со скриптом и пропиши в нём:\n"
        "   DEEPSEEK_API_KEY=твой_ключ_сюда"
    )

# 5. Создаём клиент для общения с API
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# 6. Функция, которая отправляет один кусок текста Демиургу
async def send_to_demiurge(text_chunk: str, part_number: int) -> str | None:
    
    # Отправляет один кусок текста Демиургу и сохраняет конспект в файл.
    # Параметры:
    #     text_chunk (str) – текст одной части книги
    #     part_number (int) – номер части (для имени файла)
    # Возвращает:
    #     str или None – текст конспекта или None, если сервер перегружен
    
    # Промпт, который объясняет модели её роль
    prompt = (
        f"Ты — Демиург, создатель конспектов. "
        f"Твоя задача — сделать подробный, структурированный конспект "
        f"предложенного текста. Сохраняй все ключевые тезисы, термины "
        f"и логические связи. Это часть {part_number}."
    )

    print(f"📤 Отправляю часть {part_number} Демиургу...")

    try:
        # Отправляем запрос к API и ждём ответ
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},   # Инструкция для модели
                {"role": "user", "content": text_chunk}  # Сам текст куска
            ],
            max_tokens=4096,  # Максимальная длина конспекта
        )

        # Достаём ответ модели
        answer = response.choices[0].message.content

        # Сохраняем ответ в файл
        filename = f"часть_{part_number}_конспект.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(answer)

        print(f"✅ Конспект части {part_number} сохранен в {filename}")
        return answer

    except Exception as e:
        # Обработка ошибок: если сервер перегружен (503) или превышен лимит запросов (429),
        # то мы не падаем, а просто пропускаем этот кусок
        if "503" in str(e) or "429" in str(e):
            print(f"⚠️ Сервер перегружен. Часть {part_number} будет пропущена. Ошибка: {e}")
            return None
        else:
            # Любая другая ошибка — останавливаем скрипт
            raise e

# 7. Главная функция, которая режет книгу и отправляет куски Демиургу
async def process_book(input_file: str, max_chars):

    # Читает файл с книгой, режет его на куски и отправляет каждый кусок Демиургу.
    # Параметры:
    #     input_file (str) – путь к txt-файлу с книгой
    #     max_chars (int) – максимальное количество знаков в одном куске (по умолчанию 150000)

    # Проверяем, что файл существует
    if not os.path.exists(input_file):
        print(f"❌ Файл {input_file} не найден.")
        return

    # Читаем весь файл
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()

    # Режем текст на части
    parts = [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
    print(f"📚 Книга разрезана на {len(parts)} частей. Начинаю обрабатывать...")

    # Отправляем каждую часть Демиургу
    for i, part in enumerate(parts):
        await send_to_demiurge(part, i+1)
        await asyncio.sleep(0.1)  # Пауза 1 секунда, чтобы не заспамить API

    print(f"🏁 Готово! Все части обработаны.")

# 8. Точка входа: то, что запускается при старте скрипта
async def main():
    input_path = input("Путь к книге (txt): ").strip()
    await process_book(input_path, max_chars=50000)

if __name__ == "__main__":
    asyncio.run(main())