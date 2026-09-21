from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class IngestionError(Exception):
    code: str
    message: str
    stage: str
    recoverable: bool = False
    user_action: Optional[str] = None

    def __post_init__(self):
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return asdict(self)
