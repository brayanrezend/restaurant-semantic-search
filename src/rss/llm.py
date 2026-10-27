import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

from rss import config


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    output: dict
    model: str
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None


def status() -> dict:
    provider, model = config.LLM_PROVIDER, config.LLM_MODEL
    if provider == "none":
        return {"enabled": False, "provider": provider, "model": None, "reason": "LLM_PROVIDER=none"}
    if provider == "ollama":
        try:
            tags = _ollama_get("/api/tags", timeout=2)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = f"Ollama not reachable at {config.OLLAMA_URL}: {e}"
            return {"enabled": False, "provider": provider, "model": model, "reason": reason}
        names = {m["name"] for m in tags.get("models", [])}
        if model not in names and f"{model}:latest" not in names:
            reason = f"model not pulled; run: ollama pull {model}"
            return {"enabled": False, "provider": provider, "model": model, "reason": reason}
        return {"enabled": True, "provider": provider, "model": model, "reason": None}
    if provider == "anthropic":
        try:
            _anthropic_client()
        except Exception as e:
            return {"enabled": False, "provider": provider, "model": model, "reason": f"Anthropic client unavailable: {e}"}
        return {"enabled": True, "provider": provider, "model": model, "reason": None}
    return {"enabled": False, "provider": provider, "model": model, "reason": f"unknown provider {provider}"}


def complete_json(
    system: str, user: str, schema: dict, max_tokens: int = 512, examples: list[tuple[str, str]] = (),
    temperature: float = 0,
) -> LLMResult:
    messages = [m for q, a in examples for m in ({"role": "user", "content": q}, {"role": "assistant", "content": a})]
    messages.append({"role": "user", "content": user})
    if config.LLM_PROVIDER == "ollama":
        return _ollama_json(system, messages, schema, max_tokens, temperature)
    if config.LLM_PROVIDER == "anthropic":
        return _anthropic_json(system, messages, schema, max_tokens)
    raise LLMError(f"LLM provider '{config.LLM_PROVIDER}' is not enabled")


def warm_up() -> None:
    if config.LLM_PROVIDER == "ollama" and status()["enabled"]:
        _ollama_post("/api/generate", {"model": config.LLM_MODEL, "prompt": "", "keep_alive": "30m"}, timeout=120)


def _ollama_get(path: str, timeout: float) -> dict:
    with urllib.request.urlopen(config.OLLAMA_URL + path, timeout=timeout) as r:
        return json.load(r)


def _ollama_post(path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        config.OLLAMA_URL + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _ollama_json(system: str, messages: list[dict], schema: dict, max_tokens: int, temperature: float) -> LLMResult:
    t0 = time.perf_counter()
    try:
        r = _ollama_post("/api/chat", {
            "model": config.LLM_MODEL,
            "messages": [{"role": "system", "content": system}, *messages],
            "format": schema,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }, timeout=config.LLM_TIMEOUT)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f"Ollama request failed: {e}") from e
    try:
        output = json.loads(r["message"]["content"])
    except (KeyError, json.JSONDecodeError) as e:
        raise LLMError(f"Ollama returned invalid JSON: {r.get('message', {}).get('content', '')[:200]}") from e
    return LLMResult(output, config.LLM_MODEL, (time.perf_counter() - t0) * 1000,
                     r.get("prompt_eval_count"), r.get("eval_count"))


@lru_cache
def _anthropic_client():
    import anthropic

    return anthropic.Anthropic(timeout=config.LLM_TIMEOUT)


def _anthropic_json(system: str, messages: list[dict], schema: dict, max_tokens: int) -> LLMResult:
    import anthropic

    t0 = time.perf_counter()
    try:
        response = _anthropic_client().beta.messages.create(
            model=config.LLM_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
    except anthropic.APIConnectionError as e:
        raise LLMError(f"Anthropic connection error: {e}") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
    if response.stop_reason == "refusal":
        raise LLMError("Anthropic declined the request")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        output = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"Anthropic returned invalid JSON: {text[:200]}") from e
    return LLMResult(output, response.model, (time.perf_counter() - t0) * 1000,
                     response.usage.input_tokens, response.usage.output_tokens)
