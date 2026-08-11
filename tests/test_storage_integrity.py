"""Tes ketahanan dan pemulihan storage."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import storage


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  [OK] " if condition else "  [FAIL] ") + message)
    if not condition:
        FAILURES.append(message)


class TemporaryStorage:
    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory(prefix="focusbuddy_storage_")
        self.old = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
        storage.DATA_DIR = Path(self.directory.name)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        return self

    def __exit__(self, *_):
        storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = self.old
        self.directory.cleanup()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def scenario_corruption_and_backup() -> None:
    print("\n=== Storage: corrupt JSON dan backup ===")
    with TemporaryStorage():
        backup = storage._default_state()
        backup["profile"]["name"] = "Dari backup"
        write_json(storage.BACKUP_FILE, backup)
        storage.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        storage.DATA_FILE.write_text("{json rusak", encoding="utf-8")

        restored = storage.load_state()
        check(restored["profile"]["name"] == "Dari backup",
              "primary rusak -> state valid dipulihkan dari backup")
        check(json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))["profile"]["name"] == "Dari backup",
              "recovery menulis ulang primary valid, bukan hanya membaca backup sementara")

    with TemporaryStorage():
        storage.DATA_DIR.mkdir(parents=True, exist_ok=True)
        storage.DATA_FILE.write_text("{rusak", encoding="utf-8")
        storage.BACKUP_FILE.write_text("[juga rusak", encoding="utf-8")
        state = storage.load_state()
        check(state["schema"] == storage.SCHEMA_VERSION and state["tasks"] == [],
              "primary+backup rusak -> default aman, tidak crash")


def scenario_interrupted_write_and_migration() -> None:
    print("\n=== Storage: write terputus, field hilang, dan schema lama ===")
    with TemporaryStorage():
        state = storage._default_state()
        state["profile"]["name"] = "State utuh"
        storage.save_state(state)
        storage.DATA_FILE.with_suffix(".json.tmp").write_text("{setengah", encoding="utf-8")
        loaded = storage.load_state()
        check(loaded["profile"]["name"] == "State utuh",
              "file temporary sisa dari write terputus tidak menimpa primary atomik")

    with TemporaryStorage():
        write_json(storage.DATA_FILE, {
            "schema": 1,
            "profile": {"name": "Data lama", "onboarded": True, "status": "mahasiswa"},
            "tasks": [{"title": "Tugas lama", "deadline": "2026-08-10", "urgent": True}],
            "mood_logs": [],
        })
        migrated = storage.load_state()
        check(migrated["profile"]["status"] == ["mahasiswa"] and migrated["tasks"][0]["title"] == "Tugas lama",
              "schema lama dimigrasikan tanpa membuang profil atau tugas")
        check("decision_records" in migrated and "decompose_records" in migrated,
              "schema lama mendapat field baru yang diperlukan")
        check(migrated["tasks"][0]["scheduled_date"] == "2026-08-10",
              "task lama memakai deadline lamanya sebagai tanggal kerja awal")

    with TemporaryStorage():
        current = storage._default_state()
        current["tasks"] = [{
            "id": "task-current",
            "title": "Task sebelum scheduled_date",
            "deadline": "2026-08-12",
            "steps": [{"text": "Mulai", "done": False}],
        }]
        write_json(storage.DATA_FILE, current)
        loaded = storage.load_state()
        check(loaded["tasks"][0]["scheduled_date"] == "2026-08-12",
              "state schema saat ini juga dinormalisasi tanpa kehilangan jadwal task")

    with TemporaryStorage():
        malformed = storage._default_state()
        malformed["profile"] = "bukan objek"
        malformed["tasks"] = "bukan daftar"
        malformed.pop("favorites")
        write_json(storage.DATA_FILE, malformed)
        loaded = storage.load_state()
        check(isinstance(loaded["profile"], dict) and isinstance(loaded["tasks"], list),
              "state schema saat ini tetapi bertipe rusak dinormalisasi, tidak membuat app crash")
        check(isinstance(loaded["favorites"], dict),
              "root field hilang dibangun kembali dengan bentuk yang benar")


def main() -> int:
    scenario_corruption_and_backup()
    scenario_interrupted_write_and_migration()
    print("\n" + "=" * 60)
    if FAILURES:
        print(f"GAGAL: {len(FAILURES)}")
        return 1
    print("SEMUA KONTRAK STORAGE LULUS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
