import asyncio
import os
import random
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# .env лежит в корне DS_Projects (уже в .gitignore)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"
API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "Не найден DEEPSEEK_API_KEY.\n"
        "Создай файл .env в корне DS_Projects и добавь строку:\n"
        "DEEPSEEK_API_KEY=твой_ключ"
    )

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

async def resilient_query(prompt: str) -> str:
    """Асинхронный запрос с умными повторными попытками при ошибках 503/429."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            return response.choices[0].message.content
        except Exception as e:
            # Проверка на ошибку перегрузки сервера (503) или лимитов (429)
            if "503" in str(e) or "429" in str(e):
                # Экспоненциальная задержка с "джиттером"
                delay = (2 ** attempt) + random.uniform(0, 1)
                print(f"Сервер перегружен. Попытка {attempt + 1} через {delay:.1f} сек...")
                await asyncio.sleep(delay)
            else:
                raise e
    return "Извините, сервер не отвечает. Попробуйте позже."

async def main():
    while True:
        user_input = input("\nТы: ")
        if user_input.lower() in ["выход", "exit", "quit"]:
            break
        print("Архивариус: ", end="")
        response = await resilient_query(user_input)
        print(response)

if __name__ == "__main__":
    asyncio.run(main())