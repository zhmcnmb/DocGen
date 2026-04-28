from docx import Document
from pathlib import Path


def parse_docx(path: str) -> str:
    doc = Document(path)
    parts = []
    filename = Path(path).name

    for element in doc.element.body:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

        if tag == "p":
            text = "".join(node.text or "" for node in element.iter() if node.tag.endswith("}t"))
            if text.strip():
                parts.append(text.strip())

        elif tag == "tbl":
            parts.append("[表格]")
            for row in element.iter():
                row_tag = row.tag.split("}")[-1] if "}" in row.tag else row.tag
                if row_tag == "tr":
                    cells = []
                    for cell in row.iter():
                        cell_tag = cell.tag.split("}")[-1] if "}" in cell.tag else cell.tag
                        if cell_tag == "tc":
                            cell_text = "".join(
                                n.text or "" for n in cell.iter() if n.tag.endswith("}t")
                            ).strip()
                            cells.append(cell_text)
                    if cells:
                        parts.append(" | ".join(cells))

    content = "\n".join(parts)
    return f"[文件: {filename}]\n{content}"
