"""Groq provider (free tier from console.groq.com; very fast open models)."""

from __future__ import annotations

import json
import re
from typing import Iterator

import groq

from .common import ANALYSIS_SYSTEM, CHAT_SYSTEM, AnalyzerError, analysis_prompt, chat_context
from .schema import AnalysisResult

# Preferred order: strongest general models first. Used as-is when the model list can't be fetched.
PREFERRED_MODELS = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
_SKIP = ("whisper", "tts", "guard", "embed", "playai", "orpheus", "compound", "prompt")

_SCHEMA = json.dumps(AnalysisResult.model_json_schema(), separators=(",", ":"))
JSON_INSTRUCTIONS = (
    "\n\nReturn ONLY a single JSON object (no markdown, no commentary) that is valid against this JSON Schema. "
    "Fill every field.\n" + _SCHEMA
)


def make_client(api_key: str | None) -> groq.Groq:
    try:
        # With no key passed, the SDK reads GROQ_API_KEY from the environment.
        return groq.Groq(api_key=api_key) if api_key else groq.Groq()
    except groq.GroqError as exc:
        raise AnalyzerError("No Groq API key found. Enter one in the sidebar or set GROQ_API_KEY in .env.") from exc


def list_models(api_key: str) -> list[str]:
    """Chat models available to this key, preferred ones first."""
    try:
        names = {
            m.id for m in make_client(api_key).models.list().data
            if getattr(m, "active", True) and not any(s in m.id.lower() for s in _SKIP)
        }
    except Exception:
        return PREFERRED_MODELS
    if not names:
        return PREFERRED_MODELS
    preferred = [m for m in PREFERRED_MODELS if m in names]
    return preferred + sorted(names - set(preferred))


def _wrap_errors(exc: Exception) -> AnalyzerError:
    if isinstance(exc, AnalyzerError):
        return exc
    detail = ""
    if isinstance(exc, groq.APIStatusError):
        body = exc.body if isinstance(exc.body, dict) else {}
        detail = (body.get("error") or {}).get("message", "") if isinstance(body.get("error"), dict) else str(exc)
    if isinstance(exc, groq.RateLimitError):
        return AnalyzerError(
            "Groq free-tier limit reached for this model (requests or tokens per minute/day). Wait a minute, "
            f"or pick a different model in the sidebar.\n\nDetails: {detail[:400]}"
        )
    if isinstance(exc, (groq.AuthenticationError, groq.PermissionDeniedError)):
        return AnalyzerError("Invalid Groq API key. Create one at console.groq.com and paste it in the sidebar.")
    if isinstance(exc, groq.NotFoundError):
        return AnalyzerError("This Groq model isn't available. Pick another model in the sidebar.")
    if isinstance(exc, groq.APIStatusError) and exc.status_code == 413:
        return AnalyzerError("The request is too large for this model's free-tier limit. Try a shorter job "
                             "description or another model.")
    if isinstance(exc, groq.BadRequestError):
        return AnalyzerError(f"Groq rejected the request: {detail[:400]}")
    if isinstance(exc, groq.APIStatusError):
        return AnalyzerError(f"Groq API error ({exc.status_code}). Please try again in a moment.")
    if isinstance(exc, groq.APIConnectionError):
        return AnalyzerError("Could not reach the Groq API. Check your internet connection.")
    return AnalyzerError(f"Unexpected error: {exc}")


def _extract_json(text: str) -> str:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    return fenced.group(1) if fenced else text


def analyze(
    client: groq.Groq,
    model: str,
    resume_text: str,
    job_text: str,
    effort: str = "medium",
    extra_instructions: str = "",
) -> AnalysisResult:
    extra = {"reasoning_effort": effort} if "gpt-oss" in model else {}
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM + JSON_INSTRUCTIONS},
                {"role": "user", "content": analysis_prompt(resume_text, job_text, extra_instructions)},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=8000,
            temperature=0.3,
            **extra,
        )
    except Exception as exc:
        raise _wrap_errors(exc) from exc

    choice = completion.choices[0]
    try:
        return AnalysisResult.model_validate_json(_extract_json(choice.message.content or ""))
    except Exception as exc:
        hint = " The answer was cut off; try a larger model." if choice.finish_reason == "length" else ""
        raise AnalyzerError(f"{model} returned JSON that doesn't match the report format.{hint} "
                            "Please try again or pick a larger model.") from exc


def chat_stream(
    client: groq.Groq,
    model: str,
    resume_text: str,
    job_text: str,
    analysis: AnalysisResult,
    history: list[dict],
) -> Iterator[str]:
    """Stream a coach reply. `history` is the list of {role, content} messages ending with the user turn."""
    messages = [{"role": "system", "content": f"{CHAT_SYSTEM}\n\n{chat_context(resume_text, job_text, analysis)}"}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    extra = {"reasoning_effort": "low"} if "gpt-oss" in model else {}
    try:
        stream = client.chat.completions.create(
            model=model, messages=messages, max_completion_tokens=4000, stream=True, **extra
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as exc:
        raise _wrap_errors(exc) from exc
