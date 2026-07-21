"""
Мини-демо Flet: та же морда. Flet = Flutter-вайб из Python.
"""
from __future__ import annotations

import flet as ft


def main(page: ft.Page) -> None:
    page.title = "sandbox — Flet"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 520
    page.window.height = 320
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    status = ft.Text("Статус: ждём…", color=ft.Colors.GREY_400)
    url = ft.TextField(
        label="Ссылка YouTube",
        hint_text="https://youtube.com/watch?v=...",
        width=460,
        height=56,
        text_size=14,
    )

    def on_download(_e: ft.ControlEvent) -> None:
        text = (url.value or "").strip()
        if not text:
            status.value = "Статус: вставь ссылку"
        else:
            status.value = f"Статус: нажали «Скачать» (фейк) → {text[:48]}…"
        page.update()

    def on_clear(_e: ft.ControlEvent) -> None:
        url.value = ""
        status.value = "Статус: ждём…"
        page.update()

    page.add(
        ft.Column(
            [
                ft.Text(
                    "YouTube UI — черновик морды (Flet)",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Стиль из коробки, ближе к мобилкам/вебу.",
                    color=ft.Colors.GREY_400,
                ),
                ft.Container(height=12),
                url,
                ft.Container(height=8),
                status,
                ft.Container(height=12),
                ft.Row(
                    [
                        ft.FilledButton("Скачать", on_click=on_download),
                        ft.OutlinedButton("Очистить", on_click=on_clear),
                    ],
                    spacing=8,
                ),
            ],
            spacing=4,
            tight=True,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
