"""Pecah Tugas -- fitur OPSIONAL di halaman Tracker.

Beda dari versi sebelumnya: ini nggak memecah semua tugas di kalender,
tapi HANYA tugas yang deadline-nya hari ini, lalu menatanya jadi slot
waktu berurutan supaya bisa selesai optimal sesuai level energi user.

Pakai AI (Gemini/OpenAI/DeepSeek, lihat `ai_client.active_provider()`) kalau
tersedia; kalau nggak ada API key / gagal / lagi offline, otomatis jatuh ke
pembagian rule-based. Ketergantungan ke API pihak ketiga ini sengaja
diekspos lewat `PlanResult.source`.

Output JSON-nya dipaksa lewat skema structured output (bentuk pastinya beda
per provider, urusan itu ada di `ai_client.generate_json()`), bukan cuma
minta "jawab pakai JSON" di prompt -- jadi bentuknya dijamin valid, nggak
bergantung model nurut apa nggak. File ini sendiri nggak pernah tau lagi
provider mana yang aktif.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from app import clock
from app.core import ai_client

# Satu sumber kebenaran buat pemetaan energi -> durasi, dipakai bareng
# timer di Tracker lewat kalem_engine.
from app.core.kalem_engine import ENERGY_BLOCKS

# Skema output dalam JSON Schema STANDAR (huruf kecil) -- `ai_client`
# nerjemahin ke konvensi Gemini (huruf besar) atau bentuk OpenAI sendiri,
# jadi file ini nggak perlu tau bedanya. `menit` SENGAJA DIBUANG dari sini,
# lihat catatan di bawah.
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
    "Field 'tugas' harus disalin persis dari judul yang dikasih.\n\n"
    "PENTING soal sumber langkah: beberapa tugas di bawah punya baris "
    "'Deskripsi'. Kalau ADA, langkah-langkahnya HARUS dipecah dari ISI "
    "deskripsi itu -- itu konteks nyata soal APA yang mau dikerjain "
    "(mis. deskripsi 'bikin proposal buat hackathon, cari tim dulu' harus "
    "jadi langkah kayak 'cari 1-2 orang buat diajak bareng', bukan cuma "
    "'buka dokumen proposal'). Judul di situ cuma LABEL, bukan sumber isi. "
    "Kalau tugas TIDAK punya deskripsi, pecah dari judulnya aja seperti biasa."
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
    # "ai"        -> API beneran kepanggil (dan kuota kepotong)
    # "lokal"     -> SEMUA tugas kelayanin tanpa API: dari deskripsi
    #                terstruktur user, atau pungutan hasil pecahan lama
    #                (model_pecah). Kualitasnya setara "ai", biayanya nol.
    # "campuran"  -> DUA kemungkinan: (1) sebagian tugas kelayanin lokal,
    #                sebagian lagi beneran manggil AI; (2) sebagian lokal,
    #                sisanya jatuh ke template generik karena AI nggak
    #                boleh/nggak kepakai (`allow_ai=False` atau kuota abis).
    #                Bedanya diliat dari `n_ai`: >0 berarti kasus (1).
    # "fallback"  -> template rule-based generik, dipakai kalau AI gagal/
    #                nggak ada key. Ini yang kualitasnya paling apa adanya.
    source: str
    total_minutes: int
    reason: str = ""    # kalau fallback: kenapa AI-nya nggak kepakai
    # Langkah mentah (judul, langkah, menit) SEBELUM ditaruh ke slot waktu.
    # Disimpen biar jadwalnya bisa disusun ulang pas ada tugas yang dihapus,
    # tanpa manggil AI-nya lagi.
    steps: list[tuple[str, str, int]] = field(default_factory=list)
    # Langkah yang sama, tetapi dikunci ke ID tugas untuk write-back. Judul
    # bukan identitas: dua tugas sah memiliki judul yang sama.
    task_steps: dict[str, list[dict]] = field(default_factory=dict)
    # Berapa tugas yang kelayanin tanpa API vs yang mesti nelpon AI.
    # Dipajang di Tracker biar penghematannya KELIATAN, bukan cuma kejadian
    # diam-diam di belakang layar.
    n_lokal: int = 0
    n_ai: int = 0


def _fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _garis_deskripsi(description: str) -> list[str]:
    """Deskripsi yang udah ditulis per-baris (user bikin outline sendiri
    sebelum ngisi form) jadi list baris bersih. Return [] kalau deskripsinya
    cuma satu paragraf utuh -- itu nggak bisa dipecah tanpa ngerti isinya,
    butuh AI buat itu (lihat `_ai_steps`)."""
    baris = [b.strip(" \t-•*").strip() for b in (description or "").splitlines()]
    baris = [b for b in baris if b]
    return baris if len(baris) >= 2 else []


def _rule_based_steps(tasks: list[dict], energy_level: int) -> list[tuple[str, str, int]]:
    """(judul tugas, langkah, menit) tanpa bantuan AI.

    Kalau deskripsi tugas UDAH ditulis per-baris (user bikin outline
    sendiri), baris-baris itu dipakai APA ADANYA sebagai langkah -- nggak
    ada gunanya manggil AI buat mecah sesuatu yang penulisnya sendiri udah
    pecah. Efek sampingnya kebetulan pas buat biaya API: Pecah Tugas dari
    deskripsi terstruktur GRATIS dan nggak potong kuota `decompose`, jadi
    user yang emang udah niat bikin outline nggak perlu ngorbanin jatah
    AI-nya buat itu.
    """
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
    # LANGKAH 1: model kita yang ngitung durasi.
    menit_per_tugas = perkiraan_menit(tasks, energy_level)

    def _baris_tugas(t: dict) -> str:
        baris = f"- {t['title']} (~{menit_per_tugas.get(t['title'], 30)} menit)"
        deskripsi = (t.get("description") or "").strip()
        if deskripsi:
            # Deskripsi ITU yang mau dipecah, bukan judulnya -- lihat
            # instruksi di SYSTEM_PROMPT soal ini.
            baris += f"\n  Deskripsi: {deskripsi}"
        return baris

    task_lines = "\n".join(_baris_tugas(t) for t in tasks)

    # LANGKAH 2: AI cuma mecah jadi kalimat langkah -- provider mana yang
    # beneran dipanggil (Gemini/OpenAI/DeepSeek) urusan `ai_client`, bukan di sini.
    parsed, reason = ai_client.generate_json(
        system_instruction=SYSTEM_PROMPT,
        prompt=(
            f"Tugas hari ini:\n{task_lines}\n\n"
            f"Energi user: {energy_level}/6 (1 = capek banget, 6 = penuh energi). "
            "Makin rendah energinya, makin kecil langkahnya.\n"
            "Pecah jadi langkah. Jangan sebut menit."
        ),
        schema=RESPONSE_SCHEMA,
        temperature=0.7,
    )
    if not parsed:
        return None, reason or "balasan AI kosong"

    # LANGKAH 3: teks langkah dari AI, MENIT dari model kita.
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


def _langkah_lokal(task: dict) -> tuple[Optional[list[str]], str]:
    """Langkah buat satu tugas TANPA nelpon API. Return (langkah, sumber).

    Dua jalur, dicoba berurutan:

      1. Deskripsi yang udah ditulis per-baris -- user bikin outline sendiri,
         nggak ada gunanya minta AI mecah yang penulisnya udah pecah.
      2. Pungutan dari pecahan lama yang MIRIP (`model_pecah`) -- ini yang
         bikin app makin murah seiring dipakai.

    Return (None, "") kalau dua-duanya nggak kena -> pemanggil lanjut ke AI.
    """
    baris = _garis_deskripsi(task.get("description", ""))
    if baris:
        return baris, "manual"

    from app.kalem_ml import model_pecah

    hasil = model_pecah.cari(task.get("title", ""), task.get("description", ""))
    if hasil.ketemu:
        return hasil.langkah, "retrieval"
    return None, ""


def _langkah_tambahan(task: dict) -> list[str]:
    """Normalisasi langkah yang memang ingin user lakukan sendiri."""
    raw = task.get("custom_steps", [])
    if isinstance(raw, str):
        raw = raw.splitlines()
    return [str(step).strip(" \t-•*").strip() for step in raw if str(step).strip(" \t-•*").strip()]


def _sisipkan_langkah_user(
    per_judul: dict[str, list[tuple[str, str, int]]],
    tasks: list[dict],
    menit_per_tugas: dict[str, int],
) -> None:
    """Sisipkan langkah user setelah pembuka, lalu bagi ulang durasinya.

    Posisi ini membuat kebutuhan seperti "Ambil pensil" muncul setelah
    "Buka buku" dan sebelum kerja inti, tanpa meminta user menyusun seluruh
    rencana dari nol. Langkah yang sama tidak diduplikasi.
    """
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
    """Susun rencana hari ini jadi slot waktu berurutan.

    URUTAN YANG SENGAJA: yang GRATIS dicoba dulu, API belakangan.
    Tugas yang bisa dilayanin dari deskripsi terstruktur atau pungutan
    pecahan lama nggak pernah nyampe ke API -- dan kuotanya nggak kepotong.
    Cuma sisanya yang beneran dikirim ke AI. `allow_ai=False` dipakai saat
    kuota habis: jalur lokal tetap jalan, sisa tugas mendapat template aman.
    """
    if not tasks:
        return PlanResult(blocks=[], source="fallback", total_minutes=0)

    # Respons model memakai judul sebagai penanda. Kalau ada judul kembar,
    # satu batch akan ambigu dan bisa menempelkan langkah tugas A ke B.
    # Proses masing-masing secara terpisah: sedikit lebih banyak kerja hanya
    # pada kasus ambigu, tetapi identitas tugas tetap benar.
    titles = [str(task.get("title", "")) for task in tasks]
    if len(set(titles)) != len(titles):
        parts = [plan_today([task], energy_level, start_at, allow_ai) for task in tasks]
        steps = [step for part in parts for step in part.steps]
        task_steps = {
            str(task.get("id", f"plan-{index}")): [
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

    # --- Tahap 1: yang bisa dilayanin gratis ---
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
        # Outline manual user ikut disimpen: itu bahan retrieval paling bagus
        # yang ada -- ditulis sendiri sama orang yang ngerti tugasnya.
        if sumber == "manual":
            storage.add_decompose_record(judul, t.get("description", ""), langkah, "manual")

    # --- Tahap 2: sisanya baru ke AI ---
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
            # Simpen biar tugas mirip berikutnya nggak perlu nelpon API lagi.
            for t in perlu_ai:
                langkah = [teks for j, teks, _ in ai_steps if j == t["title"]]
                if langkah:
                    storage.add_decompose_record(
                        t["title"], t.get("description", ""), langkah, "ai"
                    )
        else:
            for judul, teks, menit in _rule_based_steps(perlu_ai, energy_level):
                per_judul.setdefault(judul, []).append((judul, teks, menit))

    # Urutan tugas dipertahanin sesuai `tasks`, bukan urutan selesainya --
    # jadwal yang lompat-lompat bikin bingung.
    _sisipkan_langkah_user(per_judul, tasks, menit_per_tugas)
    steps = [langkah for t in tasks for langkah in per_judul.get(t["title"], [])]

    if n_ai and n_lokal:
        source = "campuran"
    elif n_ai:
        source = "ai"
    elif n_lokal and not perlu_ai:
        source = "lokal"
    elif n_lokal:
        source = "campuran"   # sebagian lokal, sisanya template
    else:
        source = "fallback"

    blocks, total = lay_out(steps, energy_level, start_at)
    return PlanResult(
        blocks=blocks, source=source, total_minutes=total, reason=reason,
        steps=steps,
        task_steps={
            str(task.get("id", f"plan-{index}")): [
                {"text": step, "done": False}
                for _title, step, _minutes in per_judul.get(task["title"], [])
            ]
            for index, task in enumerate(tasks)
        },
        n_lokal=n_lokal, n_ai=n_ai,
    )
