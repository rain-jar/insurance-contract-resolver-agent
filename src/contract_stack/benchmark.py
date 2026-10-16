from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_benchmark(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["cases"]
