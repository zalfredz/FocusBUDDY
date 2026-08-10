"""Kartu rekomendasi personal -- perluasan Weekly Insight (ide #4).

Reuse infrastruktur AI yang sama kayak Task Decomposer (`ai_client` --
provider-nya Gemini/OpenAI/DeepSeek, lihat `ai_client.active_provider()`).
BUKAN integrasi Spotify/resep API beneran (di luar scope 3 hari) -- cukup
teks rekomendasi singkat dari LLM, dipersonalisasi dari data Favorite yang
user isi sendiri di menu Favorit.

Kalau Favorite belum diisi sama sekali, `build_cards()` balikin satu kartu
ajakan isi Favorite dulu -- bukan kartu kosong atau nge-skip diem-diem.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core import ai_client

COOKING_KEYWORDS = ["masak", "cooking", "baking", "kue", "koki", "dapur", "resep"]

# JSON Schema standar (huruf kecil) -- `ai_client` nerjemahin ke konvensi
# Gemini atau bentuk OpenAI sendiri, jadi file ini nggak perlu tau bedanya.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "judul": {"type": "string", "description": "Judul singkat kartu, 3-6 kata"},
        "isi": {"type": "string", "description": "Isi rekomendasi, boleh beberapa baris"},
    },
    "required": ["judul", "isi"],
}


@dataclass
class RecCard:
    kind: str            # "music" | "recipe" | "empty"
    title: str
    body: str
    source: str = "ai"    # "ai" | "fallback" | "empty"
    reason: str = ""


def _generate(prompt: str) -> tuple[Optional[dict], str]:
    """Return (parsed {'judul','isi'} | None, alasan-gagal)."""
    parsed, reason = ai_client.generate_json(
        system_instruction=(
            "Kamu Kalem, buddy hangat buat orang ADHD. Kasih rekomendasi "
            "singkat, bahasa Indonesia santai, nggak ada markdown/emoji "
            "berlebihan."
        ),
        prompt=prompt,
        schema=RESPONSE_SCHEMA,
        temperature=0.9,
    )
    if not parsed:
        return None, reason or "balasan AI kosong"
    if not isinstance(parsed, dict) or not parsed.get("isi"):
        return None, "balasan AI kosong"
    return parsed, ""


def _music_card(musik: str) -> RecCard:
    prompt = (
        f"User bilang musik/genre yang nenangin buat dia: '{musik}'. Kasih 3 "
        "rekomendasi lagu atau musisi yang mirip vibe-nya, cocok buat nemenin "
        "fokus kerja atau nenangin pas kewalahan. Buka dengan 1 kalimat singkat "
        "kenapa itu nyambung, terus daftar 3 rekomendasinya."
    )
    parsed, reason = _generate(prompt)
    if parsed:
        return RecCard("music", parsed["judul"], parsed["isi"], source="ai")
    return RecCard(
        "music",
        "Lagi pengen dengerin apa?",
        f"Kamu bilang suka '{musik}' -- puter itu lagi aja, kadang yang familiar "
        "emang paling ngebantu fokus. Rekomendasi Kalem lagi belum tersedia, "
        "jadi puter yang familiar dulu aja.",
        source="fallback",
        reason=reason,
    )


def _recipe_card(hobi: str, energy_level: int) -> RecCard:
    if energy_level <= 3:
        effort = "instan dan cepet -- di bawah 10 menit, seminimal mungkin alat & cucian"
    else:
        effort = "boleh agak niat dikit -- 20-30 menit, boleh beberapa langkah"
    prompt = (
        f"User punya hobi masak (nyebut '{hobi}'). Energinya hari ini level "
        f"{energy_level}/6. Kasih 1 resep simpel yang {effort}. Sebutin nama "
        "resepnya, bahan-bahan singkat, terus 2-4 langkah cara bikinnya."
    )
    parsed, reason = _generate(prompt)
    if parsed:
        return RecCard("recipe", parsed["judul"], parsed["isi"], source="ai")
    return RecCard(
        "recipe",
        "Laper? Coba masak dikit",
        "Rekomendasi resep Kalem lagi nggak tersedia, tapi karena kamu suka masak, "
        "coba aja bikin yang paling "
        "gampang di kepala kamu sekarang, nggak usah nunggu resep sempurna.",
        source="fallback",
        reason=reason,
    )


def _empty_card() -> RecCard:
    return RecCard(
        "empty",
        "Kalem belum tau selera kamu",
        "Isi Favorit dulu yuk -- musik atau hobi yang kamu suka. Nanti Kalem "
        "bisa kasih rekomendasi yang lebih personal di sini.",
        source="empty",
    )


def build_cards(favorites: dict, energy_level: int = 3) -> list[RecCard]:
    """Susun kartu yang relevan berdasarkan Favorite yang udah diisi user.

    Nggak manggil Gemini kalau Favorite-nya belum diisi -- nggak ada
    gunanya generate rekomendasi dari data kosong.
    """
    musik = (favorites.get("musik") or "").strip()
    hobi = (favorites.get("hobi") or "").strip()

    cards: list[RecCard] = []
    if musik:
        cards.append(_music_card(musik))
    if hobi and any(kw in hobi.lower() for kw in COOKING_KEYWORDS):
        cards.append(_recipe_card(hobi, energy_level))

    if not cards:
        return [_empty_card()]
    return cards
