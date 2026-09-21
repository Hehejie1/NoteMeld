import json
from datetime import datetime, timezone
from pathlib import Path


class WikiJobStore:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self.output_dir / f"{task_id}_wiki_job.json"

    def _atomic_write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def write(
        self,
        task_id: str,
        status: str,
        stage: str = "",
        error: str = "",
        reason: str = "",
        detail: str = "",
        recoverable: bool = False,
    ) -> dict:
        payload = {
            "task_id": task_id,
            "status": status,
            "stage": stage,
            "error": error,
            "reason": reason,
            "detail": detail or error,
            "recoverable": recoverable,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._atomic_write_json(self._path(task_id), payload)
        return payload

    def cancel(self, task_id: str) -> dict:
        return self.write(
            task_id,
            "canceled",
            stage="canceled",
            reason="user_canceled",
            detail="用户已取消 Wiki 提取",
            recoverable=False,
        )

    def read(self, task_id: str) -> dict:
        path = self._path(task_id)
        if not path.exists():
            return {
                "task_id": task_id,
                "status": "pending",
                "stage": "",
                "error": "",
                "reason": "",
                "detail": "",
                "recoverable": False,
                "updated_at": "",
            }
        return json.loads(path.read_text(encoding="utf-8"))
