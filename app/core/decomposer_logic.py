"""Orkestrasi pecah tugas: manual, retrieval lokal, lalu fallback generatif KALEM."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from app import clock
from app.core import ai_client

from app.core.kalem_engine import ENERGY_BLOCKS

RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "tugas": {"type": "string", "description": "Judul tugas asli, disalin persis"},
            "langkah": {"type": "string", "description": "Satu langkah konkret yang kecil"},
        },
        "required": ["tugas", "langkah"],
    },
}

MAX_LANGKAH_PER_TUGAS = 5

SYSTEM_PROMPT = (
    "Kamu asisten yang bantu orang dengan ADHD/executive dysfunction menyusun "
    "rencana kerja HARI INI. Kamu dikasih daftar tugas beserta perkiraan durasi "
    "yang SUDAH dihitung sistem. Tugas kamu CUMA memecah tiap tugas jadi langkah "
    "konkret yang kecil. JANGAN nyebut durasi/menit sama sekali. Aturan: langkah "
    "pertama tiap tugas harus yang paling ringan (bisa dimulai dalam sekali duduk), "
    "bahasa Indonesia santai, jangan pakai jargon, maksimal 5 langkah per tugas. "
    "Field 'tugas' harus disalin persis dari judul yang dikasih.\n\n"
    "PENTING soal sumber langkah: beberapa tugas di bawah punya baris "
    "'Deskripsi'. Kalau ADA, langkah-langkahnya HARUS dipecah dari ISI "
    "deskripsi itu -- itu konteks nyata soal APA yang mau dikerjain "
    "(mis. deskripsi 'bikin proposal buat hackathon, cari tim dulu' harus "
    "jadi langkah kayak 'cari 1-2 orang buat diajak bareng', bukan cuma "
    "'buka dokumen proposal'). Judul di situ cuma LABEL, bukan sumber isi. "
    "Kalau tugas TIDAK punya deskripsi, pecah dari judulnya aja seperti biasa."
)

PORSI_LANGKAH_PERTAMA = 0.15
MENIT_LANGKAH_PERTAMA_MAKS = 5


@dataclass
class TimeBlock:
    start: str
    end: str
    task_title: str
    step: str
    is_break: bool = False


@dataclass
class PlanResult:
    blocks: list[TimeBlock]
    source: str
    total_minutes: int
    reason: str = ""
    steps: list[tuple[str, str, int]] = field(default_factory=list)
    task_steps: dict[str, list[dict]] = field(default_factory=dict)
    n_lokal: int = 0
    n_ai: int = 0


def task_plan_key(task: dict, fallback: str = "") -> str:
    task_id = str(task.get("id") or fallback)
    occurrence = str(task.get("_occurrence_date") or "")
    return f"{task_id}::{occurrence}" if occurrence else task_id


def _fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _garis_deskripsi(description: str) -> list[str]:
    baris = [b.strip(" \t-•*").strip() for b in (description or "").splitlines()]
    baris = [b for b in baris if b]
    return baris if len(baris) >= 2 else []


def _rule_based_steps(tasks: list[dict], energy_level: int) -> list[tuple[str, str, int]]:
    focus_min, _ = ENERGY_BLOCKS.get(energy_level, ENERGY_BLOCKS[3])
    menit_per_tugas = perkiraan_menit(tasks, energy_level)
    out: list[tuple[str, str, int]] = []
    for task in tasks:
        title = task["title"]
        baris = _garis_deskripsi(task.get("description", ""))
        if baris:
            bagian = _bagi_menit(menit_per_tugas.get(title, 30), len(baris))
            out.extend((title, langkah, menit) for langkah, menit in zip(baris, bagian))
            continue
        out.append((title, f"Siapin bahan/alat buat '{title}'", 5))
        out.append((title, f"Kerjain bagian paling awal dari '{title}'", focus_min))
        out.append((title, f"Rapikan & cek hasil '{title}'", max(focus_min // 2, 5)))
    return out


def perkiraan_menit(tasks: list[dict], energy_level: int) -> dict[str, int]:
    from app import storage
    from models import model_durasi

    records = storage.get_focus_records()
    hasil: dict[str, int] = {}
    for t in tasks:
        if t.get("menit_est"):
            hasil[t["title"]] = int(t["menit_est"])
            continue
        batas = storage.deadline_at(t)
        tempo_hari = (
            max(0, int((batas - clock.now()).total_seconds() // 86_400))
            if batas is not None
            else 7
        )
        est = model_durasi.perkirakan(
            t["title"],
            tempo_hari=tempo_hari,
            penting=8 if t.get("important") else 4,
            kategori=t.get("kategori", ""),
            jumlah=t.get("jumlah_unit", 0),
            records=records,
            energi=energy_level,
        )
        hasil[t["title"]] = est.menit
    return hasil


def _bagi_menit(total: int, n_langkah: int) -> list[int]:
    if n_langkah <= 0:
        return []
    if n_langkah == 1:
        return [max(3, total)]
    pertama = max(3, min(int(total * PORSI_LANGKAH_PERTAMA), MENIT_LANGKAH_PERTAMA_MAKS))
    sisa = max(total - pertama, (n_langkah - 1) * 3)
    per = sisa // (n_langkah - 1)
    bagian = [pertama] + [max(3, per)] * (n_langkah - 1)
    bagian[-1] += max(0, total - sum(bagian))
    return bagian


def _ai_steps(
    tasks: list[dict], energy_level: int
) -> tuple[Optional[list[tuple[str, str, int]]], str]:
    menit_per_tugas = perkiraan_menit(tasks, energy_level)

    def _baris_tugas(t: dict) -> str:
        from app import storage

        baris = f"- {t['title']} (~{menit_per_tugas.get(t['title'], 30)} menit)"
        deskripsi = (t.get("description") or "").strip()
        if deskripsi:
            baris += f"\n  Deskripsi: {deskripsi}"
        batas = storage.deadline_at(t)
        if batas is not None:
            status = "sudah lewat" if batas < clock.now() else "belum lewat"
            baris += f"\n  Deadline: {batas.strftime('%Y-%m-%d %H:%M')} ({status})"
        else:
            baris += "\n  Deadline: tidak ada"
        return baris

    task_lines = "\n".join(_baris_tugas(t) for t in tasks)

    parsed, reason = ai_client.generate_json(
        system_instruction=SYSTEM_PROMPT,
        prompt=(
            f"Tugas hari ini:\n{task_lines}\n\n"
            f"Energi user: {energy_level}/6 (1 = capek banget, 6 = penuh energi). "
            "Makin rendah energinya, makin kecil langkahnya.\n"
            "Pecah jadi langkah. Jangan sebut menit."
        ),
        schema=RESPONSE_SCHEMA,
        temperature=0.2,
    )
    if not parsed:
        return None, reason or "balasan AI kosong"

    def teks_langkah(value) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, list):
            result: list[str] = []
            for child in value:
                result.extend(teks_langkah(child))
            return result
        if isinstance(value, dict):
            for key in ("langkah", "step", "text", "isi"):
                if key in value:
                    return teks_langkah(value[key])
        return []

    per_tugas: dict[str, list[str]] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        raw_title = item.get("tugas", "")
        title_text = raw_title.strip() if isinstance(raw_title, str) else ""
        title = _match_title(title_text, tasks) or (
            tasks[0]["title"] if len(tasks) == 1 else None
        )
        if not title:
            continue
        bucket = per_tugas.setdefault(title, [])
        for step in teks_langkah(item.get("langkah", "")):
            if step not in bucket and len(bucket) < MAX_LANGKAH_PER_TUGAS:
                bucket.append(step)

    steps: list[tuple[str, str, int]] = []
    for t in tasks:
        judul = t["title"]
        daftar = per_tugas.get(judul)
        if not daftar:
            continue
        bagian = _bagi_menit(menit_per_tugas.get(judul, 30), len(daftar))
        for langkah, menit in zip(daftar, bagian):
            steps.append((judul, langkah, max(3, min(menit, 120))))

    if not steps:
        return None, "balasan AI kosong"
    return steps, ""


def _match_title(title: str, tasks: list[dict]) -> Optional[str]:
    if not title:
        return None
    titles = [t["title"] for t in tasks]
    if title in titles:
        return title
    low = title.lower().strip()
    for original in titles:
        o = original.lower().strip()
        if low == o or low in o or o in low:
            return original
    return None


def lay_out(
    steps: list[tuple[str, str, int]],
    energy_level: int = 3,
    start_at: Optional[datetime] = None,
) -> tuple[list[TimeBlock], int]:
    _, break_min = ENERGY_BLOCKS.get(energy_level, ENERGY_BLOCKS[3])
    cursor = start_at or clock.now()
    cursor += timedelta(minutes=(5 - cursor.minute % 5) % 5)
    cursor = cursor.replace(second=0, microsecond=0)

    blocks: list[TimeBlock] = []
    total = 0
    for i, (title, step, minutes) in enumerate(steps):
        end = cursor + timedelta(minutes=minutes)
        blocks.append(TimeBlock(_fmt(cursor), _fmt(end), title, step))
        total += minutes
        cursor = end

        if i < len(steps) - 1:
            break_end = cursor + timedelta(minutes=break_min)
            blocks.append(
                TimeBlock(_fmt(cursor), _fmt(break_end), "", "Istirahat sebentar", is_break=True)
            )
            total += break_min
            cursor = break_end

    return blocks, total


def _langkah_lokal(task: dict) -> tuple[Optional[list[str]], str]:
    baris = _garis_deskripsi(task.get("description", ""))
    if baris:
        return baris, "manual"

    from models import model_pecah

    hasil = model_pecah.cari(task.get("title", ""), task.get("description", ""))
    if hasil.ketemu:
        return hasil.langkah, "retrieval"
    return None, ""


def _langkah_tambahan(task: dict) -> list[str]:
    raw = task.get("custom_steps", [])
    if isinstance(raw, str):
        raw = raw.splitlines()
    return [str(step).strip(" \t-•*").strip() for step in raw if str(step).strip(" \t-•*").strip()]


def _sisipkan_langkah_user(
    per_judul: dict[str, list[tuple[str, str, int]]],
    tasks: list[dict],
    menit_per_tugas: dict[str, int],
) -> None:
    for task in tasks:
        title = task["title"]
        tambahan = _langkah_tambahan(task)
        if not tambahan or not per_judul.get(title):
            continue
        awal = [step for _, step, _ in per_judul[title]]
        ada = {step.casefold() for step in awal}
        tambahan = [step for step in tambahan if step.casefold() not in ada]
        if not tambahan:
            continue
        gabung = awal[:1] + tambahan + awal[1:]
        bagian = _bagi_menit(menit_per_tugas.get(title, 30), len(gabung))
        per_judul[title] = [
            (title, step, max(3, min(minutes, 120)))
            for step, minutes in zip(gabung, bagian)
        ]


def plan_today(
    tasks: list[dict],
    energy_level: int = 3,
    start_at: Optional[datetime] = None,
    allow_ai: bool = True,
) -> PlanResult:
    if not tasks:
        return PlanResult(blocks=[], source="fallback", total_minutes=0)

    titles = [str(task.get("title", "")) for task in tasks]
    if len(set(titles)) != len(titles):
        parts = [plan_today([task], energy_level, start_at, allow_ai) for task in tasks]
        steps = [step for part in parts for step in part.steps]
        task_steps = {
            task_plan_key(task, f"plan-{index}"): [
                {"text": step, "done": False}
                for _title, step, _minutes in part.steps
            ]
            for index, (task, part) in enumerate(zip(tasks, parts))
        }
        n_lokal = sum(part.n_lokal for part in parts)
        n_ai = sum(part.n_ai for part in parts)
        if n_ai and n_lokal:
            source = "campuran"
        elif n_ai:
            source = "ai"
        elif n_lokal and all(part.source == "lokal" for part in parts):
            source = "lokal"
        elif n_lokal:
            source = "campuran"
        else:
            source = "fallback"
        blocks, total = lay_out(steps, energy_level, start_at)
        return PlanResult(
            blocks=blocks, source=source, total_minutes=total,
            reason="; ".join(part.reason for part in parts if part.reason),
            steps=steps, task_steps=task_steps, n_lokal=n_lokal, n_ai=n_ai,
        )

    from app import storage

    menit_per_tugas = perkiraan_menit(tasks, energy_level)
    per_judul: dict[str, list[tuple[str, str, int]]] = {}
    perlu_ai: list[dict] = []
    n_lokal = 0

    for t in tasks:
        judul = t["title"]
        langkah, sumber = _langkah_lokal(t)
        if not langkah:
            perlu_ai.append(t)
            continue
        bagian = _bagi_menit(menit_per_tugas.get(judul, 30), len(langkah))
        per_judul[judul] = [
            (judul, teks, max(3, min(m, 120))) for teks, m in zip(langkah, bagian)
        ]
        n_lokal += 1
        if sumber == "manual":
            storage.add_decompose_record(judul, t.get("description", ""), langkah, "manual")

    reason = ""
    n_ai = 0
    if perlu_ai:
        if allow_ai:
            ai_steps, reason = _ai_steps(perlu_ai, energy_level)
        else:
            ai_steps, reason = None, "kuota AI hari ini habis"
        if ai_steps:
            for judul, teks, menit in ai_steps:
                per_judul.setdefault(judul, []).append((judul, teks, menit))
            n_ai = len({j for j, _, _ in ai_steps})
            for t in perlu_ai:
                langkah = [teks for j, teks, _ in ai_steps if j == t["title"]]
                if langkah:
                    storage.add_decompose_record(
                        t["title"], t.get("description", ""), langkah, "ai"
                    )
        else:
            for judul, teks, menit in _rule_based_steps(perlu_ai, energy_level):
                per_judul.setdefault(judul, []).append((judul, teks, menit))

    _sisipkan_langkah_user(per_judul, tasks, menit_per_tugas)
    steps = [langkah for t in tasks for langkah in per_judul.get(t["title"], [])]

    if n_ai and n_lokal:
        source = "campuran"
    elif n_ai:
        source = "ai"
    elif n_lokal and not perlu_ai:
        source = "lokal"
    elif n_lokal:
        source = "campuran"
    else:
        source = "fallback"

    blocks, total = lay_out(steps, energy_level, start_at)
    return PlanResult(
        blocks=blocks, source=source, total_minutes=total, reason=reason,
        steps=steps,
        task_steps={
            task_plan_key(task, f"plan-{index}"): [
                {"text": step, "done": False}
                for _title, step, _minutes in per_judul.get(task["title"], [])
            ]
            for index, task in enumerate(tasks)
        },
        n_lokal=n_lokal, n_ai=n_ai,
    )
