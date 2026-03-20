from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

import httpx

from .models import (
    ImageGenerationRequest,
    ImageGenerationResponse,
    ImageSamplerDescriptor,
    NativeGenerateRequest,
    NativeGenerateResponse,
    NativeModelResponse,
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIChatMessage,
    OpenAIModelsResponse,
)


ApiMode = Literal["auto", "openai", "native"]
ResponseModelT = TypeVar("ResponseModelT")


@dataclass(frozen=True)
class KoboldGenerationConfig:
    temperature: float = 0.2
    max_tokens: int | None = None


class _BaseKoboldApi:
    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def _request_json(self, method: str, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout, transport=self.transport, trust_env=False) as client:
            response = client.request(method, f"{self.base_url}{path}", json=json)
            response.raise_for_status()
            return response.json()

    def _request_model(
        self,
        method: str,
        path: str,
        response_model: type[ResponseModelT],
        json: dict[str, Any] | None = None,
    ) -> ResponseModelT:
        return response_model.model_validate(self._request_json(method, path, json=json))

    def chat(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        config: KoboldGenerationConfig | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        raise NotImplementedError

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        steps: int = 20,
        width: int = 512,
        height: int = 512,
        cfg_scale: float = 7.0,
        sampler_name: str | None = None,
        batch_size: int = 1,
    ) -> dict[str, Any]:
        payload = ImageGenerationRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            steps=steps,
            width=width,
            height=height,
            cfg_scale=cfg_scale,
            sampler_name=sampler_name,
            batch_size=batch_size,
        )
        return self._request_model(
            "POST",
            "/sdapi/v1/txt2img",
            ImageGenerationResponse,
            json=payload.model_dump(exclude_none=True),
        ).model_dump(exclude_none=True)

    def list_image_samplers(self) -> list[str]:
        with httpx.Client(timeout=self.timeout, transport=self.transport, trust_env=False) as client:
            response = client.get(f"{self.base_url}/sdapi/v1/samplers")
            response.raise_for_status()
            payload = response.json()
        return [item.name for item in [ImageSamplerDescriptor.model_validate(entry) for entry in payload]]


class OpenAICompatibleKoboldApi(_BaseKoboldApi):
    def chat_response(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        config: KoboldGenerationConfig | None = None,
    ) -> OpenAIChatCompletionResponse:
        cfg = config or KoboldGenerationConfig()
        messages: list[OpenAIChatMessage] = []
        if system_prompt:
            messages.append(OpenAIChatMessage(role="system", content=system_prompt))
        messages.append(OpenAIChatMessage(role="user", content=prompt))
        payload = OpenAIChatCompletionRequest(
            messages=messages,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            model=model,
        )
        return self._request_model(
            "POST",
            "/v1/chat/completions",
            OpenAIChatCompletionResponse,
            json=payload.model_dump(exclude_none=True),
        )

    def chat(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        config: KoboldGenerationConfig | None = None,
    ) -> dict[str, Any]:
        return self.chat_response(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            config=config,
        ).model_dump(exclude_none=True)

    def list_models(self) -> list[str]:
        response = self._request_model("GET", "/v1/models", OpenAIModelsResponse)
        return [item.id for item in response.data if item.id]


class NativeKoboldApi(_BaseKoboldApi):
    def chat_response(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        config: KoboldGenerationConfig | None = None,
    ) -> NativeGenerateResponse:
        cfg = config or KoboldGenerationConfig()
        payload = NativeGenerateRequest(
            prompt=self._build_prompt(prompt=prompt, system_prompt=system_prompt),
            temperature=cfg.temperature,
            max_length=cfg.max_tokens,
            model=model,
        )
        return self._request_model(
            "POST",
            "/api/v1/generate",
            NativeGenerateResponse,
            json=payload.model_dump(exclude_none=True),
        )

    def chat(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        config: KoboldGenerationConfig | None = None,
    ) -> dict[str, Any]:
        return self.chat_response(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            config=config,
        ).model_dump(exclude_none=True)

    def list_models(self) -> list[str]:
        response = self._request_model("GET", "/api/v1/model", NativeModelResponse)
        return [response.result] if response.result else []

    @staticmethod
    def _build_prompt(prompt: str, system_prompt: str | None = None) -> str:
        parts: list[str] = []
        if system_prompt:
            parts.append(f"System:\n{system_prompt.strip()}")
        parts.append(prompt)
        return "\n\n".join(part for part in parts if part.strip())


class KoboldClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        api_mode: ApiMode = "auto",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_mode = api_mode
        self.transport = transport
        self._api = self._build_api(api_mode)

    def _build_api(self, api_mode: ApiMode) -> _BaseKoboldApi:
        if api_mode == "openai":
            return OpenAICompatibleKoboldApi(self.base_url, timeout=self.timeout, transport=self.transport)
        if api_mode == "native":
            return NativeKoboldApi(self.base_url, timeout=self.timeout, transport=self.transport)
        return OpenAICompatibleKoboldApi(self.base_url, timeout=self.timeout, transport=self.transport)

    def chat(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        config: KoboldGenerationConfig | None = None,
    ) -> dict[str, Any]:
        try:
            return self._api.chat(prompt=prompt, model=model, system_prompt=system_prompt, config=config)
        except httpx.HTTPStatusError as exc:
            if self.api_mode != "auto" or not self._should_fallback(exc):
                raise
            native_api = NativeKoboldApi(self.base_url, timeout=self.timeout, transport=self.transport)
            self._api = native_api
            return native_api.chat(prompt=prompt, model=model, system_prompt=system_prompt, config=config)

    def list_models(self) -> list[str]:
        try:
            models = self._api.list_models()
        except httpx.HTTPStatusError as exc:
            if self.api_mode != "auto" or not self._should_fallback(exc):
                raise
            self._api = NativeKoboldApi(self.base_url, timeout=self.timeout, transport=self.transport)
            return self._api.list_models()
        if models or self.api_mode != "auto":
            return models
        self._api = NativeKoboldApi(self.base_url, timeout=self.timeout, transport=self.transport)
        return self._api.list_models()

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        steps: int = 20,
        width: int = 512,
        height: int = 512,
        cfg_scale: float = 7.0,
        sampler_name: str | None = None,
        batch_size: int = 1,
    ) -> dict[str, Any]:
        return self._api.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            steps=steps,
            width=width,
            height=height,
            cfg_scale=cfg_scale,
            sampler_name=sampler_name,
            batch_size=batch_size,
        )

    def list_image_samplers(self) -> list[str]:
        return self._api.list_image_samplers()

    @staticmethod
    def _should_fallback(exc: httpx.HTTPStatusError) -> bool:
        return exc.response.status_code in {404, 405, 501}

    @staticmethod
    def extract_text(response: dict[str, Any]) -> str:
        return KoboldClient._extract_text(response, strip_thinking=True)

    @staticmethod
    def extract_chat_text(response: dict[str, Any]) -> str:
        return KoboldClient._extract_text(response, strip_thinking=False)

    @staticmethod
    def _extract_text(response: dict[str, Any], strip_thinking: bool) -> str:
        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                parts = [item.get("text", "") for item in content if isinstance(item, dict)]
                text = "".join(part for part in parts if part)
            else:
                text = str(content or "")
            return KoboldClient._normalize_text(text, strip_thinking=strip_thinking)

        results = response.get("results") or []
        if results:
            return KoboldClient._normalize_text(str(results[0].get("text") or ""), strip_thinking=strip_thinking)
        return ""

    @staticmethod
    def _normalize_text(text: str, strip_thinking: bool) -> str:
        merged = KoboldClient._merge_completed_thinking(text)
        if strip_thinking:
            merged = re.sub(r"<think\b[^>]*>.*?</think>", "", merged, flags=re.DOTALL | re.IGNORECASE)
        return merged.strip()

    @staticmethod
    def _merge_completed_thinking(text: str) -> str:
        merged = text
        pattern = re.compile(r"<think\b([^>]*)>(.*?)</think>\s*<think\b\1>(.*?)</think>", re.DOTALL | re.IGNORECASE)
        while True:
            collapsed = pattern.sub(lambda match: f"<think{match.group(1)}>{match.group(2)}{match.group(3)}</think>", merged)
            if collapsed == merged:
                break
            merged = collapsed
        return merged

    @staticmethod
    def _strip_thinking(text: str) -> str:
        text = re.sub(r"<think\b[^>]*>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        return text.strip()
