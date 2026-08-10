"""SettingDemo harus menguji engine nyata tanpa menyentuh data pengguna."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import SettingDemo
from app import storage


def main() -> int:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_demo_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        try:
            assert len(SettingDemo.SCENARIOS) == 10, "demo harus tetap punya 10 skenario inti"
            assert set(SettingDemo.SCENARIOS) == set(SettingDemo.DEMO_OBJECTIVES), "set skenario/objective harus sama"
            results = {key: SettingDemo.run_demo(key) for key in SettingDemo.SCENARIOS}
        finally:
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original

    # `after_reset` adalah gap produk yang disengaja, bukan PASS palsu.
    assert results["after_reset"]["passed"] is False, "gap recovery harus terlihat gagal secara jujur"
    assert any(item["passed"] is False for item in results["after_reset"]["checks"])
    assert all(result["passed"] in (True, False) for result in results.values())
    print("10 skenario demo menjalankan pipeline nyata; after_reset tetap gap yang eksplisit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
