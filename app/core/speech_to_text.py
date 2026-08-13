"""Transkripsi suara Diary melalui provider KALEM yang mendukung audio."""
from __future__ import annotations

import io
import logging
import math
import os
import re
import sys
import wave
from array import array
from typing import Optional

from app.core import ai_client

_log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
MAX_RECORD_SECONDS = 120
MAX_PCM_BYTES = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH * MAX_RECORD_SECONDS
MIN_PCM_BYTES = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH // 2

OPENAI_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"

PESAN_BELUM_TERSEDIA = "Cerita suara KALEM belum dikonfigurasi. Kamu tetap bisa mengetik."
PESAN_TERLALU_PENDEK = "Suaranya belum cukup terdengar. Coba cerita sedikit lebih lama."
PESAN_TIDAK_TERDENGAR = (
    "KALEM belum mendengar ucapan yang cukup jelas. Coba dekatkan mikrofon dan ulangi."
)
PESAN_GAGAL = "KALEM belum berhasil mengubah suara jadi tulisan. Coba lagi atau ketik manual."
PESAN_JARINGAN = "Koneksi terputus saat memproses suara. Coba lagi ketika internet lebih stabil."
PESAN_KUOTA = "Cerita suara sedang ramai dipakai. Coba lagi sebentar lagi."

# Ambang ini hanya menolak buffer yang praktis sunyi. Mikrofon ponsel tertentu
# menghasilkan PCM dengan amplitudo sangat kecil, jadi rekaman baru ditolak bila
# RMS dan peak sama-sama rendah. Salah satu tanda suara yang nyata sudah cukup
# untuk meneruskan audio ke provider.
MIN_SIGNAL_RMS = 8.0
MIN_SIGNAL_PEAK = 80

_NON_SPEECH_MARKERS = {
    "noise",
    "silence",
    "inaudible",
    "unintelligible",
    "no audio",
    "no speech",
    "audio kosong",
    "tidak ada suara",
    "tidak terdengar",
    "suara tidak terdengar",
}


def _env(name: str) -> str:
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:
        pass
    return os.environ.get(name, "")


def _speech_provider() -> Optional[str]:
    forced = _env("KALEM_SPEECH_PROVIDER").strip().lower()
    if forced in ("gemini", "openai"):
        return forced

    active = ai_client.active_provider()
    if active in ("gemini", "openai"):
        return active
    if ai_client.gemini_api_key():
        return "gemini"
    if ai_client.openai_api_key():
        return "openai"
    return None


def pcm16_to_wav(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(CHANNELS)
        audio.setsampwidth(SAMPLE_WIDTH)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(pcm)
    return output.getvalue()


def pcm16_signal_metrics(pcm: bytes) -> tuple[float, int]:
    """Kembalikan RMS tanpa DC offset dan peak dari PCM16 little-endian."""
    usable = pcm[: len(pcm) - (len(pcm) % SAMPLE_WIDTH)]
    if not usable:
        return 0.0, 0

    samples = array("h")
    samples.frombytes(usable)
    if sys.byteorder != "little":
        samples.byteswap()

    total = 0
    squared_total = 0
    peak = 0
    for sample in samples:
        total += sample
        squared_total += sample * sample
        peak = max(peak, abs(sample))

    count = len(samples)
    mean = total / count
    variance = max(0.0, (squared_total / count) - (mean * mean))
    return math.sqrt(variance), peak


def _is_non_speech_transcript(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return True

    # Provider biasanya menandai rekaman kosong sebagai <noise>, [silence],
    # atau variasi marker sejenis. Kurung dan tanda baca tidak boleh membuatnya
    # lolos sebagai catatan pengguna.
    without_wrappers = re.sub(r"[<>{}\[\]()]", " ", normalized)
    without_punctuation = re.sub(r"[^\w\s]", " ", without_wrappers)
    compact = " ".join(without_punctuation.split())
    if not compact:
        return True
    if compact in _NON_SPEECH_MARKERS:
        return True

    tokens = compact.split()
    return bool(tokens) and all(
        token in {"noise", "silence", "inaudible"} for token in tokens
    )


def _clean_transcript(text: str) -> str:
    cleaned = (text or "").strip()
    prefixes = ("transkrip:", "transkripsi:")
    lowered = cleaned.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    return "" if _is_non_speech_transcript(cleaned) else cleaned


def _explain_error(exc: Exception, provider: str) -> str:
    text = str(exc).lower()
    _log.warning(
        "transkripsi suara gagal (provider=%s): %s: %s",
        provider,
        type(exc).__name__,
        exc,
    )
    if any(key in text for key in ("api key", "api_key", "401", "403", "unauthenticated")):
        return PESAN_BELUM_TERSEDIA
    if any(key in text for key in ("quota", "rate limit", "resource_exhausted", "429")):
        return PESAN_KUOTA
    if any(key in text for key in ("connection", "timeout", "network", "dns", "unreachable")):
        return PESAN_JARINGAN
    return PESAN_GAGAL


def _transcribe_gemini(wav_bytes: bytes) -> tuple[str, str]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "", PESAN_BELUM_TERSEDIA

    key = ai_client.gemini_api_key()
    if not key:
        return "", PESAN_BELUM_TERSEDIA

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=ai_client.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                (
                    "Transkripsikan ucapan ini apa adanya dalam bahasa yang digunakan "
                    "pembicara. Pertahankan gaya bahasa santai dan kata-kata pembicara. "
                    "Jangan meringkas, menanggapi, menambahkan judul, atau menambahkan "
                    "penjelasan. Keluarkan hanya teks transkripsinya."
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=2048,
            ),
        )
    except Exception as exc:
        return "", _explain_error(exc, "gemini")

    raw_text = getattr(response, "text", "") or ""
    text = _clean_transcript(raw_text)
    if text:
        return text, ""
    if _is_non_speech_transcript(raw_text):
        return "", PESAN_TIDAK_TERDENGAR
    return "", PESAN_GAGAL


def _transcribe_openai(wav_bytes: bytes) -> tuple[str, str]:
    try:
        from openai import OpenAI
    except ImportError:
        return "", PESAN_BELUM_TERSEDIA

    key = ai_client.openai_api_key()
    if not key:
        return "", PESAN_BELUM_TERSEDIA

    try:
        response = OpenAI(api_key=key).audio.transcriptions.create(
            model=OPENAI_TRANSCRIPTION_MODEL,
            file=("cerita-kalem.wav", wav_bytes, "audio/wav"),
            language="id",
            prompt=(
                "Transkripsikan apa adanya. Pertahankan bahasa Indonesia santai, "
                "nama, istilah, dan campuran bahasa yang diucapkan."
            ),
        )
    except Exception as exc:
        return "", _explain_error(exc, "openai")

    raw_text = getattr(response, "text", "") or ""
    text = _clean_transcript(raw_text)
    if text:
        return text, ""
    if _is_non_speech_transcript(raw_text):
        return "", PESAN_TIDAK_TERDENGAR
    return "", PESAN_GAGAL


def transcribe_pcm16(pcm: bytes) -> tuple[str, str]:
    if len(pcm) < MIN_PCM_BYTES:
        return "", PESAN_TERLALU_PENDEK

    rms, peak = pcm16_signal_metrics(pcm)
    if rms < MIN_SIGNAL_RMS and peak < MIN_SIGNAL_PEAK:
        _log.info(
            "rekaman suara ditolak karena sinyal terlalu rendah (bytes=%s, rms=%.1f, peak=%s)",
            len(pcm),
            rms,
            peak,
        )
        return "", PESAN_TIDAK_TERDENGAR

    provider = _speech_provider()
    if provider is None:
        return "", PESAN_BELUM_TERSEDIA

    wav_bytes = pcm16_to_wav(pcm[:MAX_PCM_BYTES])
    if provider == "gemini":
        transcript, error = _transcribe_gemini(wav_bytes)
    else:
        transcript, error = _transcribe_openai(wav_bytes)

    if not transcript and not error:
        return "", PESAN_TIDAK_TERDENGAR
    return transcript, error
