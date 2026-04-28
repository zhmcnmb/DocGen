import json
import threading
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

from docgen.config import SESSIONS_DIR
from docgen.session import SessionManager
from docgen.template import parse_template, validate_template, serialize_template
from docgen.parsers.base import parse_file
from docgen.llm import (
    extract_materials, generate_chapter, generate_chapter_stream,
    summarize_chapter, revise_chapter, revise_document,
)
from docgen.stream_bridge import StreamBridge


def create_app() -> Flask:
    app = Flask(__name__, static_folder="../frontend", static_url_path="")
    CORS(app)

    UPLOAD_DIR = Path("uploads")
    UPLOAD_DIR.mkdir(exist_ok=True)

    # ── 文件上传 ──────────────────────────────────────

    @app.route("/api/upload", methods=["POST"])
    def upload_files():
        session_id = request.form.get("session_id", "default")
        upload_dir = UPLOAD_DIR / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for key in request.files:
            for f in request.files.getlist(key):
                path = upload_dir / f.filename
                f.save(str(path))

                content, warning = parse_file(str(path))
                preview = content[:500] if content else ""

                results.append({
                    "filename": f.filename,
                    "size": path.stat().st_size,
                    "preview": preview,
                    "warning": warning,
                })

        return jsonify({"files": results}), 200

    # ── 会话管理 ──────────────────────────────────────

    @app.route("/api/sessions", methods=["POST"])
    def create_session():
        data = request.get_json()
        requirement = data.get("requirement", "")
        session = SessionManager()
        session.init_session(requirement, "", [])
        return jsonify({"session_id": session.session_id, "status": "准备"}), 201

    @app.route("/api/sessions/<sid>", methods=["GET"])
    def get_session(sid):
        session = SessionManager(SESSIONS_DIR / sid)
        meta = session.load_meta()
        return jsonify(meta), 200

    @app.route("/api/sessions/<sid>/template", methods=["POST"])
    def upload_template(sid):
        session = SessionManager(SESSIONS_DIR / sid)
        data = request.get_json()
        template_path = data.get("template_path", "")
        chapters = parse_template(template_path)
        valid, msg = validate_template(chapters)
        if not valid:
            return jsonify({"error": msg}), 400

        meta = session.load_meta()
        meta["template_path"] = template_path
        session.meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        serialize_template(chapters, session.template_path)
        return jsonify({"chapters": chapters}), 200

    @app.route("/api/sessions/<sid>/confirm", methods=["POST"])
    def confirm_understanding(sid):
        session = SessionManager(SESSIONS_DIR / sid)
        meta = session.load_meta()
        chapters = json.loads(session.template_path.read_text(encoding="utf-8"))
        return jsonify({
            "chapters": chapters,
            "requirement": meta.get("requirement", ""),
            "source_paths": meta.get("source_paths", []),
        }), 200

    # ── 素材提取 ──────────────────────────────────────

    @app.route("/api/sessions/<sid>/extract", methods=["POST"])
    def extract(sid):
        session = SessionManager(SESSIONS_DIR / sid)
        meta = session.load_meta()
        chapters = json.loads(session.template_path.read_text(encoding="utf-8"))

        source_paths = meta.get("source_paths", [])
        all_text = []
        for p in source_paths:
            content, _ = parse_file(p)
            if content:
                all_text.append(content)
        source_text = "\n\n".join(all_text)

        session.update_phase("提取")
        pool = extract_materials(chapters, source_text, meta.get("requirement", ""))
        session.save_materials(pool)

        overview = []
        for ch in pool.get("chapters", []):
            mat = ch.get("materials", "")
            overview.append({
                "index": ch.get("index"),
                "title": ch.get("title", ""),
                "chars": len(mat),
                "status": "充足" if len(mat) > 50 else "素材不足",
            })

        return jsonify({"overview": overview}), 200

    @app.route("/api/sessions/<sid>/materials/confirm", methods=["POST"])
    def confirm_materials(sid):
        session = SessionManager(SESSIONS_DIR / sid)
        session.update_phase("生成")
        return jsonify({"status": "confirmed"}), 200

    # ── 章节生成（后台线程 + SSE）─────────────────────

    def _generate_worker(sid: str):
        session = SessionManager(SESSIONS_DIR / sid)
        meta = session.load_meta()
        chapters = json.loads(session.template_path.read_text(encoding="utf-8"))
        pool = session.load_materials()
        bridge = StreamBridge.get(sid)

        prev_summaries = []
        completed = session.get_completed_chapters()

        for chapter in chapters:
            idx = chapter["index"]
            if idx in completed:
                content = session.load_chapter(idx, chapter["title"])
                summary = session.load_summary(idx, chapter["title"])
                if summary:
                    prev_summaries.append(summary)
                bridge.push("chapter_done", {
                    "chapter": idx, "title": chapter["title"],
                    "chars": len(content), "cached": True,
                })
                continue

            chapter_materials = ""
            for ch in pool.get("chapters", []):
                if ch.get("index") == idx:
                    chapter_materials = ch.get("materials", "")
                    break

            bridge.push("chapter_start", {
                "chapter": idx, "title": chapter["title"],
            })

            content_parts = []
            for token in generate_chapter_stream(
                chapter, chapter_materials,
                meta.get("requirement", ""),
                chapters, prev_summaries,
            ):
                content_parts.append(token)
                bridge.push("chunk", {"chapter": idx, "text": token})

            content = "".join(content_parts)
            summary = summarize_chapter(chapter["title"], content)
            session.save_chapter(idx, chapter["title"], content)
            session.save_summary(idx, chapter["title"], summary)
            prev_summaries.append(summary)

            bridge.push("chapter_done", {
                "chapter": idx, "title": chapter["title"],
                "chars": len(content),
            })

        bridge.push("all_done", {"total_chapters": len(chapters)})
        bridge.finish()

    @app.route("/api/sessions/<sid>/generate", methods=["POST"])
    def trigger_generate(sid):
        session = SessionManager(SESSIONS_DIR / sid)
        session.update_phase("生成")

        bridge = StreamBridge.get(sid)
        bridge.reset()

        thread = threading.Thread(target=_generate_worker, args=(sid,), daemon=True)
        thread.start()

        return jsonify({"status": "generating"}), 202

    @app.route("/api/sessions/<sid>/stream")
    def stream(sid):
        bridge = StreamBridge.get(sid)

        def generate():
            for event, data in bridge.events():
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        return Response(generate(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    # ── 章节查询与修改 ────────────────────────────────

    @app.route("/api/sessions/<sid>/chapters", methods=["GET"])
    def list_chapters(sid):
        session = SessionManager(SESSIONS_DIR / sid)
        chapters = json.loads(session.template_path.read_text(encoding="utf-8"))
        completed = session.get_completed_chapters()
        result = []
        for c in chapters:
            idx = c["index"]
            content = session.load_chapter(idx, c["title"]) if idx in completed else ""
            result.append({
                "index": idx,
                "title": c["title"],
                "description": c["description"],
                "chars": len(content),
                "done": idx in completed,
            })
        return jsonify({"chapters": result}), 200

    @app.route("/api/sessions/<sid>/chapters/<int:n>", methods=["GET"])
    def get_chapter(sid, n):
        session = SessionManager(SESSIONS_DIR / sid)
        chapters = json.loads(session.template_path.read_text(encoding="utf-8"))
        chapter = next((c for c in chapters if c["index"] == n), None)
        if not chapter:
            return jsonify({"error": "章节不存在"}), 404
        content = session.load_chapter(n, chapter["title"])
        return jsonify({"index": n, "title": chapter["title"], "content": content}), 200

    @app.route("/api/sessions/<sid>/chapters/<int:n>/revise", methods=["POST"])
    def revise_chapter_api(sid, n):
        session = SessionManager(SESSIONS_DIR / sid)
        data = request.get_json()
        feedback = data.get("feedback", "")
        chapters = json.loads(session.template_path.read_text(encoding="utf-8"))
        chapter = next((c for c in chapters if c["index"] == n), None)
        if not chapter:
            return jsonify({"error": "章节不存在"}), 404
        content = session.load_chapter(n, chapter["title"])
        revised = revise_chapter(chapter["title"], content, feedback)
        session.save_chapter(n, chapter["title"], revised)
        return jsonify({"index": n, "title": chapter["title"], "content": revised}), 200

    @app.route("/api/sessions/<sid>/revise-global", methods=["POST"])
    def revise_global(sid):
        session = SessionManager(SESSIONS_DIR / sid)
        data = request.get_json()
        feedback = data.get("feedback", "")
        chapters = json.loads(session.template_path.read_text(encoding="utf-8"))
        parts = []
        for c in chapters:
            content = session.load_chapter(c["index"], c["title"])
            if content:
                parts.append(content)
        full_doc = "\n\n".join(parts)
        revised = revise_document(full_doc, feedback)

        for i, c in enumerate(chapters):
            session.save_chapter(c["index"], c["title"], revised)

        return jsonify({"content": revised}), 200

    # ── 文档输出 ──────────────────────────────────────

    @app.route("/api/sessions/<sid>/output", methods=["GET"])
    def get_output(sid):
        session = SessionManager(SESSIONS_DIR / sid)
        if session.output_path.exists():
            content = session.output_path.read_text(encoding="utf-8")
            return jsonify({"content": content}), 200

        chapters = json.loads(session.template_path.read_text(encoding="utf-8"))
        parts = []
        for c in chapters:
            content = session.load_chapter(c["index"], c["title"])
            if content:
                parts.append(content)
        full_doc = "\n\n".join(parts)
        session.save_output(full_doc)
        session.update_phase("完成")
        return jsonify({"content": full_doc}), 200

    # ── 前端静态文件 ──────────────────────────────────

    @app.route("/")
    def index():
        return send_from_directory("../frontend", "index.html")

    return app
