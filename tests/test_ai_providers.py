"""Tes format output OpenAI dan DeepSeek tanpa memanggil jaringan."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.core import ai_client, decomposer_logic


def test_parser_menerima_wrapper_string_python() -> None:
    raw = '{"item": "[{\'tugas\': \'Kalkulus\', \'langkah\': [\'Buka buku\', \'Cari rumus\']}]"}'
    parsed = ai_client._urai_json(raw, akar_array=False)
    items = ai_client._ambil_array(parsed)
    assert items == [
        {"tugas": "Kalkulus", "langkah": ["Buka buku", "Cari rumus"]}
    ]


def test_nested_langkah_dinormalisasi_dan_dibatasi_lima() -> None:
    title = "Kerjain 10 soal kalkulus"
    response = [
        {
            "tugas": title,
            "langkah": [
                {"langkah": "Buka buku"},
                {"langkah": "Cari rumus"},
                {"langkah": "Baca soal pertama"},
                {"langkah": "Tulis informasi yang diketahui"},
                {"langkah": "Kerjakan soal pertama"},
                {"langkah": "Langkah keenam harus dibuang"},
            ],
        }
    ]
    with patch.object(decomposer_logic, "perkiraan_menit", return_value={title: 40}), patch.object(
        ai_client, "generate_json", return_value=(response, "")
    ):
        steps, reason = decomposer_logic._ai_steps([{"title": title}], 3)
    assert reason == ""
    assert steps is not None and len(steps) == 5
    assert all("[{'" not in step for _title, step, _minutes in steps)


def test_openai_memakai_json_schema_strict() -> None:
    captured = {}

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self.create)
            )

        def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(
                content='{"item":[{"tugas":"Kalkulus","langkah":"Buka buku"}]}'
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    with patch("openai.OpenAI", FakeOpenAI):
        parsed, reason = ai_client._panggil_estilo_openai(
            "system", "prompt", decomposer_logic.RESPONSE_SCHEMA, 0.2,
            key="dummy", model="gpt-test", base_url=None,
            provider="openai", env_var="OPENAI_API_KEY",
        )
    assert reason == ""
    assert parsed[0]["langkah"] == "Buka buku"
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True


def test_deepseek_memakai_schema_prompt_dan_normalisasi_wrapper() -> None:
    captured = {}

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self.create)
            )

        def create(self, **kwargs):
            captured.update(kwargs)
            content = '{"item":"[{\'tugas\':\'Kalkulus\',\'langkah\':[\'Buka buku\']}]"}'
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    with patch("openai.OpenAI", FakeOpenAI):
        parsed, reason = ai_client._panggil_estilo_openai(
            "system", "prompt", decomposer_logic.RESPONSE_SCHEMA, 0.2,
            key="dummy", model="deepseek-test", base_url="https://example.test",
            provider="deepseek", env_var="DEEPSEEK_API_KEY",
        )
    assert reason == ""
    assert parsed[0]["langkah"] == ["Buka buku"]
    assert captured["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in captured["messages"][0]["content"]


def main() -> None:
    tests = [
        test_parser_menerima_wrapper_string_python,
        test_nested_langkah_dinormalisasi_dan_dibatasi_lima,
        test_openai_memakai_json_schema_strict,
        test_deepseek_memakai_schema_prompt_dan_normalisasi_wrapper,
    ]
    for test in tests:
        test()
        print(f"[OK] {test.__name__}")


if __name__ == "__main__":
    main()
