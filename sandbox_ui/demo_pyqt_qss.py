"""
Мини-демо PyQt5 + QSS: та же морда (ссылка / скачать / статус), другой стек.
У тебя PyQt уже стоит — смотрим, можно ли дотянуть стилем без CustomTkinter.
"""
from __future__ import annotations

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

QSS = """
QMainWindow, QWidget#root {
    background: #1a1b26;
}
QLabel#title {
    color: #c0caf5;
    font-size: 18px;
    font-weight: 700;
}
QLabel#hint, QLabel#status {
    color: #a9b1d6;
    font-size: 13px;
}
QLineEdit {
    background: #24283b;
    color: #c0caf5;
    border: 1px solid #414868;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 14px;
}
QLineEdit:focus {
    border: 1px solid #7aa2f7;
}
QPushButton#primary {
    background: #7aa2f7;
    color: #1a1b26;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
}
QPushButton#primary:hover { background: #89b4fa; }
QPushButton#secondary {
    background: #414868;
    color: #c0caf5;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
}
QPushButton#secondary:hover { background: #565f89; }
"""


class Demo(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("sandbox — PyQt5 + QSS")
        self.resize(520, 260)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("YouTube UI — черновик морды (PyQt)")
        title.setObjectName("title")
        layout.addWidget(title)

        hint = QLabel("Стиль через QSS. Логика yt-dlp не подключена.")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        self.url = QLineEdit()
        self.url.setPlaceholderText("https://youtube.com/watch?v=...")
        layout.addWidget(self.url)

        self.status = QLabel("Статус: ждём…")
        self.status.setObjectName("status")
        layout.addWidget(self.status)

        row = QHBoxLayout()
        btn_dl = QPushButton("Скачать")
        btn_dl.setObjectName("primary")
        btn_dl.clicked.connect(self.on_download)
        btn_clear = QPushButton("Очистить")
        btn_clear.setObjectName("secondary")
        btn_clear.clicked.connect(self.on_clear)
        row.addWidget(btn_dl)
        row.addWidget(btn_clear)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    def on_download(self) -> None:
        text = self.url.text().strip()
        if not text:
            self.status.setText("Статус: вставь ссылку")
            return
        self.status.setText(f"Статус: нажали «Скачать» (фейк) → {text[:48]}…")

    def on_clear(self) -> None:
        self.url.clear()
        self.status.setText("Статус: ждём…")


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    win = Demo()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
