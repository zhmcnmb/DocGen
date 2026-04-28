import pdfplumber
from pathlib import Path


def parse_pdf(path: str) -> str:
    filename = Path(path).name
    parts = []

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                parts.append(f"[第{i}页]\n{text.strip()}")

            tables = page.extract_tables()
            for table in tables:
                parts.append("[表格]")
                for row in table:
                    cells = [str(cell or "") for cell in row]
                    parts.append(" | ".join(cells))

    content = "\n\n".join(parts)
    return f"[文件: {filename}]\n{content}"
