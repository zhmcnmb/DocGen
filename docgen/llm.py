import json
from collections.abc import Generator
from openai import OpenAI
from docgen.config import OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL


def _get_client() -> OpenAI:
    return OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)


def _build_messages(system: str, user: str) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def chat(system: str, user: str, temperature: float = 0.3) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=_build_messages(system, user),
        temperature=temperature,
    )
    return response.choices[0].message.content


def stream_chat(system: str, user: str, temperature: float = 0.3) -> Generator[str, None, None]:
    client = _get_client()
    stream = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=_build_messages(system, user),
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def extract_materials(chapters: list[dict], source_text: str, requirement: str) -> dict:
    chapter_list = "\n".join(
        f"- 章节 {c['index']}: {c['title']}\n  描述: {c['description']}"
        for c in chapters
    )

    system = (
        "你是一个文档素材提取助手。根据用户提供的模板章节列表，从源文件中提取相关素材。"
        "对每个章节，提取与之相关的所有信息。如果某章节在源文件中找不到相关素材，标记为空。"
        "输出格式为 JSON：{\"chapters\": [{\"index\": 1, \"title\": \"...\", \"materials\": \"提取到的素材文本\"}]}"
    )

    user = (
        f"## 模板章节\n{chapter_list}\n\n"
        f"## 用户需求\n{requirement}\n\n"
        f"## 源文件内容\n{source_text}"
    )

    result = chat(system, user, temperature=0.1)
    try:
        start = result.index("{")
        end = result.rindex("}") + 1
        return json.loads(result[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"chapters": [], "raw": result}


def generate_chapter(
    chapter: dict,
    materials: str,
    requirement: str,
    all_chapters: list[dict],
    prev_summaries: list[str],
) -> str:
    system, user = _build_chapter_prompt(
        chapter, materials, requirement, all_chapters, prev_summaries
    )
    return chat(system, user)


def _build_chapter_prompt(
    chapter: dict, materials: str, requirement: str,
    all_chapters: list[dict], prev_summaries: list[str],
) -> tuple[str, str]:
    chapter_list = "\n".join(
        f"- 章节 {c['index']}: {c['title']} — {c['description']}"
        for c in all_chapters
    )
    summary_text = ""
    if prev_summaries:
        summary_text = "\n## 前序章节摘要\n" + "\n".join(
            f"- {s}" for s in prev_summaries
        )

    system = (
        "你是一个专业技术文档撰写助手。根据提供的素材和需求，生成指定章节的完整 Markdown 内容。"
        "只输出该章节的内容（包含 ## 标题），不要输出其他章节的内容。"
        "保持专业、准确、结构清晰。"
    )

    user = (
        f"## 文档需求\n{requirement}\n\n"
        f"## 完整模板结构\n{chapter_list}\n\n"
        f"## 当前章节\n章节 {chapter['index']}: {chapter['title']}\n"
        f"描述: {chapter['description']}\n\n"
        f"## 相关素材\n{materials}"
        f"{summary_text}"
    )
    return system, user


def generate_chapter_stream(
    chapter: dict,
    materials: str,
    requirement: str,
    all_chapters: list[dict],
    prev_summaries: list[str],
) -> Generator[str, None, None]:
    system, user = _build_chapter_prompt(
        chapter, materials, requirement, all_chapters, prev_summaries
    )
    yield from stream_chat(system, user)(chapter_title: str, chapter_content: str) -> str:
    system = (
        "为以下章节生成一段 200-500 字的摘要。"
        "摘要必须包含该章的核心要点和关键术语，供后续章节参考以保持连贯性。"
    )
    user = f"## {chapter_title}\n\n{chapter_content}"
    return chat(system, user, temperature=0.1)


def revise_chapter(chapter_title: str, chapter_content: str, feedback: str) -> str:
    system = (
        "你是一个文档修改助手。根据用户的修改意见，修改指定章节的内容。"
        "输出修改后的完整章节内容（包含 ## 标题）。"
    )
    user = (
        f"## 章节: {chapter_title}\n\n"
        f"### 当前内容\n{chapter_content}\n\n"
        f"### 修改意见\n{feedback}"
    )
    return chat(system, user)


def revise_document(document: str, feedback: str) -> str:
    system = (
        "你是一个文档修改助手。根据用户的全局修改意见，修改整篇文档。"
        "输出修改后的完整文档内容。保持原有章节结构不变。"
    )
    user = f"### 当前文档\n{document}\n\n### 全局修改意见\n{feedback}"
    return chat(system, user)
