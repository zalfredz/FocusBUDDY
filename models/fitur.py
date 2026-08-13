"""Ekstraksi fitur bersama untuk seluruh model KALEM."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from app import clock, storage
from app.core.energy_predictor import sleep_hours_for
from app.core.medication_model import check_status, missed_streak
from app.core.mood_model import checkin_streak, neglect_streak

UMUR_IDX = {"<18": 0, "18-24": 1, "25-34": 2, "35+": 3}


@dataclass
class Fitur:

    nilai: dict[str, float]
    tanggal: str
    catatan: dict[str, Any]

    def vektor(self, urutan: list[str]) -> list[float]:
        return [float(self.nilai.get(k, 0.0)) for k in urutan]

    def __getitem__(self, key: str) -> float:
        return self.nilai.get(key, 0.0)

    def get(self, key: str, default: float = 0.0) -> float:
        return self.nilai.get(key, default)


def _aman_tanggal(teks: str) -> Optional[date]:
    try:
        return date.fromisoformat(teks)
    except (TypeError, ValueError):
        return None


def _rata(nilai: list[float], default: float = 0.0) -> float:
    return sum(nilai) / len(nilai) if nilai else default


def _log_dalam(logs: list[dict], hari: int, hari_ini: date) -> list[dict]:
    out = []
    for log in logs:
        when = _aman_tanggal(log.get("date", ""))
        if when is None:
            continue
        selisih = (hari_ini - when).days
        if 0 <= selisih < hari:
            out.append(log)
    return out


PITA_ENERGI = {1: "rendah", 2: "rendah", 3: "sedang", 4: "sedang", 5: "tinggi", 6: "tinggi"}

MIN_SESI_PITA = 3


def _rasio_kalibrasi(records: list[dict], pita: Optional[str] = None) -> list[float]:
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
    semua = _rasio_kalibrasi(records)
    if not semua:
        return 1.0
    global_f = _median(semua)

    if energi is not None:
        pita = PITA_ENERGI.get(int(energi))
        khusus = _rasio_kalibrasi(records, pita)
        if len(khusus) >= MIN_SESI_PITA:
            khusus_f = _median(khusus)
            global_f = (khusus_f + global_f) / 2

    return max(0.4, min(global_f, 3.0))


def bangun_fitur(
    now: Optional[datetime] = None,
    day: Any = None,
    profil: Optional[dict] = None,
) -> Fitur:
    now = now or clock.now()
    hari_ini = clock.today()
    iso = hari_ini.isoformat()

    profil = profil if profil is not None else storage.get_profile()

    if day is not None:
        favorit = day.favorites
        semua_log = day.mood_logs
        tugas_semua = day.all_tasks
        tugas_hari_ini = day.tasks_today
        sos = day.reset_events
        obat = day.medication
        records = day.focus_records
        n_inbox = day.inbox_count
    else:
        favorit = storage.get_favorites()
        semua_log = storage.get_mood_logs()
        tugas_semua = storage.get_tasks()
        tugas_hari_ini = [t for t in tugas_semua if t.get("deadline") == iso]
        sos = storage.get_reset_events()
        obat = storage.get_medication()
        records = storage.get_focus_records()
        n_inbox = len(storage.get_inbox())

    logs = [l for l in semua_log if l.get("score") is not None]

    log7 = _log_dalam(logs, 7, hari_ini)
    log3 = _log_dalam(logs, 3, hari_ini)
    log14 = _log_dalam(logs, 14, hari_ini)
    sos7 = _log_dalam(sos, 7, hari_ini)
    sos3 = _log_dalam(sos, 3, hari_ini)

    skor7 = [l["score"] for l in log7]
    skor3 = [l["score"] for l in log3]
    skor14 = [l["score"] for l in log14]

    hari_ini_log = next((l for l in logs if l.get("date") == iso), None)

    tanggal_sos = sorted(
        (d for d in (_aman_tanggal(e.get("date", "")) for e in sos) if d and d <= hari_ini),
        reverse=True,
    )
    hari_sejak_sos = (hari_ini - tanggal_sos[0]).days if tanggal_sos else 99

    jarak_checkin = storage.hari_sejak_checkin(semua_log)
    data_basi = jarak_checkin is not None and jarak_checkin > storage.STALE_AFTER_DAYS

    belum = [
        task
        for task in tugas_hari_ini
        if storage.is_recommendable_task(task) and not storage.task_is_done(task)
    ]
    mendesak = [t for t in belum if storage.is_urgent(t, now)]
    beban_menit = sum(float(t.get("menit_est") or 0) for t in belum)

    tugas7 = [
        task for task in tugas_semua
        if storage.is_recommendable_task(task)
        and (d := _aman_tanggal(task.get("deadline", "")))
        and 0 <= (hari_ini - d).days < 7
    ]
    selesai7 = [t for t in tugas7 if storage.task_is_done(t)]
    rasio_selesai = len(selesai7) / len(tugas7) if tugas7 else 0.5
    ada_data_tugas = bool(tugas7)

    umur_tertua = 0
    for t in tugas_semua:
        if not storage.is_recommendable_task(t) or storage.task_is_done(t):
            continue
        dibuat = _aman_tanggal((t.get("created_at") or "")[:10])
        if dibuat:
            umur_tertua = max(umur_tertua, (hari_ini - dibuat).days)

    status_obat = check_status(obat)
    obat_kelewat = missed_streak(obat)

    rec7 = _log_dalam(records, 7, hari_ini)
    kelar = [r for r in rec7 if r.get("selesai")]
    rasio_sesi = len(kelar) / len(rec7) if rec7 else 0.5

    di_jam_produktif = storage.in_productive_hours(profil, now.hour)
    _jam_capek = storage.FAVORITE_TIRED_HOURS.get(favorit.get("jam_capek", ""))
    di_jam_capek = bool(_jam_capek) and _jam_capek[1][0] <= now.hour < _jam_capek[1][1]

    age_range = (
        storage.age_range_from_birth_date(profil.get("birth_date", ""))
        or profil.get("age_range", "")
    )
    nilai: dict[str, float] = {
        "umur_idx": float(UMUR_IDX.get(age_range, 1)),
        "n_status": float(len(profil.get("status") or [])),
        "tidur_jam": sleep_hours_for(profil.get("sleep_condition", "")),
        "punya_jam_produktif": 1.0 if profil.get("productive_hours") else 0.0,
        "di_jam_produktif": 1.0 if di_jam_produktif else 0.0,
        "jam_produktif_diketahui": 0.0 if di_jam_produktif is None else 1.0,
        "n_pemicu": float(len(storage.all_triggers(profil))),
        "skor_hari_ini": float(hari_ini_log["score"]) if hari_ini_log else 0.0,
        "ada_checkin_hari_ini": 1.0 if hari_ini_log else 0.0,
        "skor_3h": _rata(skor3, 3.0),
        "skor_7h": _rata(skor7, 3.0),
        "skor_14h": _rata(skor14, 3.0),
        "tren_mood": _rata(skor3, 3.0) - _rata(skor14, 3.0),
        "energi_terakhir": 3.0 if (data_basi or not log7) else float(log7[0].get("energy") or 3),
        "hari_sejak_checkin": float(99 if jarak_checkin is None else min(jarak_checkin, 99)),
        "data_mood_basi": 1.0 if data_basi else 0.0,
        "streak_checkin": float(checkin_streak(logs, hari_ini)),
        "n_catatan": float(len(logs)),
        "n_diary": float(sum(1 for l in logs if (l.get("diary") or "").strip())),
        "streak_abai": 0.0 if data_basi else float(neglect_streak(logs)),
        "obat_aktif": 1.0 if status_obat.active else 0.0,
        "obat_kelewat": float(obat_kelewat),
        "obat_hari_sisa": float(status_obat.days_left if status_obat.active else 99),
        "n_tugas_hari_ini": float(len(tugas_hari_ini)),
        "n_belum_selesai": float(len(belum)),
        "n_mendesak": float(len(mendesak)),
        "beban_menit": float(beban_menit),
        "rasio_selesai_7h": float(rasio_selesai),
        "ada_data_tugas_7h": 1.0 if ada_data_tugas else 0.0,
        "umur_tugas_tertua": float(min(umur_tertua, 60)),
        "n_inbox": float(n_inbox),
        "n_sos_7h": float(len(sos7)),
        "n_sos_3h": float(len(sos3)),
        "hari_sejak_sos": float(min(hari_sejak_sos, 99)),
        "n_sesi_7h": float(len(rec7)),
        "rasio_sesi_kelar": float(rasio_sesi),
        "kalibrasi_waktu": kalibrasi_waktu(records),
        "n_favorit": float(sum(1 for v in favorit.values() if v)),
        "punya_penyemangat": 1.0 if (favorit.get("penyemangat") or "").strip() else 0.0,
        "punya_orang": 1.0 if (favorit.get("orang") or "").strip() else 0.0,
        "punya_gerak": 1.0 if (favorit.get("gerak") or "").strip() else 0.0,
        "di_jam_capek": 1.0 if di_jam_capek else 0.0,
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
        "logs": logs,
        "day": day,
    }
    return Fitur(nilai=nilai, tanggal=iso, catatan=catatan)


def ringkas_untuk_ui(fitur: Optional[Fitur] = None) -> dict[str, Any]:
    f = fitur or bangun_fitur()
    return {
        "catatan": int(f["n_catatan"]),
        "streak_checkin": int(f["streak_checkin"]),
        "rasio_selesai": round(f["rasio_selesai_7h"] * 100),
        "kalibrasi": round(f["kalibrasi_waktu"], 2),
        "sesi_7h": int(f["n_sesi_7h"]),
        "sos_7h": int(f["n_sos_7h"]),
    }
