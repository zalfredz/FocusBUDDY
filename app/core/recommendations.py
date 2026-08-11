"""Kartu rekomendasi personal dengan fallback lokal."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core import ai_client

COOKING_KEYWORDS = ["masak", "cooking", "baking", "kue", "koki", "dapur", "resep"]

WORK_STYLE_LABELS = {
    "sendiri": "kerja sendiri",
    "ditemani": "kerja ditemani",
    "tenang": "tempat tenang",
    "background": "ada suara latar",
}

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
    kind: str
    title: str
    body: str
    source: str = "ai"
    reason: str = ""


def _generate(prompt: str) -> tuple[Optional[dict], str]:
    parsed, reason = ai_client.generate_json(
        system_instruction=(
            "Kamu KALEM, buddy hangat buat orang ADHD. Kasih rekomendasi "
            "singkat, bahasa Indonesia santai, nggak ada markdown/emoji "
            "berlebihan."
        ),
        prompt=prompt,
        schema=RESPONSE_SCHEMA,
        temperature=0.9,
    )
    if not parsed:
        return None, reason or "balasan AI kosong"
    if (
        not isinstance(parsed, dict)
        or not isinstance(parsed.get("judul"), str)
        or not isinstance(parsed.get("isi"), str)
        or not parsed["isi"].strip()
    ):
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
        "emang paling ngebantu fokus. Rekomendasi KALEM lagi belum tersedia, "
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
        "Rekomendasi resep KALEM lagi nggak tersedia, tapi karena kamu suka masak, "
        "coba aja bikin yang paling "
        "gampang di kepala kamu sekarang, nggak usah nunggu resep sempurna.",
        source="fallback",
        reason=reason,
    )


def _empty_card() -> RecCard:
    return RecCard(
        "empty",
        "KALEM belum tahu selera kamu",
        "Isi Favorit dulu yuk -- musik atau hal yang biasanya membantu. Nanti KALEM "
        "bisa kasih rekomendasi yang lebih personal di sini.",
        source="empty",
    )


def _personal_support_card(favorites: dict, energy_level: int) -> Optional[RecCard]:
    if energy_level <= 3:
        safe = (favorites.get("rasa_aman") or favorites.get("tempat") or "").strip()
        reset = (favorites.get("kembali_fokus") or favorites.get("gerak") or "").strip()
        encouragement = (favorites.get("penyemangat") or "").strip()
        other = (favorites.get("overwhelm_lainnya") or "").strip()
        suggestions = [value for value in (safe, reset, encouragement, other) if value]
        if not suggestions:
            return None
        return RecCard(
            "support",
            "Pakai yang sudah membantu",
            "Energi kamu lagi nggak tinggi. Coba pilih satu aja: "
            + " · ".join(suggestions[:2]),
            source="local",
        )

    room = (favorites.get("kondisi_ruangan") or "").strip()
    sound = (favorites.get("suara_alam") or "").strip()
    place = (favorites.get("tempat_fokus") or "").strip()
    selected_styles = [
        WORK_STYLE_LABELS[value]
        for value in (favorites.get("preferensi_kerja") or "").split(",")
        if value in WORK_STYLE_LABELS
    ]
    work_style = ", ".join(selected_styles)
    custom_style = (favorites.get("preferensi_lainnya") or "").strip()
    other = (favorites.get("fokus_lainnya") or "").strip()
    suggestions = [
        value for value in (room, sound, place, work_style, custom_style, other) if value
    ]
    if not suggestions:
        return None
    return RecCard(
        "support",
        "Siapkan suasana fokusmu",
        "Sebelum mulai, coba pakai kondisi yang kamu bilang membantu: "
        + " · ".join(suggestions[:2]),
        source="local",
    )


def build_cards(favorites: dict, energy_level: int = 3) -> list[RecCard]:
    musik = (favorites.get("musik") or "").strip()
    hobi = (favorites.get("hobi") or "").strip()

    cards: list[RecCard] = []
    if musik:
        cards.append(_music_card(musik))
    if hobi and any(kw in hobi.lower() for kw in COOKING_KEYWORDS):
        cards.append(_recipe_card(hobi, energy_level))
    support = _personal_support_card(favorites, energy_level)
    if support:
        cards.append(support)

    if not cards:
        return [_empty_card()]
    return cards
