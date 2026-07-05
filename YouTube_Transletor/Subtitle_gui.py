import sys 
import os
from PyQt5.QtWidgets import ( 
    QApplication, QMainWindow, QPushButton, QLabel, QLineEdit, QVBoxLayout, QWidget
)
# Импортируем QProcess для фонового запуска
from PyQt5.QtCore import QProcess

class SubtitleWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Subtitle Ripper")
        self.setGeometry(100, 100, 500, 200)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("Вставь ссылку на YouTube...")
        layout.addWidget(self.url_input)

        self.download_button = QPushButton("Скачать субтитры", self)
        self.download_button.clicked.connect(self.on_download_clicked)
        layout.addWidget(self.download_button)

        self.status_label = QLabel("Ожидание ссылки...", self)
        layout.addWidget(self.status_label)

        # Создаем один фоновый процесс для этого окна
        self.process = QProcess()
        # Говорим ему: "Когда закончишь работу, вызови метод on_process_finished"
        self.process.finished.connect(self.on_process_finished)

    def on_download_clicked(self):
        url = self.url_input.text().strip()

        if not url:
            self.status_label.setText("Ошибка: введи ссылку!")
            return

        base_dir = os.path.dirname(os.path.abspath(__file__))
        ripper_path = os.path.join(base_dir, "Subtitle_Ripper.py")

        self.status_label.setText("Скачиваю субтитры (в фоне, окно не виснет)...")
        # Выключаем кнопку, чтобы нельзя было спамить кликами во время закачки
        self.download_button.setEnabled(False)

        # ЗАПУСК В ФОНЕ: передаем интерпретатор питона, путь к скрипту и ссылку
        self.process.start(sys.executable, [ripper_path, url])

    def on_process_finished(self, exit_code):
        # Этот метод сработает сам, как только фоновый скрипт завершится
        self.download_button.setEnabled(True) # Включаем кнопку обратно

        if exit_code == 0:
            self.status_label.setText("Готово! Субтитры скачаны.")
        else:
            # Если код не 0, значит была ошибка. Достаем ее текст из потока ошибок
            err_bytes = self.process.readAllStandardError()
            try:
                error_text = err_bytes.data().decode('utf-8')
            except:
                error_text = err_bytes.data().decode('cp1251', errors='ignore') # для Windows
            
            self.status_label.setText(f"Ошибка при скачивании:\n{error_text}")

if __name__ == '__main__':
    app = QApplication(sys.argv) 
    window = SubtitleWindow() 
    window.show() 
    sys.exit(app.exec_())