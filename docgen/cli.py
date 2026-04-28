import json
from pathlib import Path
from docgen.session import SessionManager
from docgen.template import parse_template, validate_template, serialize_template
from docgen.parsers.base import parse_files
from docgen.llm import extract_materials, generate_chapter, summarize_chapter, revise_chapter, revise_document


def _ask(prompt: str) -> str:
    return input(f"\n{prompt} ").strip()


def _confirm(prompt: str) -> bool:
    answer = input(f"\n{prompt} (y/n): ").strip().lower()
    return answer in ("y", "yes", "是")


def _choose_review_mode() -> tuple[str, int]:
    print("\n请选择审阅模式:")
    print("  1. 逐章确认 — 每章生成后暂停审阅")
    print("  2. 批量确认 — 每 N 章批量审阅")
    print("  3. 全部生成后审阅 — 连续生成所有章节后统一审阅")
    print("  4. 自定义 — 告诉我你的偏好")

    choice = _ask("请输入选项 (1/2/3/4):")

    if choice == "1":
        return "逐章", 1
    elif choice == "2":
        n = int(_ask("每几章审阅一次?") or "3")
        return "批量", n
    elif choice == "3":
        return "全部", 0
    else:
        custom = _ask("请描述你的审阅偏好:")
        return f"自定义: {custom}", 1


def run_new_session() -> None:
    print("=" * 50)
    print("  DocGen Agent — 文档生成助手")
    print("=" * 50)

    template_path = _ask("请输入模板文件路径 (MD):")
    source_input = _ask("请输入源文件路径 (多个用逗号分隔):")
    source_paths = [p.strip() for p in source_input.split(",") if p.strip()]
    requirement = _ask("请描述你的文档需求:")

    # 解析模板
    chapters = parse_template(template_path)
    valid, msg = validate_template(chapters)
    if not valid:
        print(f"\n模板错误: {msg}，请检查后重试。")
        return

    # 解析源文件
    source_text, warnings = parse_files(source_paths)
    if warnings:
        print("\n警告:")
        for w in warnings:
            print(f"  - {w}")

    # Step 1: 确认理解
    print(f"\n{'='*50}")
    print("我理解了你的需求，模板包含以下章节:")
    for c in chapters:
        print(f"  {c['index']}. {c['title']} — {c['description'][:60]}{'...' if len(c['description']) > 60 else ''}")
    print(f"源文件: {len(source_paths)} 个")
    for sp in source_paths:
        print(f"  - {Path(sp).name}")
    print(f"需求: {requirement[:100]}{'...' if len(requirement) > 100 else ''}")

    if not _confirm("以上理解是否正确?"):
        print("请调整后重新启动。")
        return

    # 初始化会话
    session = SessionManager()
    session.init_session(requirement, template_path, source_paths)
    serialize_template(chapters, session.template_path)
    session.update_phase("准备")
    print(f"\n会话已创建: {session.session_id}")

    # Step 2: 素材提取
    print("\n正在提取素材...")
    session.update_phase("提取")
    pool = extract_materials(chapters, source_text, requirement)
    session.save_materials(pool)

    # Step 3: 确认素材
    print(f"\n{'='*50}")
    print("素材提取完成，各章节素材概览:")
    for ch in pool.get("chapters", []):
        mat = ch.get("materials", "")
        status = f"{len(mat)} 字" if mat else "素材不足"
        print(f"  章节 {ch.get('index', '?')} {ch.get('title', '?')}: {status}")

    if not _confirm("素材是否满足需求?"):
        print("建议补充源文件后重新运行。")
        return

    # Step 4: 选择审阅模式
    mode, batch_size = _choose_review_mode()
    print(f"\n审阅模式: {mode}")

    # Step 5: 逐章节生成
    session.update_phase("生成")
    prev_summaries = []
    completed = session.get_completed_chapters()
    generated_chapters = []

    for chapter in chapters:
        idx = chapter["index"]
        if idx in completed:
            content = session.load_chapter(idx, chapter["title"])
            summary = session.load_summary(idx, chapter["title"])
            if summary:
                prev_summaries.append(summary)
            generated_chapters.append(content)
            print(f"\n章节 {idx}: {chapter['title']} (已存在，跳过)")
            continue

        # 获取该章节的素材
        chapter_materials = ""
        for ch in pool.get("chapters", []):
            if ch.get("index") == idx:
                chapter_materials = ch.get("materials", "")
                break

        print(f"\n正在生成章节 {idx}/{len(chapters)}: {chapter['title']}...")
        content = generate_chapter(
            chapter, chapter_materials, requirement, chapters, prev_summaries
        )

        summary = summarize_chapter(chapter["title"], content)
        session.save_chapter(idx, chapter["title"], content)
        session.save_summary(idx, chapter["title"], summary)
        prev_summaries.append(summary)
        generated_chapters.append(content)

        print(f"章节 {idx}: {chapter['title']} 已生成 ({len(content)} 字)")

        # 审阅检查
        if _should_review(mode, batch_size, idx, len(chapters)):
            _review_chapter(session, chapter, content, generated_chapters)

    # Step 6: 全局审阅
    full_doc = "\n\n".join(generated_chapters)
    print(f"\n{'='*50}")
    print(f"所有章节已生成，共 {len(chapters)} 章，{len(full_doc)} 字")
    print(f"\n文档预览 (前500字):\n{'-'*40}")
    print(full_doc[:500])
    if len(full_doc) > 500:
        print("...")

    while True:
        feedback = _ask("是否需要全局修改? (直接输入修改意见，输入 'n' 跳过):")
        if feedback.lower() in ("n", "no", "否", ""):
            break
        print("正在执行全局修改...")
        full_doc = revise_document(full_doc, feedback)
        print("修改完成。")

    # Step 7: 输出
    session.save_output(full_doc)
    session.update_phase("完成")
    print(f"\n{'='*50}")
    print(f"文档已保存到: {session.output_path}")


def run_resume_session(session_dir: str) -> None:
    session = SessionManager(Path(session_dir))

    if not session.can_resume():
        print(f"未找到会话: {session_dir}")
        return

    meta = session.load_meta()
    chapters = json.loads(session.template_path.read_text(encoding="utf-8"))
    print(f"恢复会话: {session.session_id}")
    print(f"需求: {meta['requirement'][:100]}")
    print(f"当前阶段: {meta['phase']}")

    resume_point = session.detect_resume_point()
    print(f"恢复点: {resume_point}")

    if resume_point == "准备":
        print("会话尚未完成准备工作，建议重新创建。")
        return

    pool = session.load_materials()
    completed = session.get_completed_chapters()

    mode, batch_size = _choose_review_mode()
    session.update_phase("生成")

    prev_summaries = []
    generated_chapters = []

    for chapter in chapters:
        idx = chapter["index"]

        if idx in completed:
            content = session.load_chapter(idx, chapter["title"])
            summary = session.load_summary(idx, chapter["title"])
            if summary:
                prev_summaries.append(summary)
            generated_chapters.append(content)
            print(f"章节 {idx}: {chapter['title']} (已完成，跳过)")
            continue

        chapter_materials = ""
        for ch in pool.get("chapters", []):
            if ch.get("index") == idx:
                chapter_materials = ch.get("materials", "")
                break

        print(f"\n正在生成章节 {idx}/{len(chapters)}: {chapter['title']}...")
        content = generate_chapter(
            chapter, chapter_materials, meta["requirement"], chapters, prev_summaries
        )

        summary = summarize_chapter(chapter["title"], content)
        session.save_chapter(idx, chapter["title"], content)
        session.save_summary(idx, chapter["title"], summary)
        prev_summaries.append(summary)
        generated_chapters.append(content)

        print(f"章节 {idx}: {chapter['title']} 已生成 ({len(content)} 字)")

        if _should_review(mode, batch_size, idx, len(chapters)):
            _review_chapter(session, chapter, content, generated_chapters)

    full_doc = "\n\n".join(generated_chapters)

    while True:
        feedback = _ask("是否需要全局修改? (直接输入修改意见，输入 'n' 跳过):")
        if feedback.lower() in ("n", "no", "否", ""):
            break
        print("正在执行全局修改...")
        full_doc = revise_document(full_doc, feedback)
        print("修改完成。")

    session.save_output(full_doc)
    session.update_phase("完成")
    print(f"\n文档已保存到: {session.output_path}")


def _should_review(mode: str, batch_size: int, current_idx: int, total: int) -> bool:
    if "逐章" in mode or batch_size == 1:
        return True
    if "全部" in mode or batch_size == 0:
        return current_idx == total
    if "批量" in mode:
        return current_idx % batch_size == 0 or current_idx == total
    return True


def _review_chapter(session: SessionManager, chapter: dict, content: str, generated: list) -> None:
    print(f"\n{'='*40}")
    print(f"章节 {chapter['index']}: {chapter['title']}")
    print(f"{'-'*40}")
    print(content[:800])
    if len(content) > 800:
        print("...")

    while True:
        feedback = _ask("修改意见? (直接输入，输入 'ok' 或 'n' 确认):")
        if feedback.lower() in ("ok", "n", "no", "否", "", "好的", "确认"):
            break
        print("正在修改...")
        content = revise_chapter(chapter["title"], content, feedback)
        session.save_chapter(chapter["index"], chapter["title"], content)
        print(f"{'-'*40}")
        print(content[:800])
        if len(content) > 800:
            print("...")

    # 更新 generated 列表中对应章节
    idx = chapter["index"] - 1
    if idx < len(generated):
        generated[idx] = content
