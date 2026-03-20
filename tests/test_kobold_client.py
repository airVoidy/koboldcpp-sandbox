from __future__ import annotations

import json

import httpx

from kobold_sandbox.kobold_client import KoboldClient, KoboldGenerationConfig
from kobold_sandbox.models import ImageGenerationResponse, NativeGenerateResponse, OpenAIChatCompletionResponse


def test_openai_mode_uses_chat_completions_and_extracts_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.read().decode("utf-8"))
        assert payload["model"] == "demo-model"
        assert payload["temperature"] == 0.3
        assert payload["max_tokens"] == 123
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "<think>hidden</think>Hello from OpenAI mode",
                        }
                    }
                ]
            },
        )

    client = KoboldClient(
        "http://kobold.local",
        api_mode="openai",
        transport=httpx.MockTransport(handler),
    )
    raw = client.chat(
        prompt="ping",
        model="demo-model",
        system_prompt="system",
        config=KoboldGenerationConfig(temperature=0.3, max_tokens=123),
    )

    assert client.extract_text(raw) == "Hello from OpenAI mode"
    assert client.extract_chat_text(raw) == "<think>hidden</think>Hello from OpenAI mode"
    parsed = OpenAIChatCompletionResponse.model_validate(raw)
    assert parsed.choices[0].message.content == "<think>hidden</think>Hello from OpenAI mode"


def test_native_mode_uses_generate_endpoint_and_extracts_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/generate"
        payload = json.loads(request.read().decode("utf-8"))
        assert payload["max_length"] == 64
        assert "System:\nKeep it short" in payload["prompt"]
        return httpx.Response(200, json={"results": [{"text": " Native reply "}]})

    client = KoboldClient(
        "http://kobold.local",
        api_mode="native",
        transport=httpx.MockTransport(handler),
    )
    raw = client.chat(
        prompt="ping",
        system_prompt="Keep it short",
        config=KoboldGenerationConfig(max_tokens=64),
    )

    assert client.extract_text(raw) == "Native reply"
    assert client.extract_chat_text(raw) == "Native reply"
    parsed = NativeGenerateResponse.model_validate(raw)
    assert parsed.results[0].text == " Native reply "


def test_chat_without_explicit_max_tokens_omits_limit() -> None:
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read().decode("utf-8"))
        seen_payloads.append(payload)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = KoboldClient(
        "http://kobold.local",
        api_mode="openai",
        transport=httpx.MockTransport(handler),
    )

    client.chat(prompt="ping")

    assert "max_tokens" not in seen_payloads[0]


def test_extract_chat_text_merges_completed_think_blocks() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"text": "<think>one</think>"},
                        {"text": "<think>two</think>"},
                        {"text": "answer"},
                    ]
                }
            }
        ]
    }

    assert KoboldClient.extract_chat_text(response) == "<think>onetwo</think>answer"
    assert KoboldClient.extract_text(response) == "answer"


def test_auto_mode_falls_back_to_native_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(404, json={"error": "missing"})
        if request.url.path == "/api/v1/model":
            return httpx.Response(200, json={"result": "koboldcpp/local-model"})
        raise AssertionError(f"Unexpected path: {request.url.path}")

    client = KoboldClient(
        "http://kobold.local",
        api_mode="auto",
        transport=httpx.MockTransport(handler),
    )

    assert client.list_models() == ["koboldcpp/local-model"]


def test_image_generation_uses_sdapi_txt2img() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sdapi/v1/txt2img":
            payload = json.loads(request.read().decode("utf-8"))
            assert payload["prompt"] == "red cube"
            assert payload["negative_prompt"] == "blurry"
            assert payload["steps"] == 8
            assert payload["width"] == 640
            assert payload["height"] == 384
            assert payload["sampler_name"] == "Euler"
            return httpx.Response(
                200,
                json={
                    "images": ["ZmFrZS1wbmc="],
                    "parameters": payload,
                    "info": "{\"seed\":123}",
                },
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    client = KoboldClient(
        "http://kobold.local",
        api_mode="auto",
        transport=httpx.MockTransport(handler),
    )
    raw = client.generate_image(
        prompt="red cube",
        negative_prompt="blurry",
        steps=8,
        width=640,
        height=384,
        sampler_name="Euler",
    )

    parsed = ImageGenerationResponse.model_validate(raw)
    assert parsed.images == ["ZmFrZS1wbmc="]
    assert parsed.parameters["prompt"] == "red cube"


def test_list_image_samplers_reads_sdapi() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sdapi/v1/samplers":
            return httpx.Response(
                200,
                json=[
                    {"name": "Euler", "aliases": ["k_euler"], "options": {}},
                    {"name": "DPM++ 2M", "aliases": [], "options": {}},
                ],
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    client = KoboldClient(
        "http://kobold.local",
        api_mode="openai",
        transport=httpx.MockTransport(handler),
    )

    assert client.list_image_samplers() == ["Euler", "DPM++ 2M"]
