# Импортируем модули
import sys                       # sys нужен для sys.executable (путь к питону) и sys.exit
import os
import subprocess                # subprocess позволяет запускать внешние скрипты
from PyQt5.QtWidgets import (    # Из библиотеки интерфейсов берём:
    QApplication,                #   - само приложение
    QMainWindow,                 #   - главное окно
    QPushButton,                 #   - кнопка
    QLabel,                      #   - текстовая метка
    QLineEdit,                   #   - поле ввода в одну строку
    QVBoxLayout,                 #   - вертикальное расположение элементов
    QWidget                      #   - пустой контейнер (виджет)
)

class SubtitleWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # Обязательно вызываем конструктор родителя (QMainWindow)

        # Заголовок окна
        self.setWindowTitle("Subtitle Ripper")

        # Положение и размер окна: x=100, y=100, ширина=500, высота=200
        self.setGeometry(100, 100, 500, 200)

        # Центральный виджет — контейнер, в который всё складываем
        central_widget = QWidget()
        self.setCentralWidget(central_widget)  # Назначаем его главным в окне

        # Вертикальная раскладка: все элементы будут идти столбиком
        layout = QVBoxLayout(central_widget)

        # Поле ввода для ссылки
        self.url_input = QLineEdit(self)                # Создаём поле
        self.url_input.setPlaceholderText("Вставь ссылку на YouTube...")  # Подсказка внутри
        layout.addWidget(self.url_input)                # Добавляем в раскладку

        # Кнопка «Скачать»
        self.download_button = QPushButton("Скачать субтитры", self)  # Создаём кнопку
        # Связываем сигнал нажатия (clicked) с методом, который будем выполнять
        self.download_button.clicked.connect(self.on_download_clicked)
        layout.addWidget(self.download_button)          # Добавляем кнопку

        # Текстовая метка для статуса
        self.status_label = QLabel("Ожидание ссылки...", self)  # Начальный текст
        layout.addWidget(self.status_label)             # Тоже в раскладку

    def on_download_clicked(self):
        # Метод вызывается, когда нажали кнопку

        # Берём текст из поля и обрезаем пробелы по краям
        url = self.url_input.text().strip()

        # Если ничего не ввели — показываем ошибку и выходим
        if not url:
            self.status_label.setText("Ошибка: введи ссылку!")
            return

        # 1. ГДЕ ЛЕЖИТ ЭТОТ ФАЙЛ (GUI)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. СОБИРАЕМ ПУТЬ К РИППЕРУ (склеиваем папку + имя файла)
        ripper_path = os.path.join(base_dir, "Subtitle_Ripper.py")

        self.status_label.setText("Скачиваю субтитры...")

        # 3. ЗАПУСКАЕМ ЧЕРЕЗ ПОЛНЫЙ ПУТЬ (передаем ripper_path)
        result = subprocess.run(
            [sys.executable, ripper_path, url],
            capture_output=True,
            text=True
        )

        # Проверяем код возврата: 0 — всё хорошо
        if result.returncode == 0:
            self.status_label.setText("Готово! Субтитры скачаны.")
        else:
            # Если ошибка — выводим текст ошибки (stderr)
            self.status_label.setText(f"Ошибка при скачивании:\n{result.stderr}")

# Точка входа: выполняется только при прямом запуске файла
if __name__ == '__main__':
    app = QApplication(sys.argv)   # Создаём приложение PyQt
    window = SubtitleWindow()      # Создаём экземпляр нашего окна
    window.show()                  # Показываем окно на экране
    sys.exit(app.exec_())          # Запускаем бесконечный цикл событий и выходим, когда окно закроется
