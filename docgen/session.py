import json
import uuid
from datetime import datetime
from pathlib import Path
from docgen.config import SESSIONS_DIR


class SessionManager:
    def __init__(self, session_dir: Path | None = None):
        if session_dir:
            self.dir = Path(session_dir)
        else:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{uuid.uuid4().hex[:6]}"
            self.dir = SESSIONS_DIR / session_id

        self.meta_path = self.dir / "meta.json"
        self.template_path = self.dir / "template.json"
        self.pool_path = self.dir / "source_pool.json"
        self.chapters_dir = self.dir / "chapters"
        self.output_path = self.dir / "output.md"

    @property
    def session_id(self) -> str:
        return self.dir.name

    def init_session(self, requirement: str, template_path: str, source_paths: list[str]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.chapters_dir.mkdir(exist_ok=True)
        meta = {
            "session_id": self.session_id,
            "created_at": datetime.now().isoformat(),
            "requirement": requirement,
            "template_path": str(template_path),
            "source_paths": [str(p) for p in source_paths],
            "phase": "准备",
        }
        self.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_meta(self) -> dict:
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def update_phase(self, phase: str) -> None:
        meta = self.load_meta()
        meta["phase"] = phase
        self.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_materials(self, pool: dict) -> None:
        self.pool_path.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_materials(self) -> dict:
        return json.loads(self.pool_path.read_text(encoding="utf-8"))

    def save_chapter(self, index: int, title: str, content: str) -> Path:
        safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in title)
        filename = f"{index:02d}-{safe_title}.md"
        path = self.chapters_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def save_summary(self, index: int, title: str, summary: str) -> Path:
        safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in title)
        filename = f"{index:02d}-{safe_title}.summary"
        path = self.chapters_dir / filename
        path.write_text(summary, encoding="utf-8")
        return path

    def load_chapter(self, index: int, title: str) -> str:
        safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in title)
        path = self.chapters_dir / f"{index:02d}-{safe_title}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def load_summary(self, index: int, title: str) -> str:
        safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in title)
        path = self.chapters_dir / f"{index:02d}-{safe_title}.summary"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_completed_chapters(self) -> list[int]:
        """返回已完成的章节 index 列表。"""
        indices = []
        for f in sorted(self.chapters_dir.glob("*.md")):
            try:
                idx = int(f.name.split("-")[0])
                indices.append(idx)
            except (ValueError, IndexError):
                pass
        return indices

    def save_output(self, content: str) -> Path:
        self.output_path.write_text(content, encoding="utf-8")
        return self.output_path

    def can_resume(self) -> bool:
        return self.meta_path.exists()

    def detect_resume_point(self) -> str:
        """检测中断恢复点。返回: '准备' / '提取' / '生成' / '完成'"""
        if not self.meta_path.exists():
            return "准备"
        if self.pool_path.exists():
            completed = self.get_completed_chapters()
            if completed:
                return "生成"
            return "提取"
        return "准备"
