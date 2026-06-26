# epub2txt.py — чистовой конвертер EPUB в TXT
# Установка: pip install ebooklib
import sys
import os
from ebooklib import epub

def epub_to_txt(epub_path: str, txt_path: str):
    """
    Читает EPUB-файл, извлекает весь текст и сохраняет в TXT.
    Пропускает пустые строки, чтобы на выходе было чисто.
    """
    
    if not os.path.exists(epub_path):
        print(f"❌ Файл {epub_path} не найден.")
        return False

    print(f"📖 Читаю книгу: {epub_path}")
    book = epub.read_epub(epub_path)

    all_lines = []
    # Проходим по всем элементам книги
    for item in book.get_items():
        # Берём только текстовые документы (главы)
        if item.get_type() == 9:  # 9 = ITEM_DOCUMENT
            # Декодируем содержимое в текст
            content = item.get_content().decode('utf-8', errors='ignore')
            
            # Удаляем HTML-теги, оставляем только видимый текст
            # Простой и грубый, но эффективный способ без BeautifulSoup
            import re
            # Удаляем всё, что похоже на теги
            text = re.sub(r'<[^>]+>', '', content)
            
            # Убираем HTML-сущности (например, &amp; -> &)
            text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
            
            # Разбиваем на строки и убираем совсем пустые
            lines = text.split('\n')
            for line in lines:
                stripped = line.strip()
                if stripped:  # Игнорируем строки, где ничего нет
                    all_lines.append(stripped)

    if not all_lines:
        print("❌ Не удалось извлечь текст. Возможно, книга состоит из картинок.")
        return False

    # Сохраняем результат
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_lines))

    print(f"✅ Книга сохранена в {txt_path}")
    print(f"   Строк: {len(all_lines)}, Символов: {sum(len(l) for l in all_lines)}")
    return True

if __name__ == '__main__':
    if len(sys.argv) == 3:
        # Запуск из командной строки: python epub2txt.py книга.epub книга.txt
        epub_path = sys.argv[1]
        txt_path = sys.argv[2]
    else:
        epub_path = input("Путь к EPUB-файлу: ").strip()
        txt_path = input("Куда сохранить TXT: ").strip()

    epub_to_txt(epub_path, txt_path)