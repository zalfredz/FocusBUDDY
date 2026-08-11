"""Transkripsi suara Diary melalui provider KALEM yang mendukung audio."""
from __future__ import annotations

import io
import logging
import os
import wave
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
PESAN_GAGAL = "KALEM belum berhasil mengubah suara jadi tulisan. Coba lagi atau ketik manual."
PESAN_JARINGAN = "Koneksi terputus saat memproses suara. Coba lagi ketika internet lebih stabil."
PESAN_KUOTA = "Cerita suara sedang ramai dipakai. Coba lagi sebentar lagi."


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


def _clean_transcript(text: str) -> str:
    cleaned = (text or "").strip()
    prefixes = ("transkrip:", "transkripsi:")
    lowered = cleaned.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return cleaned[len(prefix):].strip()
    return cleaned


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

    text = _clean_transcript(getattr(response, "text", "") or "")
    return (text, "") if text else ("", PESAN_GAGAL)


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

    text = _clean_transcript(getattr(response, "text", "") or "")
    return (text, "") if text else ("", PESAN_GAGAL)


def transcribe_pcm16(pcm: bytes) -> tuple[str, str]:
    if len(pcm) < MIN_PCM_BYTES:
        return "", PESAN_TERLALU_PENDEK

    provider = _speech_provider()
    if provider is None:
        return "", PESAN_BELUM_TERSEDIA

    wav_bytes = pcm16_to_wav(pcm[:MAX_PCM_BYTES])
    if provider == "gemini":
        return _transcribe_gemini(wav_bytes)
    return _transcribe_openai(wav_bytes)
