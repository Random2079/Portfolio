import os

def clean_and_split(input_file, max_chars=150000):
    if not os.path.exists(input_file):
        print(f"❌ Файл {input_file} не найден.")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Убираем пустые строки
    clean_lines = [line for line in lines if line.strip()]
    clean_text = ''.join(clean_lines)

    # Режем на куски по max_chars
    base_name = os.path.splitext(input_file)[0]
    for i in range(0, len(clean_text), max_chars):
        chunk = clean_text[i:i+max_chars]
        filename = f"{base_name}_часть{i//max_chars + 1}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(chunk)
        print(f'✅ {filename} ({len(chunk)} знаков)')

    print(f'Готово. Текст без пустых строк разделён на части.')

if __name__ == '__main__':
    path = input("Путь к txt-файлу: ").strip()
    clean_and_split(path)