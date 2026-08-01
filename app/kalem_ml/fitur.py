"""LAPISAN FITUR -- satu-satunya tempat sinyal user diubah jadi angka.

KENAPA HARUS SATU TEMPAT
------------------------
Sebelum ini tiap model ngumpulin datanya sendiri: `mood_model` ngitung
rata-rata mingguannya sendiri, `energy_predictor` nerima jam tidur dari
pemanggilnya, `kalem_engine` ngitung neglect streak lagi dari nol. Akibatnya
dua halaman bisa ngasih vonis beda di hari yang sama -- dan itu BENERAN
kejadian (halaman Mood vs Morning Brief pernah pakai definisi `streak` yang
beda total).

Sekarang semua model baca dari `bangun_fitur()`. Satu definisi, satu angka,
dan kalau definisinya berubah, semua model ikut berubah bareng.

APA YANG DIPELAJARI KALEM DARI USER
-----------------------------------
Dikelompokin biar kebaca, tapi keluarnya satu dict datar:

    profil    umur, status kerja, jam tidur, jam produktif, pemicu kewalahan
    mood      skor hari ini, tren 3/7/14 hari, energi, streak check-in
    rawat     makan & istirahat (neglect streak), obat kelewat, stok obat
    tugas     jumlah, mendesak, beban menit, rasio selesai, umur tugas
    jeda      frekuensi SOS, jarak dari SOS terakhir, opsi yang dipilih
    fokus     sesi selesai vs disudahi, kalibrasi waktu (est vs nyata)
    favorit   berapa terisi, punya penyemangat/orang/gerak, lagi jam capek
    konteks   hari apa, weekend, jam berapa, inbox numpuk

Semua fitur AMAN kalau datanya kosong -- user baru dapet nilai netral, bukan
error dan bukan nol yang menyesatkan. `siap_belajar()` yang mutusin kapan
sebuah model boleh mulai percaya sama data user.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from app import clock, storage
from app.core.medication_model import check_status, missed_streak

# Umur dipetakan ke satu angka biar bisa dipakai model. Urutannya bermakna
# (makin besar makin tua), jadi nggak perlu one-hot.
UMUR_IDX = {"<18": 0, "18-24": 1, "25-34": 2, "35+": 3}

# Jam tidur estimasi -- satu sumber, dipakai semua model.
TIDUR_JAM = {"cukup": 7.0, "begadang": 5.0, "susah_tidur": 4.5, "berantakan": 4.0}
TIDUR_DEFAULT = 6.5

# Ambang minimal sebelum sebuah model boleh belajar dari data user sendiri.
# Angkanya beda-beda karena sinyalnya beda kepadatan: mood diisi harian,
# SOS jarang, sesi fokus di tengah-tengah.
MIN_DATA = {
    "mood": 5,        # sama kayak MIN_LOGS_FOR_PATTERN yang udah dipakai
    "overwhelm": 10,  # butuh cukup hari BER-label (ada SOS / nggak)
    "durasi": 3,      # 3 sesi di satu kategori udah lumayan
    "penenang": 4,    # 4 kali pakai opsi jeda
}


@dataclass
class Fitur:
    """Satu snapshot user. `nilai` datar biar gampang jadi vektor model."""

    nilai: dict[str, float]
    tanggal: str
    catatan: dict[str, Any]      # hal non-numerik yang tetap berguna buat UI

    def vektor(self, urutan: list[str]) -> list[float]:
        return [float(self.nilai.get(k, 0.0)) for k in urutan]

    def __getitem__(self, key: str) -> float:
        return self.nilai.get(key, 0.0)

    def get(self, key: str, default: float = 0.0) -> float:
        return self.nilai.get(key, default)


# ------------------------------------------------------------ pembantu


def _aman_tanggal(teks: str) -> Optional[date]:
    try:
        return date.fromisoformat(teks)
    except (TypeError, ValueError):
        return None


def _rata(nilai: list[float], default: float = 0.0) -> float:
    return sum(nilai) / len(nilai) if nilai else default


def _log_dalam(logs: list[dict], hari: int, hari_ini: date) -> list[dict]:
    """Catatan dalam N hari terakhir. Tanggal MASA DEPAN dibuang.

    Sisa tombol "Maju 1 hari" bisa ninggalin catatan bertanggal depan; kalau
    ikut kehitung, semua rata-rata jadi bohong.
    """
    out = []
    for log in logs:
        when = _aman_tanggal(log.get("date", ""))
        if when is None:
            continue
        selisih = (hari_ini - when).days
        if 0 <= selisih < hari:
            out.append(log)
    return out


def streak_checkin(logs: list[dict], hari_ini: Optional[date] = None) -> int:
    """Berapa hari berturut-turut user check-in. Momentum, 0-10.

    Boleh mulai dari hari ini ATAU kemarin -- jam 9 pagi user belum sempat
    check-in, dan streak-nya nggak pantes dianggap putus gara-gara itu.
    """
    hari_ini = hari_ini or clock.today()
    ada = {d for d in (_aman_tanggal(l.get("date", "")) for l in logs) if d}
    if not ada:
        return 0
    kursor = hari_ini if hari_ini in ada else hari_ini - timedelta(days=1)
    n = 0
    while kursor in ada and n < 10:
        n += 1
        kursor -= timedelta(days=1)
    return n


def streak_abai(logs: list[dict]) -> int:
    """Berapa check-in terakhir berturut-turut user bilang belum makan /
    kurang istirahat. Hari yang nggak dijawab (None, None) dilewatin --
    nggak mutusin streak, karena jawabnya emang opsional."""
    n = 0
    for log in logs:
        makan, istirahat = log.get("ate_today"), log.get("rested_enough")
        if makan is None and istirahat is None:
            continue
        if makan is False or istirahat is False:
            n += 1
        else:
            break
    return n


# Pita energi buat kalibrasi. Dikelompokin 3, bukan 6 level: dengan 6 level
# tiap kelompok cuma keisi satu-dua sesi, dan itu bukan pola, itu kebetulan.
PITA_ENERGI = {1: "rendah", 2: "rendah", 3: "sedang", 4: "sedang", 5: "tinggi", 6: "tinggi"}

# Minimal sesi dalam satu pita sebelum faktornya dipercaya sendiri.
MIN_SESI_PITA = 3


def _rasio_kalibrasi(records: list[dict], pita: Optional[str] = None) -> list[float]:
    """Rasio (menit nyata / menit perkiraan) dari sesi yang layak dihitung."""
    out = []
    for r in records:
        try:
            est = float(r.get("menit_est") or 0)
            nyata = float(r.get("menit") or 0)
        except (TypeError, ValueError):
            continue
        if est < 3 or nyata < 3:
            continue
        if pita is not None and PITA_ENERGI.get(int(r.get("energi") or 4)) != pita:
            continue
        out.append(nyata / est)
    return out


def _median(nilai: list[float]) -> float:
    urut = sorted(nilai)
    n = len(urut)
    return urut[n // 2] if n % 2 else (urut[n // 2 - 1] + urut[n // 2]) / 2


def kalibrasi_waktu(records: list[dict], energi: Optional[int] = None) -> float:
    """Seberapa meleset perkiraan waktu user, sebagai FAKTOR.

    1.0 = perkiraannya pas. 1.6 = kenyataannya 60% lebih lama dari yang
    diperkirakan. Ini ukuran *time blindness* yang paling langsung yang bisa
    diambil app ini -- dan angkanya dipakai buat ngoreksi perkiraan
    berikutnya, bukan buat dipajang sebagai nilai rapor.

    KENAPA HUBUNGAN ENERGI-KECEPATAN DIPELAJARI DI SINI, BUKAN DARI DATASET
    ----------------------------------------------------------------------
    Dataset durasi isinya tugas orang lain. Nambahin kolom "energi saat itu"
    ke situ artinya ngarang angka -- energi siapa, diukur kapan? Dan lebih
    parah: seberapa jauh energi rendah ngelambatin orang itu BEDA-BEDA per
    orang, jadi koefisien rata-rata populasi malah bisa nyesatin.

    Sesi fokus user SUDAH nyimpen `energi` apa adanya. Itu sumber yang jujur,
    dan itu satu-satunya yang dipakai di sini. Konsekuensinya jelas dan
    diterima: hubungan ini baru kebaca sesudah user punya beberapa sesi di
    pita energi yang sama -- sebelum itu, faktornya global.
    """
    semua = _rasio_kalibrasi(records)
    if not semua:
        return 1.0
    global_f = _median(semua)

    if energi is not None:
        pita = PITA_ENERGI.get(int(energi))
        khusus = _rasio_kalibrasi(records, pita)
        if len(khusus) >= MIN_SESI_PITA:
            # Ditarik separuh jalan ke faktor global. Sesi per-pita selalu
            # lebih sedikit, jadi angkanya lebih berisik -- peredam ini yang
            # bikin perkiraan nggak lompat-lompat tiap ganti level energi.
            khusus_f = _median(khusus)
            global_f = (khusus_f + global_f) / 2

    return max(0.4, min(global_f, 3.0))


def kalibrasi_per_pita(records: list[dict]) -> dict[str, tuple[float, int]]:
    """{pita: (faktor, jumlah sesi)} -- buat ditampilin & dites."""
    hasil: dict[str, tuple[float, int]] = {}
    for pita in ("rendah", "sedang", "tinggi"):
        r = _rasio_kalibrasi(records, pita)
        if r:
            hasil[pita] = (round(max(0.4, min(_median(r), 3.0)), 2), len(r))
    return hasil


# ------------------------------------------------------------ pembangun


def bangun_fitur(now: Optional[datetime] = None) -> Fitur:
    """Susun seluruh sinyal user jadi satu snapshot."""
    now = now or clock.now()
    hari_ini = clock.today()
    iso = hari_ini.isoformat()

    profil = storage.get_profile()
    favorit = storage.get_favorites()
    logs = [l for l in storage.get_mood_logs() if l.get("score") is not None]
    tugas_semua = storage.get_tasks()
    tugas_hari_ini = [t for t in tugas_semua if t.get("deadline") == iso]
    sos = storage.get_reset_events()
    obat = storage.get_medication()
    records = storage.get_focus_records()

    log7 = _log_dalam(logs, 7, hari_ini)
    log3 = _log_dalam(logs, 3, hari_ini)
    log14 = _log_dalam(logs, 14, hari_ini)
    sos7 = _log_dalam(sos, 7, hari_ini)
    sos3 = _log_dalam(sos, 3, hari_ini)

    skor7 = [l["score"] for l in log7]
    skor3 = [l["score"] for l in log3]
    skor14 = [l["score"] for l in log14]

    hari_ini_log = next((l for l in logs if l.get("date") == iso), None)

    # --- jarak dari SOS terakhir ---
    tanggal_sos = sorted(
        (d for d in (_aman_tanggal(e.get("date", "")) for e in sos) if d and d <= hari_ini),
        reverse=True,
    )
    hari_sejak_sos = (hari_ini - tanggal_sos[0]).days if tanggal_sos else 99

    # --- tugas ---
    belum = [t for t in tugas_hari_ini if not storage.task_is_done(t)]
    mendesak = [t for t in belum if t.get("urgent")]
    beban_menit = sum(float(t.get("menit_est") or 0) for t in belum)

    # Rasio selesai 7 hari: dari tugas yang deadline-nya dalam rentang itu.
    tugas7 = [
        t for t in tugas_semua
        if (d := _aman_tanggal(t.get("deadline", ""))) and 0 <= (hari_ini - d).days < 7
    ]
    selesai7 = [t for t in tugas7 if storage.task_is_done(t)]
    rasio_selesai = len(selesai7) / len(tugas7) if tugas7 else 0.5

    # Umur tugas tertua yang belum kelar -- ukuran penundaan yang paling polos.
    umur_tertua = 0
    for t in tugas_semua:
        if storage.task_is_done(t):
            continue
        dibuat = _aman_tanggal((t.get("created_at") or "")[:10])
        if dibuat:
            umur_tertua = max(umur_tertua, (hari_ini - dibuat).days)

    # --- obat ---
    status_obat = check_status(obat)
    obat_kelewat = missed_streak(obat)

    # --- fokus ---
    rec7 = _log_dalam(records, 7, hari_ini)
    kelar = [r for r in rec7 if r.get("selesai")]
    rasio_sesi = len(kelar) / len(rec7) if rec7 else 0.5

    # --- waktu ---
    di_jam_produktif = storage.in_productive_hours(profil, now.hour)
    di_jam_capek = storage.in_tired_window(now)

    nilai: dict[str, float] = {
        # profil
        "umur_idx": float(UMUR_IDX.get(profil.get("age_range", ""), 1)),
        "n_status": float(len(profil.get("status") or [])),
        "tidur_jam": TIDUR_JAM.get(profil.get("sleep_condition", ""), TIDUR_DEFAULT),
        "punya_jam_produktif": 1.0 if profil.get("productive_hours") else 0.0,
        "di_jam_produktif": 1.0 if di_jam_produktif else 0.0,
        "jam_produktif_diketahui": 0.0 if di_jam_produktif is None else 1.0,
        "n_pemicu": float(len(storage.all_triggers(profil))),
        # mood
        "skor_hari_ini": float(hari_ini_log["score"]) if hari_ini_log else 0.0,
        "ada_checkin_hari_ini": 1.0 if hari_ini_log else 0.0,
        "skor_3h": _rata(skor3, 3.0),
        "skor_7h": _rata(skor7, 3.0),
        "skor_14h": _rata(skor14, 3.0),
        "tren_mood": _rata(skor3, 3.0) - _rata(skor14, 3.0),
        "energi_terakhir": float(logs[0].get("energy") or 3) if logs else 3.0,
        "streak_checkin": float(streak_checkin(logs, hari_ini)),
        "n_catatan": float(len(logs)),
        "n_diary": float(sum(1 for l in logs if (l.get("diary") or "").strip())),
        # rawat diri
        "streak_abai": float(streak_abai(logs)),
        "obat_aktif": 1.0 if status_obat.active else 0.0,
        "obat_kelewat": float(obat_kelewat),
        "obat_hari_sisa": float(status_obat.days_left if status_obat.active else 99),
        # tugas
        "n_tugas_hari_ini": float(len(tugas_hari_ini)),
        "n_belum_selesai": float(len(belum)),
        "n_mendesak": float(len(mendesak)),
        "beban_menit": float(beban_menit),
        "rasio_selesai_7h": float(rasio_selesai),
        "umur_tugas_tertua": float(min(umur_tertua, 60)),
        "n_inbox": float(len(storage.get_inbox())),
        # jeda / SOS
        "n_sos_7h": float(len(sos7)),
        "n_sos_3h": float(len(sos3)),
        "hari_sejak_sos": float(min(hari_sejak_sos, 99)),
        # fokus
        "n_sesi_7h": float(len(rec7)),
        "rasio_sesi_kelar": float(rasio_sesi),
        "kalibrasi_waktu": kalibrasi_waktu(records),
        # favorit
        "n_favorit": float(storage.favorites_filled()),
        "punya_penyemangat": 1.0 if (favorit.get("penyemangat") or "").strip() else 0.0,
        "punya_orang": 1.0 if (favorit.get("orang") or "").strip() else 0.0,
        "punya_gerak": 1.0 if (favorit.get("gerak") or "").strip() else 0.0,
        "di_jam_capek": 1.0 if di_jam_capek else 0.0,
        # konteks waktu
        "weekday": float(hari_ini.weekday()),
        "is_weekend": 1.0 if hari_ini.weekday() >= 5 else 0.0,
        "jam": float(now.hour),
    }

    catatan = {
        "profil": profil,
        "favorit": favorit,
        "pemicu": storage.all_triggers(profil),
        "status_obat": status_obat,
        "log_hari_ini": hari_ini_log,
        "tugas_belum": belum,
    }
    return Fitur(nilai=nilai, tanggal=iso, catatan=catatan)


def siap_belajar(nama_model: str, fitur: Optional[Fitur] = None) -> bool:
    """Apa data user udah cukup buat model ini berhenti nebak pakai prior?

    Dipisah dari modelnya sendiri supaya aturan "jangan ngarang kalau data
    belum cukup" kelihatan di satu tempat, bukan kesebar jadi angka ajaib.
    """
    fitur = fitur or bangun_fitur()
    batas = MIN_DATA.get(nama_model, 5)
    if nama_model == "mood":
        return fitur["n_catatan"] >= batas
    if nama_model == "overwhelm":
        return fitur["n_catatan"] >= batas
    if nama_model == "penenang":
        return len(storage.get_reset_events()) >= batas
    if nama_model == "durasi":
        return fitur["n_sesi_7h"] >= 1 or len(storage.get_focus_records()) >= batas
    return fitur["n_catatan"] >= batas


def ringkas_untuk_ui(fitur: Optional[Fitur] = None) -> dict[str, Any]:
    """Angka-angka yang layak ditunjukin ke user apa adanya."""
    f = fitur or bangun_fitur()
    return {
        "catatan": int(f["n_catatan"]),
        "streak_checkin": int(f["streak_checkin"]),
        "rasio_selesai": round(f["rasio_selesai_7h"] * 100),
        "kalibrasi": round(f["kalibrasi_waktu"], 2),
        "sesi_7h": int(f["n_sesi_7h"]),
        "sos_7h": int(f["n_sos_7h"]),
    }
