import json
import re
from pathlib import Path


def parse_template(template_path: str) -> list[dict]:
    content = Path(template_path).read_text(encoding="utf-8")
    chapters = []
    current = None
    sub_descriptions = []

    for line in content.splitlines():
        h1_match = re.match(r"^#\s+(.+)", line)
        sub_match = re.match(r"^(#{2,3})\s+(.+)", line)

        if h1_match and not sub_match:
            if current:
                current["description"] = _finalize_description(
                    current["description"], sub_descriptions
                )
                chapters.append(current)
            current = {"index": len(chapters) + 1, "title": h1_match.group(1).strip(), "description": ""}
            sub_descriptions = []
        elif sub_match and current:
            sub_descriptions.append(f"{'#' * len(sub_match.group(1))} {sub_match.group(2).strip()}")
        elif current and line.strip():
            if current["description"]:
                current["description"] += "\n" + line.strip()
            else:
                current["description"] = line.strip()

    if current:
        current["description"] = _finalize_description(current["description"], sub_descriptions)
        chapters.append(current)

    return chapters


def _finalize_description(desc: str, sub_descriptions: list[str]) -> str:
    if sub_descriptions:
        sub_text = "\n子结构: " + ", ".join(
            s.lstrip("# ").strip() for s in sub_descriptions
        )
        desc = desc + sub_text if desc else sub_text.strip()
    return desc


def validate_template(chapters: list[dict]) -> tuple[bool, str]:
    if not chapters:
        return False, "模板中未找到章节定义（需要 # 标题）"
    return True, ""


def serialize_template(chapters: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
