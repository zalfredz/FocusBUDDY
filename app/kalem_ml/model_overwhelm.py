"""MODEL RISIKO KEWALAHAN -- "hari ini kayaknya bakal berat, nih."

APA YANG DIPELAJARI
-------------------
Peluang user bakal butuh halaman jeda HARI INI, dari pola dia sendiri.
Labelnya jujur dan otomatis: hari yang ada `reset_event`-nya = hari dia
beneran kewalahan. Nggak perlu user ngisi apa-apa tambahan.

Ini model yang paling "Kalem" dari semuanya -- yang lain menjawab pertanyaan
user, yang ini NGANTISIPASI sebelum ditanya.

DUA TAHAP, JUJUR SOAL TAHAPNYA
------------------------------
    < 10 catatan   ->  skor aturan (prior). Transparan, bisa dijelasin
                       satu kalimat, dan nggak ngarang pola dari 3 hari.
    >= 10 catatan  ->  Logistic Regression dari riwayat user sendiri,
                       DICAMPUR sama prior biar nggak liar pas datanya
                       masih tipis.

Kenapa Logistic Regression, bukan hutan: datanya sedikit (puluhan baris),
kelasnya nggak seimbang (hari kewalahan jarang), dan bobot per fitur bisa
dibaca langsung -- jadi Kalem bisa NYEBUTIN alasannya, bukan cuma angka.

YANG SENGAJA TIDAK DILAKUKAN
----------------------------
Angka ini nggak pernah dipajang sebagai persentase ke user. "Risiko kamu
73%" itu bikin cemas dan kesannya pasti, padahal nggak. Yang dipakai cuma
tingkatannya (tenang/waspada/berat) buat NGATUR NADA -- nurunin target,
naikin opsi jeda, nggak nyodorin tugas berat.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.kalem_ml import fitur as F
from app.kalem_ml import riwayat

# Minimal hari ber-label sebelum model belajar dari user. Di bawah ini,
# prior aturan yang jalan.
MIN_HARI = 10
# Minimal hari kewalahan DAN hari tenang. Model nggak bisa belajar apa-apa
# dari data yang labelnya seragam -- dan lebih parah, dia bakal pede.
MIN_PER_KELAS = 2

# Ambang tingkat. Dari prior: 0.5 itu titik di mana tanda-tandanya udah
# numpuk (mood rendah + beban tinggi + abai), bukan cuma satu sinyal.
AMBANG_WASPADA, AMBANG_BERAT = 0.35, 0.60


@dataclass
class Risiko:
    skor: float                  # 0..1, internal -- jangan dipajang mentah
    tingkat: str                 # "tenang" | "waspada" | "berat"
    sumber: str                  # "prior" | "belajar"
    alasan: list[str] = field(default_factory=list)
    n_data: int = 0

    @property
    def perlu_diringankan(self) -> bool:
        return self.tingkat in ("waspada", "berat")


def _prior(f: F.Fitur) -> tuple[float, list[str]]:
    """Skor aturan. Tiap komponen punya bobot yang bisa dibaca & dijelasin.

    Bobotnya dari urutan yang sama yang udah dipakai `kalem_engine.decide()`:
    tanda distress > kondisi badan > beban kerja. Bukan hasil pelatihan --
    ini memang PRIOR, dan ditandai gitu di outputnya.
    """
    skor = 0.0
    alasan: list[str] = []

    if f["n_sos_3h"] >= 2:
        skor += 0.30
        alasan.append("beberapa hari terakhir kamu butuh jeda berulang")
    elif f["n_sos_7h"] >= 2:
        skor += 0.15
        alasan.append("minggu ini udah beberapa kali ambil jeda")

    if f["skor_3h"] and f["skor_3h"] <= 2.5:
        skor += 0.25
        alasan.append("mood kamu lagi rendah beberapa hari ini")
    elif f["tren_mood"] <= -0.8:
        skor += 0.12
        alasan.append("mood kamu lagi turun dibanding biasanya")

    if f["streak_abai"] >= 3:
        skor += 0.20
        alasan.append(f"{int(f['streak_abai'])} hari makan/istirahat kelewat")
    elif f["streak_abai"] >= 1:
        skor += 0.08

    if f["tidur_jam"] < 5.5:
        skor += 0.10
        alasan.append("pola tidur kamu lagi berantakan")

    if f["obat_kelewat"] >= 2:
        skor += 0.10
        alasan.append(f"obat belum keabsen {int(f['obat_kelewat'])} hari")

    # Beban kerja: yang bikin berat itu MENDESAK + numpuk, bukan jumlahnya.
    if f["n_mendesak"] >= 3:
        skor += 0.15
        alasan.append(f"{int(f['n_mendesak'])} tugas mendesak hari ini")
    elif f["n_belum_selesai"] >= 5:
        skor += 0.10
        alasan.append(f"{int(f['n_belum_selesai'])} tugas numpuk")

    if f["umur_tugas_tertua"] >= 14:
        skor += 0.08
        alasan.append("ada tugas yang udah lama ngendon")

    if f["di_jam_capek"]:
        skor += 0.05

    return min(skor, 1.0), alasan


_model: Optional[LogisticRegression] = None
_scaler: Optional[StandardScaler] = None
_n_latih: int = 0
_terlatih_dari: str = ""


def reset_model() -> None:
    global _model, _scaler, _n_latih, _terlatih_dari
    _model = _scaler = None
    _n_latih = 0
    _terlatih_dari = ""


def _latih(day: Any = None) -> bool:
    """Latih dari riwayat user. Return False kalau datanya belum cukup."""
    global _model, _scaler, _n_latih, _terlatih_dari

    X, meta = riwayat.baris_harian(day=day)
    if len(X) < MIN_HARI:
        return False
    y = np.array([1 if m["ada_sos"] else 0 for m in meta])
    if y.sum() < MIN_PER_KELAS or (len(y) - y.sum()) < MIN_PER_KELAS:
        return False

    # Kunci cache dari ISI data, bukan (jumlah baris + jumlah SOS) -- lihat
    # `riwayat.sidik_jari()`. Versi lama nganggep dua user beda yang kebetulan
    # punya statistik ringkas yang sama sebagai dataset identik.
    tanda = riwayat.sidik_jari(X, meta)
    if _model is not None and _terlatih_dari == tanda:
        return True

    Xa = np.array(X, dtype=float)
    _scaler = StandardScaler().fit(Xa)
    # class_weight seimbang: hari kewalahan jarang, dan tanpa ini model
    # bakal ambil jalan pintas "tebak tenang terus" yang akurasinya tinggi
    # tapi gunanya nol.
    _model = LogisticRegression(
        max_iter=1000, class_weight="balanced", C=0.5, random_state=42
    ).fit(_scaler.transform(Xa), y)
    _n_latih = len(X)
    _terlatih_dari = tanda
    return True


def _bobot_teratas(baris: list[float], n: int = 2) -> list[str]:
    """Fitur yang paling ndorong skor NAIK buat baris ini.

    Kontribusi = bobot x nilai-terskala. Ini yang bikin Kalem bisa nyebut
    alasan spesifik hasil belajar, bukan cuma kalimat prior yang tetap.
    """
    if _model is None or _scaler is None:
        return []
    z = _scaler.transform([baris])[0]
    kontrib = _model.coef_[0] * z
    urut = np.argsort(kontrib)[::-1]
    nama = {
        "skor": "mood kamu hari ini",
        "energi": "energi kamu",
        "makan": "makan kamu hari ini",
        "istirahat": "istirahat kamu semalam",
        "weekday": "hari ini di minggu kamu",
        "is_weekend": "weekend/hari kerja",
        "sos_7h_sebelum": "seringnya kamu ambil jeda minggu ini",
        "streak_abai": "makan & istirahat yang kelewat",
        "n_tugas": "jumlah tugas hari ini",
        "n_mendesak": "tugas yang mendesak",
    }
    out = []
    for i in urut[:n]:
        if kontrib[i] <= 0.05:
            break
        out.append(nama.get(riwayat.KOLOM[i], riwayat.KOLOM[i]))
    return out


def nilai(f: Optional[F.Fitur] = None) -> Risiko:
    """Perkiraan risiko kewalahan hari ini."""
    f = f or F.bangun_fitur()
    skor_prior, alasan = _prior(f)

    # DayState asal snapshot ini diteruskan ke pelatihan -- biar modelnya
    # belajar dari data yang dioper, bukan storage yang lagi aktif.
    if not _latih(f.catatan.get("day")):
        return Risiko(
            skor=skor_prior,
            tingkat=_tingkat(skor_prior),
            sumber="prior",
            alasan=alasan[:3],
            n_data=int(f["n_catatan"]),
        )

    baris = riwayat.baris_hari_ini(f)
    p = float(_model.predict_proba(_scaler.transform([baris]))[0][1])

    # Dicampur sama prior. Bobot belajar naik pelan seiring data numpuk:
    # 10 hari -> 0.33, 30 hari -> 0.60, 100 hari -> 0.77. Tanpa peredam ini,
    # model dari 10 hari bakal ayun-ayunan tiap ada satu hari aneh.
    w = _n_latih / (_n_latih + 20.0)
    gabung = w * p + (1 - w) * skor_prior

    belajar = _bobot_teratas(baris)
    semua = alasan[:2] + [a for a in belajar if a not in alasan][:1]

    return Risiko(
        skor=gabung,
        tingkat=_tingkat(gabung),
        sumber="belajar",
        alasan=semua[:3],
        n_data=_n_latih,
    )


def _tingkat(skor: float) -> str:
    if skor >= AMBANG_BERAT:
        return "berat"
    if skor >= AMBANG_WASPADA:
        return "waspada"
    return "tenang"


def status() -> dict:
    siap = _latih()
    return {"siap": siap, "n_latih": _n_latih, "min_hari": MIN_HARI}
