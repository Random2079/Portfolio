from __future__ import annotations

from typing import Any


def render_cover(template: str, vacancy: dict[str, Any]) -> str:
    title = (vacancy.get("title") or "").strip() or "вакансию"
    company = (vacancy.get("company") or "").strip()
    if company:
        company_bit = company
        text = template.replace("{title}", title).replace("{company}", company_bit)
    else:
        text = template.replace("{title}", title)
        text = text.replace("({company})", "").replace("{company}", "компанию")
        text = text.replace("  ", " ").replace("« »", "«вакансию»")
    hits = vacancy.get("hits") or []
    if "{stack_hit}" in text:
        text = text.replace(
            "{stack_hit}",
            ", ".join(hits[:5]) if hits else "Python",
        )
    return text.strip()
