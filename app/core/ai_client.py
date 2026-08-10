"""Helper AI yang dipakai bareng oleh Task Decomposer & kartu rekomendasi
Weekly Insight -- satu tempat, biar key handling, pesan error, DAN pilihan
provider konsisten di kedua fitur (nggak duplikat).

PROVIDER DIPILIH DARI .env, BUKAN DI-HARDCODE
----------------------------------------------
Dulu file ini (dan pemanggilnya) ngunci ke Gemini doang -- import
`google.genai` langsung di `decomposer_logic.py` & `recommendations.py`.
Sekarang dua-duanya cuma manggil `generate_json()` di bawah, dan provider
mana yang beneran jalan ditentuin dari `.env`:

    AI_PROVIDER=gemini   # atau "openai" / "deepseek" -- maksa salah satu
    GEMINI_API=...
    OPENAI_API_KEY=...
    DEEPSEEK_API_KEY=...

Kalau `AI_PROVIDER` nggak diisi, ditebak dari key yang ADA -- urutan menang
Gemini > OpenAI > DeepSeek kalau lebih dari satu keisi (lihat
`active_provider()`). Ganti provider = ganti `.env`, NOL perubahan kode
di pemanggil.

Kenapa ini aman dilakuin belakangan: SDK provider (`google.genai`/`openai`)
cuma pernah diimpor di SINI, nggak pernah di file lain -- jadi nambah
provider baru nggak nyebar ke seluruh app. DeepSeek pinjem SDK `openai`
yang sama (API-nya didesain kompatibel persis, cuma beda `base_url` +
model) -- bukan SDK ketiga yang perlu dipasang lagi.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

_log = logging.getLogger(__name__)

# Pesan yang boleh nyampe ke user: netral, nggak nyebut nama provider, SDK,
# env var, atau model. User nggak bisa (dan nggak perlu) ngoprek `.env` dari
# dalam app -- nyebutin detail teknis di situ cuma bikin bingung tanpa guna.
# Detail aslinya tetep kecatet lewat `_log` (module `logging`) buat developer.
PESAN_BELUM_DIKONFIGURASI = "penyusunan Kalem belum dikonfigurasi"
PESAN_KUOTA_PENUH = "penyusunan Kalem lagi kebanyakan dipakai, coba lagi nanti"
PESAN_JARINGAN = "nggak bisa nyambung buat penyusunan Kalem, coba lagi kalau internetnya udah oke"
PESAN_GAGAL_UMUM = "penyusunan Kalem lagi nggak bisa diproses, coba lagi nanti"

# PILIHAN MODEL GEMINI -- diukur, bukan ditebak (dicek langsung ke API):
#
#   gemini-flash-latest       -> resolve ke gemini-3.6-flash.
#                                Kuota gratis CUMA 20 panggilan/HARI, dan
#                                ngabisin ~1600-2000 token "thinking" tiap
#                                panggilan sebelum sempat nulis JSON-nya.
#   gemini-flash-lite-latest  -> kuota harian jauh lebih longgar, dan
#                                thinking token-nya NOL. Kualitas hasil
#                                Pecah Tugas dites setara buat kerjaan ini
#                                (langkah konkret, langkah pertama < 5 menit,
#                                nurut sama level energi).
#   gemini-2.5-flash / -lite  -> 404 buat API key baru.
GEMINI_MODEL = "gemini-flash-lite-latest"

# Model OpenAI & DeepSeek default -- cepet & murah, dua-duanya support JSON
# mode. Belum diukur langsung ke API kayak Gemini di atas (belum ada key
# buat tes pas ini ditulis) -- ganti kalau ternyata kurang pas.
OPENAI_MODEL = "gpt-4o-mini"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Tanpa thinking token, budget nggak perlu segede model yang mikir dulu.
# Angka ini dipakai bareng sama decomposer & kartu rekomendasi, semua provider.
MAX_OUTPUT_TOKENS = 3072


def _env(name: str) -> Optional[str]:
    """Baca satu env var, dibantu .env kalau python-dotenv ada.

    Nggak pernah nge-hardcode key: kalau nggak ketemu, fitur pemanggilnya
    diem-diem balik ke mode fallback (dan alasannya dilaporin ke UI).
    """
    try:
        from dotenv import load_dotenv

        # override=False: kalau user udah export manual di shell, itu yang menang.
        load_dotenv(override=False)
    except ImportError:
        pass
    return os.environ.get(name) or None


def gemini_api_key() -> Optional[str]:
    # `GEMINI_API` adalah nama yang dipakai konfigurasi FocusBuddy sejak
    # awal. Terima juga `GEMINI_API_KEY` supaya setup lama/tim lain tetap
    # kompatibel; `GEMINI_API` diprioritaskan bila keduanya sengaja diisi.
    return _env("GEMINI_API") or _env("GEMINI_API_KEY")


def openai_api_key() -> Optional[str]:
    return _env("OPENAI_API_KEY")


def deepseek_api_key() -> Optional[str]:
    return _env("DEEPSEEK_API_KEY")


_PROVIDERS = ("gemini", "openai", "deepseek")


def active_provider() -> Optional[str]:
    """"gemini" | "openai" | "deepseek" | None -- provider aktif sekarang.

    `AI_PROVIDER` di .env maksa salah satu secara eksplisit. Kalau nggak
    diisi, ditebak dari key yang ADA -- urutan menang Gemini > OpenAI >
    DeepSeek kalau lebih dari satu keisi (biar nambahin key kedua buat
    nyoba-nyoba nggak diem-diem mindahin provider yang lagi dipakai user).
    """
    dipaksa = (_env("AI_PROVIDER") or "").strip().lower()
    if dipaksa in _PROVIDERS:
        return dipaksa
    if gemini_api_key():
        return "gemini"
    if openai_api_key():
        return "openai"
    if deepseek_api_key():
        return "deepseek"
    return None


def active_model() -> str:
    provider = active_provider()
    if provider == "openai":
        return OPENAI_MODEL
    if provider == "deepseek":
        return DEEPSEEK_MODEL
    return GEMINI_MODEL


# --------------------------------------------------------- lama panggilan
# Dipakai UI buat nampilin progress bar yang BERDASAR, bukan animasi ngasal.
# Disimpen di memori proses aja -- ini bukan data user, dan nggak ada gunanya
# dibawa antar sesi. Dibagi PER PROVIDER: latensi tiap provider beda,
# nyampur semuanya bikin perkiraannya nggak berarti buat satu pun.
_lama: dict[str, list[float]] = {p: [] for p in _PROVIDERS}
LAMA_DEFAULT = 2.5      # tebakan awal sebelum ada pengukuran (detik)
LAMA_MAKS = 30.0


def catat_lama(detik: float, provider: Optional[str] = None) -> None:
    """Catat lama satu panggilan API yang sukses."""
    provider = provider or active_provider() or "gemini"
    if 0 < detik < LAMA_MAKS:
        bucket = _lama.setdefault(provider, [])
        bucket.append(detik)
        del bucket[:-20]     # 20 terakhir aja; yang lama nggak relevan


def perkiraan_lama() -> float:
    """Berapa detik panggilan berikutnya kemungkinan makan waktu.

    Median, bukan rata-rata: satu panggilan yang kebetulan lemot nggak boleh
    bikin semua progress bar berikutnya kepanjangan.
    """
    urut = sorted(_lama.get(active_provider() or "gemini", []))
    if not urut:
        return LAMA_DEFAULT
    n = len(urut)
    return urut[n // 2] if n % 2 else (urut[n // 2 - 1] + urut[n // 2]) / 2


def punya_ukuran() -> bool:
    return bool(_lama.get(active_provider() or "gemini"))


def explain_error(exc: Exception, model: str = "") -> str:
    """Terjemahin exception SDK (Gemini/OpenAI) jadi pesan netral buat user.

    Dua SDK beda kelas exception-nya, tapi pesan errornya sama-sama nyebut
    kata kunci yang sama (401/403/429/404, "quota", "api key", dst) -- jadi
    pencocokan teks generik ini kepakai buat dua-duanya tanpa perlu tau
    provider mana yang lagi aktif.

    Return value SENGAJA nggak nyebut provider/SDK/model/env var -- itu
    detail yang user nggak bisa apa-apain dari dalam app. Detail lengkapnya
    dicatat lewat `_log` buat developer, bukan dibalikin ke pemanggil.
    """
    name = type(exc).__name__
    text = str(exc).lower()
    model = model or active_model()
    _log.warning(
        "panggilan AI gagal (provider=%s model=%s): %s: %s",
        active_provider(), model, name, exc,
    )

    if "api key" in text or "api_key" in text or "unauthenticated" in text or "401" in text:
        return PESAN_BELUM_DIKONFIGURASI
    if "permission" in text or "403" in text:
        return PESAN_BELUM_DIKONFIGURASI
    if "quota" in text or "rate limit" in text or "resource_exhausted" in text or "429" in text:
        return PESAN_KUOTA_PENUH
    if "not found" in text or "404" in text:
        return PESAN_GAGAL_UMUM
    if any(k in text for k in ("connection", "timeout", "network", "dns", "unreachable")):
        return PESAN_JARINGAN
    return PESAN_GAGAL_UMUM


# --------------------------------------------------- pemanggilan terpadu


def _urai_json(text: str, akar_array: bool) -> Optional[Any]:
    """Bersihin fence markdown & ambil JSON dari teks balasan model.

    Dua tahap: coba parse langsung dulu, baru kalau gagal cari kurung
    pembuka/penutup paling luar (`[...]` atau `{...}`) dan parse potongan
    itu -- jaga-jaga model nambahin kalimat basa-basi sebelum/sesudah JSON.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    buka, tutup = ("[", "]") if akar_array else ("{", "}")
    start, end = text.find(buka), text.rfind(tutup)
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _ke_skema_gemini(schema: Any) -> Any:
    """JSON Schema standar (huruf kecil, dipakai pemanggil) -> format
    `response_schema` Gemini (huruf besar: ARRAY/OBJECT/STRING) -- Gemini
    punya konvensi sendiri, beda dari JSON Schema resmi."""
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    if isinstance(out.get("type"), str):
        out["type"] = out["type"].upper()
    if "items" in out:
        out["items"] = _ke_skema_gemini(out["items"])
    if "properties" in out:
        out["properties"] = {k: _ke_skema_gemini(v) for k, v in out["properties"].items()}
    return out


def _panggil_gemini(
    system_instruction: str, prompt: str, schema: dict, temperature: float
) -> tuple[Optional[Any], str]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        _log.warning("SDK google-genai belum terpasang")
        return None, PESAN_BELUM_DIKONFIGURASI

    key = gemini_api_key()
    if not key:
        _log.info("Gemini aktif tapi key kosong")
        return None, PESAN_BELUM_DIKONFIGURASI

    import time

    mulai = time.time()
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                # Structured output: bentuk JSON-nya dijamin API, bukan
                # bergantung model nurut sama instruksi prompt.
                response_mime_type="application/json",
                response_schema=_ke_skema_gemini(schema),
                temperature=temperature,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            ),
        )
    except Exception as exc:
        return None, explain_error(exc, GEMINI_MODEL)
    catat_lama(time.time() - mulai, "gemini")

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        # Paling sering: kena safety filter, atau kepotong di tengah jalan.
        blocked = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
        if blocked:
            return None, "permintaan ditahan filter keamanan Kalem"
        return None, "balasan Kalem kosong"

    parsed = _urai_json(text, akar_array=(schema.get("type") == "array"))
    if parsed is None:
        return None, "balasan Kalem nggak kebaca dengan benar"
    return parsed, ""


def _panggil_estilo_openai(
    system_instruction: str, prompt: str, schema: dict, temperature: float,
    *, key: Optional[str], model: str, base_url: Optional[str],
    provider: str, env_var: str,
) -> tuple[Optional[Any], str]:
    """Pemanggilan lewat SDK `openai` -- dipakai OpenAI DAN DeepSeek.

    DeepSeek API-nya sengaja dibikin kompatibel sama SDK ini (cuma beda
    `base_url` + nama model), jadi satu fungsi ini cukup buat dua provider
    -- nggak perlu SDK terpisah atau kode yang diduplikat.
    """
    try:
        from openai import OpenAI
    except ImportError:
        _log.warning("SDK openai belum terpasang (provider=%s)", provider)
        return None, PESAN_BELUM_DIKONFIGURASI

    if not key:
        _log.info("Provider %s aktif tapi key (%s) kosong", provider, env_var)
        return None, PESAN_BELUM_DIKONFIGURASI

    # Mode json_object cuma jamin JSON VALID, beda dari response_schema
    # Gemini yang jamin BENTUKNYA juga. Jadi bentuk yang diminta dijelasin
    # eksplisit di prompt, dan root-nya harus object (json_object nolak root
    # array) -- kalau skemanya array, minta dibungkus {"item": [...]} dulu
    # terus dibongkar lagi di bawah.
    akar_array = schema.get("type") == "array"
    petunjuk_bentuk = (
        '\n\nBalas HANYA JSON valid, dibungkus begini: {"item": [...]} -- '
        "isi array-nya ngikutin instruksi di atas."
        if akar_array
        else "\n\nBalas HANYA JSON valid sesuai instruksi di atas."
    )

    import time

    mulai = time.time()
    try:
        client = OpenAI(api_key=key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_instruction + petunjuk_bentuk},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        return None, explain_error(exc, model)
    catat_lama(time.time() - mulai, provider)

    text = ""
    if response.choices:
        text = (response.choices[0].message.content or "").strip()
    if not text:
        return None, "balasan Kalem kosong"

    parsed = _urai_json(text, akar_array=False)   # root SELALU object dari mode ini
    if parsed is None:
        return None, "balasan Kalem nggak kebaca dengan benar"
    if akar_array:
        if not isinstance(parsed, dict):
            return None, "balasan Kalem nggak sesuai format yang diharapkan"
        parsed = parsed.get("item", [])
    return parsed, ""


def _panggil_openai(
    system_instruction: str, prompt: str, schema: dict, temperature: float
) -> tuple[Optional[Any], str]:
    return _panggil_estilo_openai(
        system_instruction, prompt, schema, temperature,
        key=openai_api_key(), model=OPENAI_MODEL, base_url=None,
        provider="openai", env_var="OPENAI_API_KEY",
    )


def _panggil_deepseek(
    system_instruction: str, prompt: str, schema: dict, temperature: float
) -> tuple[Optional[Any], str]:
    return _panggil_estilo_openai(
        system_instruction, prompt, schema, temperature,
        key=deepseek_api_key(), model=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL,
        provider="deepseek", env_var="DEEPSEEK_API_KEY",
    )


_PANGGIL: dict[str, Any] = {
    "gemini": _panggil_gemini,
    "openai": _panggil_openai,
    "deepseek": _panggil_deepseek,
}


def generate_json(
    system_instruction: str, prompt: str, schema: dict, temperature: float = 0.7
) -> tuple[Optional[Any], str]:
    """Minta balasan JSON dari provider AI yang lagi aktif (lihat
    `active_provider()`), sesuai `schema` (JSON Schema standar -- huruf
    kecil: "object"/"array"/"string", BUKAN konvensi Gemini).

    Return (hasil, alasan_gagal). `hasil` None kalau gagal; alasannya
    actionable buat ditunjukin ke user (bukan exception mentah) -- pola
    yang sama kayak `explain_error()`.

    SATU-SATUNYA tempat di app ini yang tau SDK Gemini/OpenAI/DeepSeek itu
    apa. `decomposer_logic.py` & `recommendations.py` cuma manggil fungsi
    ini; ganti provider = ganti .env, nol perubahan kode di pemanggil.
    """
    provider = active_provider()
    if provider is None:
        _log.info("Nggak ada provider AI yang kekonfigurasi di .env")
        return None, PESAN_BELUM_DIKONFIGURASI
    return _PANGGIL[provider](system_instruction, prompt, schema, temperature)
