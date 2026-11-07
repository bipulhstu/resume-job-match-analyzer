"""Claude (Anthropic API) provider."""

from __future__ import annotations

from typing import Iterator

import anthropic

from .common import ANALYSIS_SYSTEM, CHAT_SYSTEM, AnalyzerError, analysis_prompt, chat_context
from .schema import AnalysisResult

MODEL = "claude-opus-5-5"
# Server-side fallback: if a request is ever declined by a safety classifier,
# the API re-runs it on a suitable fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

def make_client(api_key: str | None) -> anthropic.Anthropic:
    # With no key passed, the SDK falls back to ANTHROPIC_API_KEY / saved `ant auth login` profile.
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def _wrap_errors(exc: Exception) -> AnalyzerError:
    if isinstance(exc, anthropic.AuthenticationError):
        return AnalyzerError("Invalid API key. Check the key in the sidebar or your .env file.")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return AnalyzerError("This API key does not have access to the model.")
    if isinstance(exc, anthropic.RateLimitError):
        return AnalyzerError("Rate limit reached. Wait a minute and try again.")
    if isinstance(exc, anthropic.BadRequestError):
        body = exc.body if isinstance(exc.body, dict) else {}
        detail = body.get("error", {}).get("message", exc.message)
        return AnalyzerError(f"The request was rejected: {detail}")
    if isinstance(exc, anthropic.APIStatusError):
        return AnalyzerError(f"Claude API error ({exc.status_code}). Please try again.")
    if isinstance(exc, anthropic.APIConnectionError):
        return AnalyzerError("Could not reach the Claude API. Check your internet connection.")
    if "authentication method" in str(exc) or "api_key" in str(exc).lower():
        return AnalyzerError("No API key found. Enter one in the sidebar or set ANTHROPIC_API_KEY in .env.")
    return AnalyzerError(f"Unexpected error: {exc}")


def analyze(
    client: anthropic.Anthropic,
    resume_text: str,
    job_text: str,
    effort: str = "medium",
    extra_instructions: str = "",
) -> AnalysisResult:
    user_content = analysis_prompt(resume_text, job_text, extra_instructions)

    try:
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=ANALYSIS_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            output_format=AnalysisResult,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except (anthropic.AnthropicError, TypeError) as exc:  # TypeError: no credentials configured
        raise _wrap_errors(exc) from exc

    if response.stop_reason == "refusal":
        raise AnalyzerError("The model declined to analyse this content. Please check the uploaded files.")
    if response.stop_reason == "max_tokens":
        raise AnalyzerError("The analysis was cut off. Try a shorter job description or lower analysis depth.")
    if response.parsed_output is None:
        raise AnalyzerError("The model returned an unreadable result. Please try again.")
    return response.parsed_output


def chat_stream(
    client: anthropic.Anthropic,
    resume_text: str,
    job_text: str,
    analysis: AnalysisResult,
    history: list[dict],
) -> Iterator[str]:
    """Stream a coach reply. `history` is the list of {role, content} messages ending with the user turn."""
    context = chat_context(resume_text, job_text, analysis)
    try:
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=8000,
            system=[
                {"type": "text", "text": CHAT_SYSTEM},
                # Resume + JD + analysis are identical every turn, so cache them.
                {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
            ],
            messages=history,
            output_config={"effort": "low"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
            if final.stop_reason == "refusal":
                yield "\n\n_The model declined to answer this question._"
    except (anthropic.AnthropicError, TypeError) as exc:  # TypeError: no credentials configured
        raise _wrap_errors(exc) from exc
