"""
Model backends — unified interface for local (ollama) and remote (API) LLMs.
Each agent picks its backend; the orchestrator doesn't care which.
"""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelResponse:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0


class OllamaBackend:
    """Local model via ollama HTTP API (localhost:11434 by default)."""

    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")

    def generate(self, prompt: str, system: str = "", temperature: float = 0.7) -> ModelResponse:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": temperature},
        }
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
            return ModelResponse(
                text=body.get("response", ""),
                model=self.model,
                tokens_in=body.get("prompt_eval_count", 0),
                tokens_out=body.get("eval_count", 0),
                latency_ms=body.get("total_duration", 0) / 1e6,
            )
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            return ModelResponse(text=f"[ollama unreachable: {e}]", model=self.model)

    def chat(self, messages: list[dict], temperature: float = 0.7) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
            msg = body.get("message", {})
            return ModelResponse(
                text=msg.get("content", ""),
                model=self.model,
                tokens_in=body.get("prompt_eval_count", 0),
                tokens_out=body.get("eval_count", 0),
                latency_ms=body.get("total_duration", 0) / 1e6,
            )
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            return ModelResponse(text=f"[ollama unreachable: {e}]", model=self.model)


class AnthropicBackend:
    """Remote model via Anthropic Messages API."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str = ""):
        self.model = model
        self.api_key = api_key

    def generate(self, prompt: str, system: str = "", temperature: float = 0.7) -> ModelResponse:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, system=system, temperature=temperature)

    def chat(self, messages: list[dict], system: str = "", temperature: float = 0.7) -> ModelResponse:
        if not self.api_key:
            return ModelResponse(text="[no API key set]", model=self.model)
        payload: dict = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            import time
            t0 = time.monotonic()
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
            elapsed = (time.monotonic() - t0) * 1000
            text = ""
            for block in body.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            usage = body.get("usage", {})
            return ModelResponse(
                text=text,
                model=self.model,
                tokens_in=usage.get("input_tokens", 0),
                tokens_out=usage.get("output_tokens", 0),
                latency_ms=elapsed,
            )
        except Exception as e:
            return ModelResponse(text=f"[API error: {e}]", model=self.model)


def get_backend(config: dict):
    backend_type = config.get("backend", "ollama")
    if backend_type == "ollama":
        return OllamaBackend(
            model=config.get("model", "llama3"),
            host=config.get("host", "http://localhost:11434"),
        )
    elif backend_type == "anthropic":
        return AnthropicBackend(
            model=config.get("model", "claude-sonnet-4-20250514"),
            api_key=config.get("api_key", ""),
        )
    raise ValueError(f"Unknown backend: {backend_type}")
