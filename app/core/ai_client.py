"""Gateway tunggal provider penyusun KALEM tanpa membocorkan detail provider ke UI."""
from __future__ import annotations

import ast
import json
import logging
import os
from typing import Any, Optional

_log = logging.getLogger(__name__)

PESAN_BELUM_DIKONFIGURASI = "penyusunan KALEM belum dikonfigurasi"
PESAN_KUOTA_PENUH = "penyusunan KALEM lagi kebanyakan dipakai, coba lagi nanti"
PESAN_JARINGAN = "nggak bisa nyambung buat penyusunan KALEM, coba lagi kalau internetnya udah oke"
PESAN_GAGAL_UMUM = "penyusunan KALEM lagi nggak bisa diproses, coba lagi nanti"

GEMINI_MODEL = "gemini-flash-lite-latest"

OPENAI_MODEL = "gpt-4o-mini"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

MAX_OUTPUT_TOKENS = 3072


def _env(name: str) -> Optional[str]:
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:
        pass
    return os.environ.get(name) or None


def gemini_api_key() -> Optional[str]:
    return _env("GEMINI_API") or _env("GEMINI_API_KEY")


def openai_api_key() -> Optional[str]:
    return _env("OPENAI_API_KEY")


def deepseek_api_key() -> Optional[str]:
    return _env("DEEPSEEK_API_KEY")


_PROVIDERS = ("gemini", "openai", "deepseek")


def active_provider() -> Optional[str]:
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


def can_generate() -> bool:
    """Whether a configured provider has credentials for a real API request."""
    provider = active_provider()
    if provider == "gemini":
        return bool(gemini_api_key())
    if provider == "openai":
        return bool(openai_api_key())
    if provider == "deepseek":
        return bool(deepseek_api_key())
    return False


_lama: dict[str, list[float]] = {p: [] for p in _PROVIDERS}
LAMA_DEFAULT = 2.5
LAMA_MAKS = 30.0


def catat_lama(detik: float, provider: Optional[str] = None) -> None:
    provider = provider or active_provider() or "gemini"
    if 0 < detik < LAMA_MAKS:
        bucket = _lama.setdefault(provider, [])
        bucket.append(detik)
        del bucket[:-20]


def perkiraan_lama() -> float:
    urut = sorted(_lama.get(active_provider() or "gemini", []))
    if not urut:
        return LAMA_DEFAULT
    n = len(urut)
    return urut[n // 2] if n % 2 else (urut[n // 2 - 1] + urut[n // 2]) / 2


def punya_ukuran() -> bool:
    return bool(_lama.get(active_provider() or "gemini"))


def explain_error(exc: Exception, model: str = "") -> str:
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


def _urai_json(text: str, akar_array: bool) -> Optional[Any]:
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
        pass
    for kandidat in (text, text[start:end + 1]):
        try:
            parsed = ast.literal_eval(kandidat)
        except (SyntaxError, ValueError):
            continue
        if isinstance(parsed, (dict, list)):
            return parsed
    return None


def _ambil_array(parsed: Any) -> Optional[list[Any]]:
    if isinstance(parsed, list):
        return parsed
    if not isinstance(parsed, dict):
        return None
    for key in ("item", "items", "data", "result"):
        value = parsed.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            nested = _urai_json(value, akar_array=True)
            if isinstance(nested, list):
                return nested
    return None


def _skema_openai(schema: dict) -> dict:
    def ketatkan(value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        out = {key: ketatkan(item) for key, item in value.items()}
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out

    wrapped = (
        {
            "type": "object",
            "properties": {"item": schema},
            "required": ["item"],
            "additionalProperties": False,
        }
        if schema.get("type") == "array"
        else schema
    )
    return ketatkan(wrapped)


def _ke_skema_gemini(schema: Any) -> Any:
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
        blocked = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
        if blocked:
            return None, "permintaan ditahan filter keamanan KALEM"
        return None, "balasan KALEM kosong"

    parsed = _urai_json(text, akar_array=(schema.get("type") == "array"))
    if parsed is None:
        return None, "balasan KALEM nggak kebaca dengan benar"
    return parsed, ""


def _panggil_estilo_openai(
    system_instruction: str, prompt: str, schema: dict, temperature: float,
    *, key: Optional[str], model: str, base_url: Optional[str],
    provider: str, env_var: str,
) -> tuple[Optional[Any], str]:
    try:
        from openai import OpenAI
    except ImportError:
        _log.warning("SDK openai belum terpasang (provider=%s)", provider)
        return None, PESAN_BELUM_DIKONFIGURASI

    if not key:
        _log.info("Provider %s aktif tapi key (%s) kosong", provider, env_var)
        return None, PESAN_BELUM_DIKONFIGURASI

    akar_array = schema.get("type") == "array"
    output_schema = _skema_openai(schema)
    petunjuk_bentuk = (
        "\n\nFORMAT OUTPUT WAJIB:\n"
        "- Balas HANYA JSON valid tanpa markdown atau penjelasan tambahan.\n"
        "- Ikuti JSON Schema ini persis:\n"
        f"{json.dumps(output_schema, ensure_ascii=False)}\n"
        "- Jangan ubah array atau object menjadi string."
    )
    response_format = (
        {
            "type": "json_schema",
            "json_schema": {
                "name": "kalem_response",
                "strict": True,
                "schema": output_schema,
            },
        }
        if provider == "openai"
        else {"type": "json_object"}
    )

    import time

    mulai = time.time()
    try:
        client = OpenAI(api_key=key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format=response_format,
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
        return None, "balasan KALEM kosong"

    parsed = _urai_json(text, akar_array=False)
    if parsed is None:
        return None, "balasan KALEM nggak kebaca dengan benar"
    if akar_array:
        parsed = _ambil_array(parsed)
        if parsed is None:
            return None, "balasan KALEM nggak sesuai format yang diharapkan"
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
    provider = active_provider()
    if provider is None:
        _log.info("Nggak ada provider AI yang kekonfigurasi di .env")
        return None, PESAN_BELUM_DIKONFIGURASI
    return _PANGGIL[provider](system_instruction, prompt, schema, temperature)
