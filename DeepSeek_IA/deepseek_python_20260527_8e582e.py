import asyncio
import random
from openai import OpenAI

MODEL = "deepseek-v4-pro"
API_KEY = "sk-d9fb696f569c4e09989deba684ca425b"
BASE_URL = "https://api.deepseek.com"

# Инициализация клиента
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