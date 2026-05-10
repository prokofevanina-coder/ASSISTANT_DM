"""Загрузка базы знаний из data/*.txt."""

from pathlib import Path


def knowledge_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


# Эти файлы идут первыми в блоке «База знаний» (важно для цен и ключевых ответов).
_KNOWLEDGE_PRIORITY_FILES: tuple[str, ...] = ("price_стоимость тренинга.txt",)


def _read_kb_file(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def load_knowledge_bundle() -> str:
    """Склеивает все .txt из data/ с заголовками-разделителями."""
    root = knowledge_root()
    if not root.is_dir():
        return ""

    parts: list[str] = []
    seen: set[str] = set()

    for name in _KNOWLEDGE_PRIORITY_FILES:
        path = root / name
        if not path.is_file():
            continue
        text = _read_kb_file(path)
        if text:
            parts.append(f"### Файл: {path.name}\n\n{text}")
            seen.add(path.name)

    for path in sorted(root.glob("*.txt")):
        if path.name in seen:
            continue
        text = _read_kb_file(path)
        if text:
            parts.append(f"### Файл: {path.name}\n\n{text}")

    return "\n\n---\n\n".join(parts)


def build_system_instructions(system_prompt_text: str, knowledge_text: str) -> str:
    kb_block = knowledge_text.strip() or "(Материалы базы знаний временно недоступны.)"
    return (
        f"{system_prompt_text.strip()}\n\n"
        "## База знаний\n\n"
        "Используй только следующие материалы как источник фактов о тренингах, условиях и контактах:\n\n"
        f"{kb_block}"
    )
