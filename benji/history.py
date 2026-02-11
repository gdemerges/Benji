import json
import os
from datetime import datetime
from pathlib import Path


class TranscriptionHistory:
    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        cache_dir = Path.home() / ".cache" / "benji"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = cache_dir / "history.jsonl"

    def add(self, text: str):
        """Add a transcription to history."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "text": text,
        }
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._trim_if_needed()

    def _trim_if_needed(self):
        """Keep only the last max_entries."""
        if not self.history_file.exists():
            return
        with open(self.history_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > self.max_entries:
            with open(self.history_file, "w", encoding="utf-8") as f:
                f.writelines(lines[-self.max_entries :])

    def get_recent(self, n: int = 50) -> list[dict]:
        """Get the n most recent transcriptions."""
        if not self.history_file.exists():
            return []
        with open(self.history_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entries = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(entries))  # Most recent first

    def clear(self):
        """Clear all history."""
        if self.history_file.exists():
            self.history_file.unlink()
