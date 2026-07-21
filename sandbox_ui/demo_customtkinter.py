"""
Мини-демо CustomTkinter: поле ссылки + кнопка + статус.
Никакого yt-dlp — только вид и клики.
"""
from __future__ import annotations

import customtkinter as ctk


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("sandbox — CustomTkinter")
    app.geometry("520x260")
    app.minsize(420, 220)

    title = ctk.CTkLabel(app, text="YouTube UI — черновик морды", font=ctk.CTkFont(size=18, weight="bold"))
    title.pack(padx=20, pady=(20, 8), anchor="w")

    hint = ctk.CTkLabel(app, text="Сюда потом воткнём yt-dlp. Сейчас только кнопки.", text_color="gray70")
    hint.pack(padx=20, pady=(0, 12), anchor="w")

    url = ctk.CTkEntry(app, placeholder_text="https://youtube.com/watch?v=...", height=36)
    url.pack(fill="x", padx=20, pady=4)

    status = ctk.CTkLabel(app, text="Статус: ждём…", anchor="w")
    status.pack(fill="x", padx=20, pady=(12, 4))

    def on_download() -> None:
        text = url.get().strip()
        if not text:
            status.configure(text="Статус: вставь ссылку")
            return
        status.configure(text=f"Статус: нажали «Скачать» (фейк) → {text[:48]}…")

    def on_clear() -> None:
        url.delete(0, "end")
        status.configure(text="Статус: ждём…")

    row = ctk.CTkFrame(app, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=16)

    ctk.CTkButton(row, text="Скачать", command=on_download, width=120).pack(side="left", padx=(0, 8))
    ctk.CTkButton(row, text="Очистить", command=on_clear, width=100, fg_color="gray35").pack(side="left")

    theme = ctk.CTkSegmentedButton(
        row,
        values=["dark", "light"],
        command=lambda m: ctk.set_appearance_mode(m),
        width=140,
    )
    theme.set("dark")
    theme.pack(side="right")

    app.mainloop()


if __name__ == "__main__":
    main()
