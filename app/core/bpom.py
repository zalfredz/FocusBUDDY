"""Pencarian lokal registri obat BPOM untuk informasi, bukan validasi medis."""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app import clock

INDEX_PATH = Path(__file__).resolve().parents[2] / "datasets" / "generated" / "bpom_index.json"

FUZZY_CUTOFF = 0.72

INGREDIENT_CUTOFF = 0.88

RESEP_WAJIB = {"Keras", "Psikotropika", "Narkotika"}


@dataclass
class DrugMatch:
    found: bool
    exact: bool = False
    matched_by: str = "nama"
    name: str = ""
    nie: str = ""
    golongan: str = ""
    bentuk: str = ""
    komposisi: str = ""
    berlaku_sampai: str = ""
    pendaftar: str = ""
    suggestions: list[str] = field(default_factory=list)

    @property
    def butuh_resep(self) -> bool:
        return self.golongan in RESEP_WAJIB

    @property
    def registrasi_kedaluwarsa(self) -> bool:
        if not self.berlaku_sampai:
            return False
        try:
            return date.fromisoformat(self.berlaku_sampai) < clock.today()
        except ValueError:
            return False


def normalise(name: str) -> str:
    text = (name or "").upper().strip()
    text = text.replace("®", "").replace("™", "")
    text = re.sub(r"[^A-Z0-9\s]", " ", text)
    text = re.sub(r"(?<=[A-Z])(?=\d)", " ", text)
    text = re.sub(r"(?<=\d)(?=[A-Z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_strength(name: str) -> str:
    text = normalise(name)
    text = re.sub(r"\b\d+([.,]\d+)?\s?(MG|ML|MCG|G|IU|%)\b", " ", text)
    text = re.sub(r"\b(MG|ML|MCG|IU)\b", " ", text)
    text = re.sub(r"\b\d+([.,]\d+)?\b\s*$", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_ID_RULES = [
    (r"PH", "F"),
    (r"TH", "T"),
    (r"CH", "K"),
    (r"OE", "E"),
    (r"AE", "E"),
    (r"C(?=[AOU])", "K"),
    (r"C(?=[EI])", "S"),
    (r"X", "KS"),
    (r"Y", "I"),
    (r"E\b", ""),
]


def indonesianise(text: str) -> str:
    out = normalise(text)
    for pattern, repl in _ID_RULES:
        out = re.sub(pattern, repl, out)
    return re.sub(r"\s+", " ", out).strip()


_normalise = normalise
_strip_strength = strip_strength


@lru_cache(maxsize=1)
def _index() -> dict:
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def available() -> bool:
    return bool(_index().get("obat"))


def index_info() -> dict:
    idx = _index()
    return {
        "sumber": idx.get("sumber", ""),
        "baris_asli": idx.get("baris_asli", 0),
        "jumlah_obat": len(idx.get("obat", {})),
    }


def _build(key: str, entry: dict, exact: bool, matched_by: str = "nama") -> DrugMatch:
    return DrugMatch(
        found=True,
        exact=exact,
        matched_by=matched_by,
        name=entry.get("n", key),
        nie=entry.get("nie", ""),
        golongan=entry.get("g", ""),
        bentuk=entry.get("b", ""),
        komposisi=entry.get("k", ""),
        berlaku_sampai=entry.get("s", ""),
        pendaftar=entry.get("p", ""),
    )


def lookup(typed: str) -> DrugMatch:
    idx = _index()
    obat = idx.get("obat")
    if not obat:
        return DrugMatch(found=False)

    key = _normalise(typed)
    if not key:
        return DrugMatch(found=False)

    if key in obat:
        return _build(key, obat[key], exact=True)

    bare = _strip_strength(key)
    if bare and bare in obat:
        return _build(bare, obat[bare], exact=True)
    alias = idx.get("tanpa_kekuatan", {}).get(bare)
    if alias and alias in obat:
        return _build(alias, obat[alias], exact=True)

    zat = idx.get("zat_aktif", {})
    target = bare or key
    target_id = indonesianise(target)

    def by_ingredient(merek: list[str]) -> DrugMatch:
        first = merek[0]
        match = _build(first, obat[first], exact=False, matched_by="zat")
        match.suggestions = [obat[m]["n"] for m in merek[:6] if m in obat]
        return match

    merek = zat.get(target_id) or zat.get(target)
    if merek:
        return by_ingredient(merek)

    close = difflib.get_close_matches(target, list(obat.keys()), n=5, cutoff=FUZZY_CUTOFF)
    if close:
        match = _build(close[0], obat[close[0]], exact=False, matched_by="mirip")
        match.suggestions = [obat[c]["n"] for c in close]
        return match

    dekat = difflib.get_close_matches(target_id, list(zat.keys()), n=1, cutoff=INGREDIENT_CUTOFF)
    if dekat:
        return by_ingredient(zat[dekat[0]])

    return DrugMatch(found=False)


def summary(match: DrugMatch) -> str:
    if not match.found:
        return ""
    bits = [match.golongan] if match.golongan else []
    if match.bentuk:
        bits.append(match.bentuk.split(";")[0].strip().title())
    if match.komposisi:
        bits.append(match.komposisi.title())
    head = " · ".join(b for b in bits if b)
    return f"{head} · NIE {match.nie}" if head else f"NIE {match.nie}"


def suggestion_for(typed: str, match: DrugMatch) -> Optional[str]:
    if not match.found or match.exact or match.matched_by != "mirip":
        return None
    if not match.name:
        return None
    if _normalise(match.name) == _strip_strength(typed):
        return None
    return match.name


def ingredient_note(match: DrugMatch) -> str:
    if not match.found or match.matched_by != "zat":
        return ""
    n = len(match.suggestions)
    contoh = ", ".join(match.suggestions[:3])
    if n > 3:
        return f"Itu nama zat aktifnya. Di Indonesia ada beberapa mereknya — mis. {contoh}."
    return f"Itu nama zat aktifnya. Merek yang ngandung: {contoh}."
