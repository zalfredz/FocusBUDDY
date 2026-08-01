"""MODEL PENENANG -- "opsi jeda mana yang beneran nolong KAMU?"

MASALAH YANG DIJAWAB
--------------------
Halaman jeda punya 4 opsi (napas, grounding, musik, gerak). Versi sebelumnya
ngurutin murni dari SEBERAPA SERING dipakai. Itu ada cacat yang halus tapi
serius: opsi yang dipakai berulang belum tentu yang nolong -- bisa jadi
justru yang nggak mempan, makanya diulang terus.

Yang diukur di sini: setelah user milih opsi X, MOOD-NYA JADI GIMANA?

CARA NGUKURNYA
--------------
Buat tiap kali user mencet opsi di hari D, dibandingin:

    skor mood terdekat SESUDAH D   -   skor mood pada/sebelum D

Selisih positif = hari-hari sesudah pakai opsi itu cenderung lebih enak.
Ini bukan bukti sebab-akibat, dan sengaja nggak diklaim gitu -- cuma sinyal
yang jauh lebih relevan daripada sekadar hitungan pemakaian.

TIGA TAHAP
----------
    belum ada riwayat  ->  urutan dari pemicu kewalahan (onboarding)
    < 4 pemakaian      ->  frekuensi, seperti sebelumnya
    >= 4 pemakaian     ->  peringkat manfaat terukur, dicampur frekuensi

KENAPA NGGAK PAKAI MODEL BESAR
------------------------------
Datanya cuma puluhan baris dengan 4 pilihan. Rata-rata berbobot udah cukup,
bisa dijelasin ke user dalam satu kalimat ("napas yang paling sering bikin
kamu lebih enak"), dan nggak bisa gagal diam-diam kayak model yang lebih
rumit di data sekecil ini.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from app import clock, storage
from app.core.reset_preferences import OPTIONS, TRIGGER_DEFAULTS

# Minimal pemakaian satu opsi sebelum manfaatnya dianggap terukur.
MIN_PAKAI = 4
# Berapa hari ke depan yang dilihat buat nilai "sesudahnya jadi gimana".
JENDELA_SESUDAH = 3
# Selisih mood yang dianggap berarti. Di bawah ini dianggap datar aja --
# jangan bikin cerita dari noise.
SELISIH_BERARTI = 0.4


@dataclass
class Peringkat:
    urutan: list[str]
    sumber: str                              # "pemicu" | "frekuensi" | "manfaat"
    catatan: str = ""
    manfaat: dict[str, float] = field(default_factory=dict)
    jumlah: dict[str, int] = field(default_factory=dict)


def _tanggal(teks: str) -> Optional[date]:
    try:
        return date.fromisoformat(teks)
    except (TypeError, ValueError):
        return None


def ukur_manfaat(
    events: list[dict], logs: list[dict]
) -> tuple[dict[str, float], dict[str, int]]:
    """Rata-rata perubahan mood sesudah tiap opsi dipakai."""
    skor_per_hari: dict[date, float] = {}
    for log in logs:
        d = _tanggal(log.get("date", ""))
        if d is not None and log.get("score") is not None:
            skor_per_hari[d] = float(log["score"])
    if not skor_per_hari:
        return {}, {}

    hari_urut = sorted(skor_per_hari)
    kumpul: dict[str, list[float]] = {}
    jumlah: dict[str, int] = {}

    for ev in events:
        pilihan = ev.get("choice")
        d = _tanggal(ev.get("date", ""))
        if pilihan not in OPTIONS or d is None:
            continue
        jumlah[pilihan] = jumlah.get(pilihan, 0) + 1

        sebelum = [h for h in hari_urut if h <= d]
        sesudah = [h for h in hari_urut if d < h <= d + timedelta(days=JENDELA_SESUDAH)]
        if not sebelum or not sesudah:
            continue
        awal = skor_per_hari[sebelum[-1]]
        akhir = sum(skor_per_hari[h] for h in sesudah) / len(sesudah)
        kumpul.setdefault(pilihan, []).append(akhir - awal)

    manfaat = {k: sum(v) / len(v) for k, v in kumpul.items() if v}
    return manfaat, jumlah


def peringkat(
    events: Optional[list[dict]] = None,
    logs: Optional[list[dict]] = None,
    pemicu: Optional[list[str]] = None,
) -> Peringkat:
    """Urutan opsi jeda buat user ini, dari yang paling mungkin nolong."""
    events = storage.get_reset_events() if events is None else events
    logs = storage.get_mood_logs() if logs is None else logs
    pemicu = storage.all_triggers() if pemicu is None else pemicu

    manfaat, jumlah = ukur_manfaat(events, logs)
    total = sum(jumlah.values())

    # Benih dari pemicu kewalahan yang disebut waktu onboarding.
    benih = [TRIGGER_DEFAULTS[t] for t in pemicu if t in TRIGGER_DEFAULTS]

    def kunci_benih(k: str) -> int:
        return benih.index(k) if k in benih else 99

    # --- tahap 1: belum ada riwayat sama sekali ---
    if total == 0:
        urut = sorted(OPTIONS, key=lambda k: (kunci_benih(k), k))
        catatan = ""
        if benih:
            catatan = (
                f"Urutan ini dari jawaban kamu waktu kenalan — "
                f"'{OPTIONS[urut[0]]['label']}' biasanya paling pas buat itu."
            )
        return Peringkat(urutan=urut, sumber="pemicu", catatan=catatan)

    # --- tahap 3: manfaat terukur ---
    terukur = {k: v for k, v in manfaat.items() if jumlah.get(k, 0) >= MIN_PAKAI}
    if terukur:
        def kunci_manfaat(k: str):
            return (-terukur.get(k, -9.0), -jumlah.get(k, 0), kunci_benih(k), k)

        urut = sorted(OPTIONS, key=kunci_manfaat)
        atas = urut[0]
        naik = terukur.get(atas, 0.0)
        if naik >= SELISIH_BERARTI:
            catatan = (
                f"Dari {jumlah.get(atas, 0)}x kamu pakai, "
                f"'{OPTIONS[atas]['label']}' yang paling sering bikin "
                "hari-hari sesudahnya lebih enak."
            )
        else:
            catatan = (
                "Belum ada opsi yang jelas lebih ngebantu buat kamu — "
                "urutannya masih ngikutin yang paling sering kamu pakai."
            )
        return Peringkat(urutan=urut, sumber="manfaat", catatan=catatan,
                         manfaat=terukur, jumlah=jumlah)

    # --- tahap 2: frekuensi ---
    def kunci_freq(k: str):
        return (-jumlah.get(k, 0), kunci_benih(k), k)

    urut = sorted(OPTIONS, key=kunci_freq)
    atas = urut[0]
    catatan = ""
    if jumlah.get(atas, 0) >= 2:
        catatan = (
            f"Biasanya '{OPTIONS[atas]['label']}' yang kamu pilih — "
            "Kalem taruh paling atas."
        )
    return Peringkat(urutan=urut, sumber="frekuensi", catatan=catatan, jumlah=jumlah)


def status() -> dict:
    events = storage.get_reset_events()
    manfaat, jumlah = ukur_manfaat(events, storage.get_mood_logs())
    return {
        "n_pakai": sum(jumlah.values()),
        "terukur": {k: round(v, 2) for k, v in manfaat.items() if jumlah.get(k, 0) >= MIN_PAKAI},
        "min_pakai": MIN_PAKAI,
    }
