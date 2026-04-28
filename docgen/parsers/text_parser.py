from pathlib import Path


def parse_plain(path: str) -> str:
    filename = Path(path).name
    content = Path(path).read_text(encoding="utf-8")
    return f"[文件: {filename}]\n{content}"
