"""Pecah Tugas -- fitur OPSIONAL di halaman Tracker.

Beda dari versi sebelumnya: ini nggak memecah semua tugas di kalender,
tapi HANYA tugas yang deadline-nya hari ini, lalu menatanya jadi slot
waktu berurutan supaya bisa selesai optimal sesuai level energi user.

Pakai Gemini API kalau tersedia; kalau nggak ada API key / gagal /
lagi offline, otomatis jatuh ke pembagian rule-based. Ketergantungan ke
API pihak ketiga ini sengaja diekspos lewat `PlanResult.source`.

Output JSON-nya dipaksa lewat `response_schema` Gemini (structured output),
bukan cuma minta "jawab pakai JSON" di prompt -- jadi bentuknya dijamin
valid sama API-nya, bukan bergantung model nurut apa nggak.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from app import clock
from app.core import ai_client

# Satu sumber kebenaran buat pemetaan energi -> durasi, dipakai bareng
# timer di Tracker lewat kalem_engine.
from app.core.kalem_engine import ENERGY_BLOCKS

DECOMPOSER_MODEL = ai_client.MODEL

# Skema output. `menit` SENGAJA DIBUANG dari sini -- lihat catatan di bawah.
RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "tugas": {"type": "STRING", "description": "Judul tugas asli, disalin persis"},
            "langkah": {"type": "STRING", "description": "Satu langkah konkret yang kecil"},
        },
        "required": ["tugas", "langkah"],
    },
}

# KENAPA GEMINI NGGAK DIMINTAIN DURASI LAGI
# -----------------------------------------
# Dulu model diminta ngarang `menit` per langkah. Tiga masalahnya:
#
#   1. Tebakannya nggak berdasar apa-apa. Sekarang app punya `model_durasi`
#      yang dilatih dari 549 tugas berbahasa Indonesia + kecepatan asli user
#      -- itu jauh lebih bisa dipertanggungjawabkan daripada tebakan LLM.
#   2. Angkanya nggak konsisten sama sisa app. Perkiraan di kartu tugas dan
#      di rencana bisa beda buat tugas yang sama.
#   3. Boros token, dan token output yang paling mahal.
#
# Sekarang urutannya: MODEL KITA DULU, baru Gemini. Gemini cuma ngerjain
# bagian yang dia emang paling jago -- nulis kalimat langkah yang enak dibaca.
# Total menit dari model kita, tinggal dibagi ke langkah-langkahnya.
SYSTEM_PROMPT = (
    "Kamu asisten yang bantu orang dengan ADHD/executive dysfunction menyusun "
    "rencana kerja HARI INI. Kamu dikasih daftar tugas beserta perkiraan durasi "
    "yang SUDAH dihitung sistem. Tugas kamu CUMA memecah tiap tugas jadi langkah "
    "konkret yang kecil. JANGAN nyebut durasi/menit sama sekali. Aturan: langkah "
    "pertama tiap tugas harus yang paling ringan (bisa dimulai dalam sekali duduk), "
    "bahasa Indonesia santai, jangan pakai jargon, maksimal 3 langkah per tugas. "
    "Field 'tugas' harus disalin persis dari judul yang dikasih."
)

# Bagian menit buat langkah PERTAMA. Kecil disengaja: hambatan ADHD ada di
# titik mulai, jadi pintu masuknya harus keliatan gampang.
PORSI_LANGKAH_PERTAMA = 0.15
MENIT_LANGKAH_PERTAMA_MAKS = 5


@dataclass
class TimeBlock:
    start: str          # "09:00"
    end: str            # "09:15"
    task_title: str
    step: str
    is_break: bool = False


@dataclass
class PlanResult:
    blocks: list[TimeBlock]
    source: str         # "ai" | "fallback"
    total_minutes: int
    reason: str = ""    # kalau fallback: kenapa AI-nya nggak kepakai
    # Langkah mentah (judul, langkah, menit) SEBELUM ditaruh ke slot waktu.
    # Disimpen biar jadwalnya bisa disusun ulang pas ada tugas yang dihapus,
    # tanpa manggil AI-nya lagi.
    steps: list[tuple[str, str, int]] = field(default_factory=list)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _rule_based_steps(tasks: list[dict], energy_level: int) -> list[tuple[str, str, int]]:
    """(judul tugas, langkah, menit) tanpa bantuan LLM."""
    focus_min, _ = ENERGY_BLOCKS.get(energy_level, ENERGY_BLOCKS[3])
    out: list[tuple[str, str, int]] = []
    for task in tasks:
        title = task["title"]
        out.append((title, f"Siapin bahan/alat buat '{title}'", 5))
        out.append((title, f"Kerjain bagian paling awal dari '{title}'", focus_min))
        out.append((title, f"Rapikan & cek hasil '{title}'", max(focus_min // 2, 5)))
    return out


def _extract_json_array(text: str) -> Optional[list]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        return None


def perkiraan_menit(tasks: list[dict], energy_level: int) -> dict[str, int]:
    """Durasi tiap tugas MENURUT MODEL KITA -- dihitung SEBELUM manggil Gemini.

    Ini inti perubahannya: data yang masuk ke API udah diolah dulu, bukan
    mentah. Gemini nerima "Bikin Skripsi Bab 1 (~150 menit)" dan tinggal
    mecah jadi langkah, bukan disuruh nebak angkanya sendiri.
    """
    from app import storage
    from app.kalem_ml import model_durasi

    records = storage.get_focus_records()
    hasil: dict[str, int] = {}
    for t in tasks:
        # Tugas yang udah punya perkiraan tersimpan dipakai apa adanya --
        # itu angka yang udah dilihat user di kartunya, jangan berubah diam-diam.
        if t.get("menit_est"):
            hasil[t["title"]] = int(t["menit_est"])
            continue
        est = model_durasi.perkirakan(
            t["title"],
            tempo_hari=0,
            penting=8 if t.get("important") else 4,
            kategori=t.get("kategori", ""),
            jumlah=t.get("jumlah_unit", 0),
            records=records,
            energi=energy_level,
        )
        hasil[t["title"]] = est.menit
    return hasil


def _bagi_menit(total: int, n_langkah: int) -> list[int]:
    """Bagi total menit ke langkah-langkah, yang pertama paling ringan."""
    if n_langkah <= 0:
        return []
    if n_langkah == 1:
        return [max(3, total)]
    pertama = max(3, min(int(total * PORSI_LANGKAH_PERTAMA), MENIT_LANGKAH_PERTAMA_MAKS))
    sisa = max(total - pertama, (n_langkah - 1) * 3)
    per = sisa // (n_langkah - 1)
    bagian = [pertama] + [max(3, per)] * (n_langkah - 1)
    # Selisih pembulatan ditaruh di langkah terakhir biar totalnya pas.
    bagian[-1] += max(0, total - sum(bagian))
    return bagian


def _ai_steps(
    tasks: list[dict], energy_level: int
) -> tuple[Optional[list[tuple[str, str, int]]], str]:
    """Return (langkah, alasan-gagal). Alasan dipakai UI biar user tau
    kenapa mode AI-nya nggak kepakai -- bukan cuma diem-diem fallback."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None, "SDK google-genai belum terpasang (pip install google-genai)"

    api_key = ai_client.api_key()
    if not api_key:
        return None, "API key belum di-set (isi GEMINI_API_KEY di file .env)"

    # LANGKAH 1: model kita yang ngitung durasi.
    menit_per_tugas = perkiraan_menit(tasks, energy_level)
    task_lines = "\n".join(
        f"- {t['title']} (~{menit_per_tugas.get(t['title'], 30)} menit)" for t in tasks
    )
    import time

    mulai = time.time()
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=DECOMPOSER_MODEL,
            contents=(
                f"Tugas hari ini:\n{task_lines}\n\n"
                f"Energi user: {energy_level}/6 (1 = capek banget, 6 = penuh energi). "
                "Makin rendah energinya, makin kecil langkahnya.\n"
                "Pecah jadi langkah. Jangan sebut menit."
            ),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                # Structured output: bentuk JSON-nya dijamin API, bukan
                # bergantung model nurut sama instruksi prompt.
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                temperature=0.7,
                # Model lite nggak makan token "thinking" (diukur: 0), jadi
                # budget segini udah lega buat 5 tugas x 3 langkah. Budget
                # yang kekecilan bikin balasan kepotong MAX_TOKENS sebelum
                # JSON-nya utuh -> diem-diem jatuh ke rule-based.
                max_output_tokens=ai_client.MAX_OUTPUT_TOKENS,
            ),
        )
    except Exception as exc:
        return None, _explain(exc)
    ai_client.catat_lama(time.time() - mulai)

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        # Paling sering: kena safety filter, atau kepotong di tengah jalan.
        blocked = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
        if blocked:
            return None, "permintaan ditolak filter keamanan model"
        return None, "balasan AI kosong"

    parsed = _extract_json_array(text)
    if not parsed:
        return None, "balasan AI nggak bisa dibaca sebagai JSON"

    # LANGKAH 3: teks langkah dari Gemini, MENIT dari model kita.
    per_tugas: dict[str, list[str]] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        step = str(item.get("langkah", "")).strip()
        if not step:
            continue
        # Jangan percaya judul karangan model -- kunci balik ke tugas asli.
        # Kalau nggak dikunci, langkahnya nyangkut ke judul yang nggak ada
        # tugasnya dan diem-diem ilang pas ditulis balik ke checklist.
        title = _match_title(str(item.get("tugas", "")).strip(), tasks) or (
            tasks[0]["title"] if tasks else "Tugas hari ini"
        )
        per_tugas.setdefault(title, []).append(step)

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
    """Cocokin judul balesan model ke judul tugas asli.

    Model kadang ngerapiin judul ("Bikin Skripsi Bab 1" -> "Skripsi Bab 1").
    Tanpa pencocokan longgar, langkahnya jadi yatim: judulnya nggak ketemu
    tugas mana pun, terus ilang diem-diem pas ditulis ke checklist.
    """
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


_explain = ai_client.explain_error


def lay_out(
    steps: list[tuple[str, str, int]],
    energy_level: int = 3,
    start_at: Optional[datetime] = None,
) -> tuple[list[TimeBlock], int]:
    """Susun langkah jadi slot waktu berurutan + sisipan istirahat.

    Dipisah dari `plan_today()` supaya jadwalnya bisa DISUSUN ULANG tanpa
    manggil AI lagi -- mis. pas satu tugas dihapus, sisa langkahnya harus
    digeser biar jamnya nggak bolong.
    """
    _, break_min = ENERGY_BLOCKS.get(energy_level, ENERGY_BLOCKS[3])
    cursor = start_at or clock.now()
    # Bulatkan ke kelipatan 5 menit terdekat biar jadwalnya enak dibaca.
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


def plan_today(
    tasks: list[dict],
    energy_level: int = 3,
    start_at: Optional[datetime] = None,
) -> PlanResult:
    """Susun rencana hari ini jadi slot waktu berurutan."""
    if not tasks:
        return PlanResult(blocks=[], source="fallback", total_minutes=0)

    steps, reason = _ai_steps(tasks, energy_level)
    source = "ai"
    if not steps:
        steps = _rule_based_steps(tasks, energy_level)
        source = "fallback"

    blocks, total = lay_out(steps, energy_level, start_at)
    return PlanResult(
        blocks=blocks, source=source, total_minutes=total, reason=reason, steps=steps
    )
