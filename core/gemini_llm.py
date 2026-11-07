"""Google Gemini provider (works with the free tier from aistudio.google.com)."""

from __future__ import annotations

from typing import Iterator

from google import genai
from google.genai import errors, types

from .common import ANALYSIS_SYSTEM, CHAT_SYSTEM, AnalyzerError, analysis_prompt, chat_context
from .schema import AnalysisResult

# Used when the model list can't be fetched. Flash-Lite first: it has the most generous free-tier limits.
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash"]
_SKIP = ("image", "tts", "audio", "live", "embedding", "vision", "robotics", "computer-use", "learnlm")

THINKING = {"low": types.ThinkingLevel.LOW, "medium": types.ThinkingLevel.MEDIUM, "high": types.ThinkingLevel.HIGH}


def make_client(api_key: str | None) -> genai.Client:
    # With no key passed, the SDK reads GEMINI_API_KEY / GOOGLE_API_KEY from the environment.
    try:
        return genai.Client(api_key=api_key) if api_key else genai.Client()
    except ValueError as exc:  # raised when no key is configured at all
        raise AnalyzerError("No Gemini API key found. Enter one in the sidebar or set GEMINI_API_KEY in .env.") from exc


def list_models(api_key: str) -> list[str]:
    """Text-generation Gemini models available to this key; Flash-Lite models first."""
    try:
        names = [
            m.name.removeprefix("models/")
            for m in make_client(api_key).models.list()
            if m.name and m.name.startswith("models/gemini")
            and "generateContent" in (m.supported_actions or [])
            and not any(s in m.name for s in _SKIP)
        ]
    except Exception:
        return FALLBACK_MODELS
    if not names:
        return FALLBACK_MODELS
    names = sorted(set(names), reverse=True)  # newest versions first
    return sorted(names, key=lambda n: (0 if "flash-lite" in n else 1 if "flash" in n else 2))


def _wrap_errors(exc: Exception) -> AnalyzerError:
    if isinstance(exc, AnalyzerError):
        return exc
    if isinstance(exc, errors.APIError):
        detail = (exc.message or "").strip()
        if exc.code == 429:
            return AnalyzerError(
                "Gemini free-tier limit reached for this model. If it's a per-minute limit, wait about a minute; "
                "if it's a daily limit, try a Flash-Lite model or come back tomorrow (it resets at midnight "
                f"Pacific time).\n\nDetails: {detail[:400]}"
            )
        if exc.code in (401, 403) or "API key not valid" in detail:
            return AnalyzerError("Invalid Gemini API key. Create one at aistudio.google.com and paste it in the sidebar.")
        if exc.code == 404:
            return AnalyzerError("This Gemini model isn't available for your key. Pick another model in the sidebar.")
        if exc.code == 400:
            return AnalyzerError(f"Gemini rejected the request: {detail[:400]}")
        return AnalyzerError(f"Gemini API error ({exc.code}). Please try again in a moment.")
    if "connect" in type(exc).__name__.lower() or "timeout" in type(exc).__name__.lower():
        return AnalyzerError("Could not reach the Gemini API. Check your internet connection.")
    return AnalyzerError(f"Unexpected error: {exc}")


def _is_thinking_unsupported(exc: Exception) -> bool:
    return isinstance(exc, errors.APIError) and exc.code == 400 and "thinking" in (exc.message or "").lower()


def analyze(
    client: genai.Client,
    model: str,
    resume_text: str,
    job_text: str,
    effort: str = "medium",
    extra_instructions: str = "",
) -> AnalysisResult:
    def config(with_thinking: bool) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=ANALYSIS_SYSTEM,
            response_mime_type="application/json",
            response_schema=AnalysisResult,
            max_output_tokens=16000,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING[effort]) if with_thinking else None,
        )

    prompt = analysis_prompt(resume_text, job_text, extra_instructions)
    try:
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config(True))
        except errors.APIError as exc:
            # Some (older / lite) models don't accept a thinking level; retry once without it.
            if not _is_thinking_unsupported(exc):
                raise
            response = client.models.generate_content(model=model, contents=prompt, config=config(False))
    except Exception as exc:
        raise _wrap_errors(exc) from exc

    result = response.parsed
    if isinstance(result, AnalysisResult):
        return result
    try:  # fall back to validating the raw JSON text
        return AnalysisResult.model_validate_json(response.text or "")
    except Exception as exc:
        reason = ""
        if response.candidates and response.candidates[0].finish_reason:
            reason = f" (finish reason: {response.candidates[0].finish_reason.name})"
        raise AnalyzerError(f"Gemini returned an incomplete result{reason}. Please try again.") from exc


def chat_stream(
    client: genai.Client,
    model: str,
    resume_text: str,
    job_text: str,
    analysis: AnalysisResult,
    history: list[dict],
) -> Iterator[str]:
    """Stream a coach reply. `history` is the list of {role, content} messages ending with the user turn."""
    contents = [
        types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])])
        for m in history
    ]
    config = types.GenerateContentConfig(
        system_instruction=f"{CHAT_SYSTEM}\n\n{chat_context(resume_text, job_text, analysis)}",
        max_output_tokens=8000,
    )
    try:
        for chunk in client.models.generate_content_stream(model=model, contents=contents, config=config):
            if chunk.text:
                yield chunk.text
    except Exception as exc:
        raise _wrap_errors(exc) from exc
