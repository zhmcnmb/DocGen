from pathlib import Path
from docgen.config import MAX_FILE_CHARS
from docgen.parsers.docx_parser import parse_docx
from docgen.parsers.pdf_parser import parse_pdf
from docgen.parsers.xlsx_parser import parse_xlsx
from docgen.parsers.text_parser import parse_plain

PARSERS = {
    ".docx": parse_docx,
    ".pdf": parse_pdf,
    ".xlsx": parse_xlsx,
    ".md": parse_plain,
    ".txt": parse_plain,
}


def parse_file(path: str) -> tuple[str, str]:
    ext = Path(path).suffix.lower()
    parser = PARSERS.get(ext)

    if not parser:
        return "", f"不支持格式 '{ext}'，已跳过: {path}"

    try:
        content = parser(path)
    except Exception as e:
        return "", f"解析失败 '{path}': {e}"

    if len(content) > MAX_FILE_CHARS:
        content = content[:MAX_FILE_CHARS] + f"\n[文件: {Path(path).name} - 已截断]"

    return content, ""


def parse_files(paths: list[str]) -> tuple[str, list[str]]:
    results = []
    warnings = []

    for path in paths:
        content, warning = parse_file(path)
        if warning:
            warnings.append(warning)
        if content:
            results.append(content)

    return "\n\n".join(results), warnings
