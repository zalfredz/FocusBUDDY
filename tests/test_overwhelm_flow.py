"""Behavior contract untuk recovery loop OVERWHELM."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

from app import clock, storage
from app.core import kalem_engine
from app.core.reset_preferences import CRISIS_HOTLINES, TELEHEALTH_PARTNERS
from app.views import reset
from models.model_overwhelm import Risiko


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  [OK] " if condition else "  [FAIL] ") + message)
    if not condition:
        FAILURES.append(message)


class FakePage:
    def __init__(self) -> None:
        self.dialogs: list = []
        self.overlay: list = []
        self.tasks: list[tuple] = []

    def update(self) -> None:
        pass

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, fn, *args) -> None:
        self.tasks.append((fn, args))


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from walk(child)
    for action in getattr(control, "actions", []) or []:
        yield from walk(action)
    yield from walk(getattr(control, "content", None))


def texts(root) -> list[str]:
    return [
        control.value
        for control in walk(root)
        if isinstance(getattr(control, "value", None), str)
    ]


def button(root, label: str):
    for control in walk(root):
        if getattr(control, "on_click", None) is None:
            continue
        content = getattr(control, "content", None)
        if getattr(content, "value", None) == label:
            return control
    return None


def click(root, label: str) -> None:
    control = button(root, label)
    check(control is not None, f"tombol '{label}' tersedia")
    if control is not None:
        control.on_click(SimpleNamespace(control=control))


def finish_grounding(root) -> None:
    for count in (5, 4, 3, 2, 1):
        check(str(count) in texts(root), f"grounding menampilkan tahap {count}")
        click(root, "Udah")


async def _no_sleep(*args, **kwargs) -> None:
    return None


def finish_latest_breathing(page: FakePage) -> None:
    check(bool(page.tasks), "satu sesi napas dijadwalkan")
    if not page.tasks:
        return
    fn, args = page.tasks.pop(0)
    with patch("app.views.reset.asyncio.sleep", _no_sleep):
        asyncio.run(fn(*args))


def finish_completion_transition(page: FakePage) -> None:
    check(bool(page.tasks), "transisi selesai dijadwalkan selama tiga detik")
    if not page.tasks:
        return
    fn, args = page.tasks.pop(0)
    with patch("app.views.reset.asyncio.sleep", _no_sleep):
        asyncio.run(fn(*args))


def prepare() -> None:
    state = storage.reset_all_data()
    state["profile"].update({"name": "Ari", "onboarded": True})
    storage.save_state(state)
    storage.add_mood_log("cemas", 2, 2)


def scenario_retry_loop() -> None:
    print("\n=== CASE A: belum bisa mengulang grounding → napas → check-in ===")
    page = FakePage()
    routes: list[str] = []
    root = reset.build(page, routes.append)
    initial = texts(root)
    check("Balik ke sini dulu." in initial, "OVERWHELM langsung membuka grounding")
    check("Gerak 60 detik" not in initial, "Gerak 60 detik tidak muncul")
    check("Dengerin musik nenangin" not in initial,
          "Dengerin musik nenangin tidak muncul")

    finish_grounding(root)
    completion = texts(root)
    check("Frame 2.png" in [getattr(control, "src", None) for control in walk(root)],
          "grounding menampilkan layar selesai sebelum latihan napas")
    finish_completion_transition(page)
    breathing = texts(root)
    check("Latihan napas 4-7-8" in breathing,
          "grounding langsung berlanjut ke napas tanpa menu pilihan")
    finish_latest_breathing(page)
    outcome = texts(root)
    check("Sekarang rasanya gimana?" in outcome, "satu sesi napas langsung ke check-in")
    check("Latihan napas 4-7-8" not in outcome,
          "check-in tidak meminta user memilih napas berkali-kali")

    click(root, "Belum bisa")
    check("Balik ke sini dulu." in texts(root),
          "Belum bisa tetap di recovery dan mengulang grounding")
    check(not routes, "Belum bisa tidak kembali ke Home")

    finish_grounding(root)
    finish_completion_transition(page)
    finish_latest_breathing(page)
    check("Sekarang rasanya gimana?" in texts(root),
          "loop kedua kembali meminta outcome user")

    events = storage.get_reset_events()
    check(len(events) == 1 and events[0].get("choice") == reset.EVENT_CHOICE,
          "satu recovery hanya menjadi satu sinyal OVERWHELM untuk decision model")
    stages = [stage.get("name") for stage in events[0].get("stages", [])]
    check(stages.count(reset.STAGE_OPEN) == 1, "pembukaan OVERWHELM tercatat")
    check(stages.count(reset.STAGE_GROUNDING_DONE) == 2,
          "dua grounding selesai tercatat terpisah")
    check(stages.count(reset.STAGE_BREATHING_DONE) == 2,
          "dua sesi napas selesai tercatat terpisah")
    check(stages.count(reset.STAGE_RETRY) == 1, "pengulangan recovery tercatat")
    check(
        stages.count(reset.STAGE_CHECKIN_NOT_READY) == 1
        and events[0].get("completed") is False
        and events[0].get("improved") is None,
        "Belum bisa tercatat tetapi belum dianggap recovery berhasil",
    )


def scenario_improved_and_light_menu() -> None:
    print("\n=== CASE B: sedikit lebih baik membuka recovery ringan ===")
    page = FakePage()
    routes: list[str] = []
    root = reset.build(page, routes.append)
    finish_grounding(root)
    finish_completion_transition(page)
    finish_latest_breathing(page)
    click(root, "Sedikit lebih baik")

    light = texts(root)
    for label in ("Balik ke sini", "Latihan napas 4-7-8"):
        check(label in light, f"recovery ringan menyediakan '{label}'")
    check("NGOBROL DENGAN PROFESIONAL" in light,
          "bantuan profesional langsung tampil sebagai card")
    check(button(root, "Ngobrol dengan profesional") is None,
          "bantuan profesional bukan tombol ketiga")
    check("Gerak 60 detik" not in light, "recovery ringan tidak memuat Gerak 60 detik")
    check("Dengerin musik nenangin" not in light,
          "recovery ringan tidak memuat musik nenangin")
    check(not routes, "Sedikit lebih baik tidak otomatis kembali ke Home")

    outcomes = storage.get_reset_events()
    stages = [stage.get("name") for stage in outcomes[0].get("stages", [])]
    check(
        len(outcomes) == 1
        and outcomes[0].get("completed") is True
        and outcomes[0].get("improved") is True
        and reset.STAGE_CHECKIN_IMPROVED in stages,
        "Sedikit lebih baik tercatat dari jawaban user",
    )

    check(any(partner["name"] in light for partner in TELEHEALTH_PARTNERS),
          "card profesional memakai partner yang sudah ada")
    urls = {
        getattr(control, "url", None)
        for control in walk(root)
        if getattr(control, "url", None)
    }
    expected_urls = {
        *(partner["url"] for partner in TELEHEALTH_PARTNERS),
        *(hotline["tel"] for hotline in CRISIS_HOTLINES),
    }
    check(expected_urls.issubset(urls),
          "card profesional mempertahankan link dan hotline existing")

    task = storage.add_task(
        "Lanjut pelan-pelan",
        clock.today().isoformat(),
        menit_est=30,
        steps=[{"text": "Buka catatan", "done": False}],
    )
    storage.set_today_energy(4)
    profile, day = kalem_engine.snapshot()
    with patch(
        "models.model_overwhelm.nilai",
        return_value=Risiko(0, "tenang", "test"),
    ):
        decision = kalem_engine.decide(profile, day)
    check(
        decision.action_kind == "focus"
        and decision.task
        and decision.task["id"] == task["id"]
        and decision.focus_minutes <= 10
        and decision.context_event_id == outcomes[0]["id"],
        "outcome sedikit lebih baik tersambung ke next action existing yang diringankan",
    )


def main() -> int:
    original = storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE
    with tempfile.TemporaryDirectory(prefix="focusbuddy_overwhelm_") as directory:
        storage.DATA_DIR = Path(directory)
        storage.DATA_FILE = storage.DATA_DIR / "data.json"
        storage.BACKUP_FILE = storage.DATA_DIR / "data.json.bak"
        try:
            prepare()
            scenario_retry_loop()
            prepare()
            scenario_improved_and_light_menu()
        finally:
            storage.DATA_DIR, storage.DATA_FILE, storage.BACKUP_FILE = original

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"GAGAL: {len(FAILURES)} behavior OVERWHELM belum terpenuhi")
        return 1
    print("SEMUA BEHAVIOR OVERWHELM LULUS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
