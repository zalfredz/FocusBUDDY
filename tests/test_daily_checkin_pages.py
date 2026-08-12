"""Regresi UI untuk check-in harian dua halaman."""
from __future__ import annotations

from types import SimpleNamespace

import flet as ft

from app import buddy, storage
from app.views import daily_checkin, home, task_add


class FakePage:
    def __init__(self) -> None:
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from walk(child)
    yield from walk(getattr(control, "content", None))


def button(root, label: str):
    return next(
        (
            control
            for control in walk(root)
            if getattr(control, "on_click", None) is not None
            and any(
                getattr(descendant, "value", None) == label
                for descendant in walk(getattr(control, "content", None))
            )
        ),
        None,
    )


def images(root) -> set[str]:
    return {
        control.src
        for control in walk(root)
        if isinstance(control, ft.Image) and isinstance(control.src, str)
    }


def texts(root) -> list[str]:
    return [
        control.value
        for control in walk(root)
        if isinstance(getattr(control, "value", None), str)
    ]


def prepare_storage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "DATA_FILE", tmp_path / "data.json")
    monkeypatch.setattr(storage, "BACKUP_FILE", tmp_path / "data.json.bak")
    storage.reset_all_data()


def test_daily_checkin_is_two_full_pages_and_saves(monkeypatch, tmp_path) -> None:
    prepare_storage(monkeypatch, tmp_path)
    page = FakePage()
    routes: list[str] = []
    root = daily_checkin.build(page, routes.append)

    assert root.bgcolor == "#343446"
    first_images = images(root)
    assert "Property 1=bad_mood.png" in first_images
    assert {buddy.asset_for(mood) for mood in buddy.MOOD_ORDER} <= first_images

    sad = button(root, "Sedih")
    assert sad is not None
    sad.on_click(SimpleNamespace(control=sad))

    lanjut = button(root, "Lanjut")
    assert lanjut is not None
    lanjut.on_click(SimpleNamespace(control=lanjut))

    assert "Property 1=bad_mood (1).png" in images(root)
    assert button(root, "1") is not None
    assert button(root, "6") is not None

    for level, expected_asset in (
        (1, "Property 1=bad_mood (1).png"),
        (2, "Property 1=bad_mood (1).png"),
        (3, "Property 1=med_mood (1).png"),
        (4, "Property 1=med_mood (1).png"),
        (5, "Property 1=good_mood (5).png"),
        (6, "Property 1=good_mood (5).png"),
    ):
        choice = button(root, str(level))
        assert choice is not None
        choice.on_click(SimpleNamespace(control=choice))
        assert expected_asset in images(root)

    lanjut = button(root, "Lanjut")
    assert lanjut is not None
    lanjut.on_click(SimpleNamespace(control=lanjut))

    assert routes == ["home"]
    assert storage.today_mood()["mood"] == "sedih"
    assert storage.today_mood()["energy"] == 6
    assert storage.today_energy() == 6


def test_home_uses_checkin_energy_mood_and_has_no_meal_popup(
    monkeypatch, tmp_path
) -> None:
    prepare_storage(monkeypatch, tmp_path)
    state = storage.load_state()
    state["profile"].update({"name": "Ari", "onboarded": True})
    storage.save_state(state)
    storage.add_mood_log("cemas", buddy.score_for("cemas"), 2)
    storage.set_today_energy(2)

    page = FakePage()
    page.dialogs = []
    page.overlay = []
    page.run_task = lambda fn, *args: None
    page.show_dialog = page.dialogs.append
    root = home.build(page, lambda route: None)
    shown = texts(root)

    assert "Hai!, Ari" in shown
    assert "Kurang Bertenaga" in shown
    assert "Nggak ada tugas hari ini Ari, nikmati aja" in shown
    assert "kalem_cemas.svg" in images(root)
    assert "Ada yang keinget?" in shown
    assert "Kewalahan? Ambil Jeda Dulu" in shown
    assert not page.dialogs

    controls = list(walk(root))
    greeting = next(control for control in controls if getattr(control, "value", None) == "Hai!, Ari")
    task_copy = next(
        control
        for control in controls
        if getattr(control, "value", "").startswith("Nggak ada tugas hari ini")
    )
    capture = next(
        control
        for control in controls
        if isinstance(control, ft.Container)
        and control.bgcolor == "#DDE0FF"
        and "Ada yang keinget?" in texts(control)
    )
    reset_gradient = next(
        control.gradient
        for control in controls
        if isinstance(control, ft.Container)
        and isinstance(control.gradient, ft.LinearGradient)
    )
    reset_face = next(
        control
        for control in controls
        if isinstance(control, ft.Image)
        and control.src == "kalem_cemas.svg"
        and control.width == 60
    )

    assert home.HOME_CONTENT_WIDTH == 320
    assert greeting.size == 35 and greeting.weight == ft.FontWeight.W_900
    assert greeting.style.letter_spacing == 1.1
    assert task_copy.size == 21
    assert capture.height == 42
    assert reset_gradient.colors == ["#95D899", "#95D899", "#AEEEF8"]
    assert reset_gradient.stops == [0.0, 0.8, 1.0]
    assert reset_face.left == -10


def test_home_add_task_opens_dedicated_page(monkeypatch, tmp_path) -> None:
    prepare_storage(monkeypatch, tmp_path)
    state = storage.load_state()
    state["profile"].update({"name": "Ari", "onboarded": True})
    storage.save_state(state)
    storage.add_mood_log("tenang", buddy.score_for("tenang"), 4)

    routes: list[str] = []
    page = FakePage()
    page.dialogs = []
    page.overlay = []
    page.run_task = lambda fn, *args: None
    page.show_dialog = page.dialogs.append
    root = home.build(page, routes.append)
    add = button(root, "Tambah tugas")

    assert add is not None
    add.on_click(SimpleNamespace(control=add))
    assert routes == ["task_add"]


def test_task_add_page_saves_and_returns_home(monkeypatch, tmp_path) -> None:
    from app import main as main_module

    prepare_storage(monkeypatch, tmp_path)
    estimate = SimpleNamespace(
        menit=30,
        model_version="test",
        global_minutes=30,
        global_dataset_version="test-data",
        global_artifact_sha256="test-sha",
        personalization_version="",
        personalization_dataset_version="",
        sumber="test",
    )
    monkeypatch.setattr(task_add.duration_predictions, "predict", lambda *a, **k: estimate)

    page = FakePage()
    page.dialogs = []
    page.show_dialog = page.dialogs.append
    routes: list[str] = []
    root = task_add.build(page, routes.append)
    fields = [control for control in walk(root) if isinstance(control, ft.TextField)]
    title = next(field for field in fields if field.hint_text == "Nama Tugas")
    description = next(field for field in fields if field.hint_text == "Deskripsi Tugas")
    title.value = "Siapkan alat tulis"
    description.value = "Pensil dan kalkulator"

    save = button(root, "Tambah")
    assert save is not None
    save.on_click(SimpleNamespace(control=save))

    tasks = storage.get_tasks()
    assert routes == ["home"]
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Siapkan alat tulis"
    assert tasks[0]["description"] == "Pensil dan kalkulator"
    assert tasks[0]["deadline_time"] == "07:00"
    assert root.bgcolor == "#141416"
    assert main_module.ROUTES["task_add"] is task_add.build
    assert "task_add" in main_module.FULLSCREEN_ROUTES


def test_home_energy_copy_matches_all_ranges() -> None:
    assert [home._energy_label(level) for level in range(1, 7)] == [
        "Kurang Bertenaga",
        "Kurang Bertenaga",
        "Bertenaga",
        "Bertenaga",
        "Sangat Bertenaga",
        "Sangat Bertenaga",
    ]
