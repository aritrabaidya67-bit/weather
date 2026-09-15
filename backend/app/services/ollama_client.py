"""Ollama integration.

This module **uses the Ollama installation that already exists on the machine**.
It never installs, downloads, pulls or replaces anything:

* it detects the installed binary and the configured model directory
* it asks the running server which models are available (``GET /api/tags``)
* if the server is not running it still reports the models present on disk by
  reading the Ollama manifests directory, so the user can pick one
* the model name is configuration, never hardcoded - if ``OLLAMA_MODEL`` is empty
  the service selects the best already-installed chat model

The browser never talks to Ollama directly; only the backend does.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Sequence

import httpx

from ..core.config import Settings, get_settings
from ..core.logging import get_logger

logger = get_logger("app.ollama")

#: Models whose job is embeddings, not chat - never selected for the chatbot.
_EMBEDDING_HINTS = ("embed", "bge-", "mxbai", "all-minilm")


class OllamaUnavailable(RuntimeError):
    """Raised when Ollama cannot be reached or has no usable chat model."""


@dataclass
class OllamaStatus:
    installed: bool = False
    running: bool = False
    host: str = ""
    models: list[str] = field(default_factory=list)
    selected_model: str | None = None
    binary_path: str | None = None
    models_directory: str | None = None
    source: str = "unknown"
    detail: str = ""
    checked_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "running": self.running,
            "host": self.host,
            "models_available": self.models,
            "model": self.selected_model,
            "binary_path": self.binary_path,
            "models_directory": self.models_directory,
            "source": self.source,
            "detail": self.detail,
        }


def detect_binary() -> str | None:
    """Locate the existing Ollama binary without installing anything."""
    found = shutil.which("ollama")
    if found:
        return found
    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe")
    if program_files:
        candidates.append(Path(program_files) / "Ollama" / "ollama.exe")
    candidates.extend(
        [
            Path("/usr/local/bin/ollama"),
            Path("/usr/bin/ollama"),
            Path("/opt/homebrew/bin/ollama"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def detect_models_directory(settings: Settings | None = None) -> Path | None:
    """Find the model store of the *existing* Ollama installation.

    Nothing is ever written here; the directory is only read so the UI can list
    what is already installed when the server is not running. Resolution order:

    1. ``OLLAMA_MODELS`` - the variable Ollama itself honours, so if the user has
       already moved their store, this is authoritative.
    2. ``OLLAMA_MODELS_DIRS`` - this project's own comma-separated list, for
       machines that keep models off the system drive (e.g. ``D:/OllamaModels``).
       It is configuration, never a hardcoded path, so no machine layout is
       baked into the source.
    3. The conventional per-platform locations.
    """
    settings = settings or get_settings()

    env = os.environ.get("OLLAMA_MODELS")
    if env:
        path = Path(env)
        if path.exists():
            return path

    configured = [Path(entry) for entry in settings.ollama_models_dir_list]
    candidates: list[Path] = list(configured)
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            candidates.append(Path(local_appdata) / "Ollama" / "models")
        candidates.append(Path.home() / ".ollama" / "models")
    else:
        candidates.append(Path.home() / ".ollama" / "models")
        candidates.append(Path("/usr/share/ollama/.ollama/models"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def models_from_disk(models_directory: Path | None) -> list[str]:
    """Read installed model tags straight from the Ollama manifests layout."""
    if models_directory is None:
        return []
    library = models_directory / "manifests" / "registry.ollama.ai" / "library"
    if not library.exists():
        return []
    names: list[str] = []
    try:
        for model_dir in sorted(library.iterdir()):
            if not model_dir.is_dir():
                continue
            for tag_file in sorted(model_dir.iterdir()):
                if tag_file.is_file():
                    names.append(f"{model_dir.name}:{tag_file.name}")
    except OSError:  # pragma: no cover - defensive
        return []
    return names


class OllamaClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._status: OllamaStatus | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ status
    async def status(self, *, refresh: bool = False) -> OllamaStatus:
        async with self._lock:
            if (
                not refresh
                and self._status is not None
                and time.time() - self._status.checked_at < self.settings.ollama_health_cache_seconds
            ):
                return self._status
            self._status = await self._probe()
            return self._status

    async def _probe(self) -> OllamaStatus:
        status = OllamaStatus(host=self.settings.ollama_host, checked_at=time.time())
        binary = detect_binary()
        status.binary_path = binary
        status.installed = binary is not None
        models_dir = detect_models_directory()
        status.models_directory = str(models_dir) if models_dir else None
        disk_models = models_from_disk(models_dir)

        if not self.settings.ollama_enabled:
            status.detail = "Ollama integration is disabled (OLLAMA_ENABLED=false)."
            status.models = disk_models
            status.source = "disabled"
            return status

        server_models: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.settings.ollama_host}/api/tags")
                response.raise_for_status()
                payload = response.json()
            server_models = [
                str(item.get("name") or item.get("model"))
                for item in payload.get("models", [])
                if item.get("name") or item.get("model")
            ]
            status.running = True
            status.source = "server"
        except Exception as exc:  # connection refused, timeout, invalid JSON ...
            status.running = False
            status.source = "disk" if disk_models else "unavailable"
            status.detail = (
                f"Ollama is not reachable at {self.settings.ollama_host} ({exc.__class__.__name__}). "
                "Start the existing Ollama installation (`ollama serve` or the desktop app); "
                "this project never installs or replaces Ollama."
            )

        status.models = server_models or disk_models
        status.selected_model = self._select_model(status.models)
        if status.running and status.selected_model:
            status.detail = f"Using pre-installed model '{status.selected_model}'."
        elif status.running and not status.models:
            status.detail = (
                "Ollama is running but no models were reported. Set OLLAMA_MODEL explicitly "
                "or pull a model with your existing Ollama installation."
            )
        elif status.installed and not disk_models:
            status.detail = status.detail or "Ollama is installed but no models were found on disk."
        if not status.installed and not status.models:
            status.detail = (
                "Ollama was not detected on this machine. The platform keeps working: the chatbot "
                "falls back to its built-in data-grounded analyst. Install nothing unless you want "
                "the LLM narrative features."
            )
        if status.checked_at:
            logger.info(
                "ollama_status",
                installed=status.installed,
                running=status.running,
                models=len(status.models),
                selected=status.selected_model,
                source=status.source,
            )
        return status

    def _select_model(self, models: Sequence[str]) -> str | None:
        """Pick a model: configured first, then the fallback preference list."""
        if not models:
            return None
        normalized = {model: model for model in models}

        def find(name: str) -> str | None:
            if name in normalized:
                return name
            base = name.split(":")[0]
            for model in models:
                if model.split(":")[0] == base:
                    return model
            return None

        configured = self.settings.ollama_model.strip()
        if configured:
            match = find(configured)
            if match:
                logger.info("ollama_model_from_config", model=match)
                return match
            logger.warning(
                "ollama_model_not_installed",
                configured=configured,
                available=list(models)[:10],
            )

        chat_models = [
            model for model in models if not any(hint in model.lower() for hint in _EMBEDDING_HINTS)
        ]
        # Exact tags win over family matches, so an operator who lists "qwen3:4b"
        # before "qwen3:8b" gets the smaller/faster model rather than whichever
        # member of the family the server happened to report first.
        for candidate in self.settings.ollama_fallback_list:
            if candidate in chat_models:
                logger.info("ollama_model_autodetected", model=candidate)
                return candidate
        for candidate in self.settings.ollama_fallback_list:
            for model in chat_models:
                if model.split(":")[0] == candidate.split(":")[0]:
                    logger.info("ollama_model_autodetected", model=model)
                    return model
        if chat_models:
            logger.info("ollama_model_first_available", model=chat_models[0])
            return chat_models[0]
        return None

    async def resolved_model(self, *, refresh: bool = False) -> str:
        status = await self.status(refresh=refresh)
        if not status.selected_model:
            raise OllamaUnavailable(
                status.detail
                or "No usable chat model found. Set OLLAMA_MODEL in backend/.env to an installed model."
            )
        return status.selected_model

    async def ensure_available(self) -> OllamaStatus:
        status = await self.status()
        if not status.running:
            raise OllamaUnavailable(
                status.detail
                or f"Ollama is not running at {self.settings.ollama_host}. Start it and try again."
            )
        if not status.selected_model:
            raise OllamaUnavailable(
                "Ollama is running but no chat model is available. "
                f"Available: {', '.join(status.models) or 'none'}. "
                "Set OLLAMA_MODEL in backend/.env."
            )
        return status

    # -------------------------------------------------------------------- chat
    def _chat_payload(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        stream: bool,
        temperature: float | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self.settings.ollama_keep_alive,
            "options": {
                "temperature": (
                    self.settings.ollama_temperature if temperature is None else temperature
                ),
                "num_ctx": self.settings.ollama_num_ctx,
                "num_predict": max_tokens or self.settings.ollama_num_predict,
            },
        }
        if json_mode:
            payload["format"] = "json"
        if self.settings.ollama_disable_thinking:
            # Ask thinking models for the answer only; ``think`` is honoured by
            # recent Ollama versions and ignored/refused by older ones (handled
            # by the retry in ``chat``/``chat_stream``).
            payload["think"] = False
        return payload

    @staticmethod
    def _without_thinking(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key != "think"}

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> tuple[str, str]:
        """Return ``(answer, model)``."""
        status = await self.ensure_available()
        model = model or status.selected_model
        assert model is not None
        payload = self._chat_payload(
            messages,
            model,
            stream=False,
            temperature=temperature,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )
        logger.info("ollama_request_started", model=model, messages=len(messages), json_mode=json_mode)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.settings.ollama_timeout_seconds) as client:
                response = await client.post(f"{self.settings.ollama_host}/api/chat", json=payload)
                if response.status_code == 400 and "think" in payload:
                    logger.info("ollama_think_flag_unsupported", model=model)
                    payload = self._without_thinking(payload)
                    response = await client.post(
                        f"{self.settings.ollama_host}/api/chat", json=payload
                    )
                if response.status_code == 404:
                    raise OllamaUnavailable(
                        f"Model '{model}' is not installed in the existing Ollama installation. "
                        f"Installed models: {', '.join(status.models) or 'none'}."
                    )
                response.raise_for_status()
                data = response.json()
        except OllamaUnavailable:
            raise
        except httpx.HTTPError as exc:
            logger.error("ollama_request_failed", model=model, error=str(exc))
            raise OllamaUnavailable(f"Ollama request failed: {exc}") from exc
        answer = str((data.get("message") or {}).get("content") or "").strip()
        elapsed = round((time.perf_counter() - started) * 1000)
        logger.info(
            "ollama_request_completed",
            model=model,
            latency_ms=elapsed,
            answer_chars=len(answer),
            eval_count=data.get("eval_count"),
        )
        return answer, model

    async def chat_stream(
        self, messages: list[dict[str, str]], *, model: str | None = None
    ) -> AsyncIterator[tuple[str, str]]:
        """Yield ``(chunk, model)`` tuples as the model produces tokens."""
        status = await self.ensure_available()
        model = model or status.selected_model
        assert model is not None
        payload = self._chat_payload(messages, model, stream=True)
        attempts = 2 if "think" in payload else 1
        logger.info("ollama_stream_started", model=model)
        try:
            async with httpx.AsyncClient(timeout=self.settings.ollama_timeout_seconds) as client:
                for _attempt in range(attempts):
                    async with client.stream(
                        "POST", f"{self.settings.ollama_host}/api/chat", json=payload
                    ) as response:
                        if response.status_code == 400 and "think" in payload:
                            await response.aread()
                            logger.info("ollama_think_flag_unsupported", model=model)
                            payload = self._without_thinking(payload)
                            continue
                        if response.status_code == 404:
                            raise OllamaUnavailable(f"Model '{model}' is not installed.")
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                chunk = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            content = (chunk.get("message") or {}).get("content")
                            if content:
                                yield str(content), model
                            if chunk.get("done"):
                                break
                        # Success: the retry loop is done.
                        break
        except OllamaUnavailable:
            raise
        except httpx.HTTPError as exc:
            logger.error("ollama_stream_failed", model=model, error=str(exc))
            raise OllamaUnavailable(f"Ollama stream failed: {exc}") from exc
        logger.info("ollama_stream_completed", model=model)


_client: OllamaClient | None = None


def get_ollama_client() -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client


def reset_ollama_client() -> None:
    global _client
    _client = None
