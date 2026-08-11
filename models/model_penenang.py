"""Pemeringkatan opsi penenang berdasarkan dampak pada histori mood."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from app import clock, storage
from app.core.reset_preferences import OPTIONS, TRIGGER_DEFAULTS

MIN_PAKAI = 4
JENDELA_SESUDAH = 3
SELISIH_BERARTI = 0.4


@dataclass
class Peringkat:
    urutan: list[str]
    sumber: str
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
    skor_per_hari: dict[date, float] = {}
    for log in logs:
        d = _tanggal(log.get("date", ""))
        if d is not None and log.get("score") is not None:
            skor_per_hari[d] = float(log["score"])
    hari_urut = sorted(skor_per_hari)
    kumpul: dict[str, list[float]] = {}
    jumlah: dict[str, int] = {}

    for ev in events:
        pilihan = ev.get("choice")
        d = _tanggal(ev.get("date", ""))
        if pilihan not in OPTIONS or d is None:
            continue
        if ev.get("completed") is False:
            continue
        jumlah[pilihan] = jumlah.get(pilihan, 0) + 1

        if isinstance(ev.get("improved"), bool):
            kumpul.setdefault(pilihan, []).append(1.0 if ev["improved"] else -1.0)
            continue

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
    events = storage.get_reset_events() if events is None else events
    logs = storage.get_mood_logs() if logs is None else logs
    pemicu = storage.all_triggers() if pemicu is None else pemicu

    manfaat, jumlah = ukur_manfaat(events, logs)
    total = sum(jumlah.values())

    benih = [TRIGGER_DEFAULTS[t] for t in pemicu if t in TRIGGER_DEFAULTS]

    def kunci_benih(k: str) -> int:
        return benih.index(k) if k in benih else 99

    if total == 0:
        urut = sorted(OPTIONS, key=lambda k: (kunci_benih(k), k))
        catatan = ""
        if benih:
            catatan = (
                f"Urutan ini dari jawaban kamu waktu kenalan — "
                f"'{OPTIONS[urut[0]]['label']}' biasanya paling pas buat itu."
            )
        return Peringkat(urutan=urut, sumber="pemicu", catatan=catatan)

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
                f"'{OPTIONS[atas]['label']}' yang paling sering terasa membantu."
            )
        else:
            catatan = (
                "Belum ada opsi yang jelas lebih ngebantu buat kamu — "
                "urutannya masih ngikutin yang paling sering kamu pakai."
            )
        return Peringkat(urutan=urut, sumber="manfaat", catatan=catatan,
                         manfaat=terukur, jumlah=jumlah)

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
