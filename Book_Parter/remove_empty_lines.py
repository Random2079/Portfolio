import os

def remove_empty_lines(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"❌ Файл {input_file} не найден.")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Оставляем только непустые строки
    clean_lines = [line for line in lines if line.strip()]

    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(clean_lines)

    print(f"✅ Готово. Чистый текст сохранён в {output_file}")

if __name__ == '__main__':
    path = input("Путь к txt-файлу: ").strip()
    out = input("Имя нового файла: ").strip()
    remove_empty_lines(path, out)