"""Single entry point that routes analysis and chat to the selected LLM provider."""

from __future__ import annotations

from typing import Iterator

from .common import AnalyzerError
from .schema import AnalysisResult

PROVIDERS = {
    "Google Gemini (free tier)": "gemini",
    "Groq (free tier, fast)": "groq",
    "Anthropic Claude": "claude",
}
CLAUDE_MODEL = "claude-opus-5-5"

__all__ = ["PROVIDERS", "CLAUDE_MODEL", "AnalyzerError", "analyze", "chat_stream"]


def analyze(provider: str, api_key: str, model: str, resume_text: str, job_text: str,
            effort: str = "medium", extra_instructions: str = "") -> AnalysisResult:
    if provider == "groq":
        from . import groq_llm as q
        return q.analyze(q.make_client(api_key), model, resume_text, job_text, effort, extra_instructions)
    if provider == "gemini":
        from . import gemini_llm as g
        return g.analyze(g.make_client(api_key), model, resume_text, job_text, effort, extra_instructions)
    from . import claude_llm as c
    return c.analyze(c.make_client(api_key), resume_text, job_text, effort, extra_instructions)


def chat_stream(provider: str, api_key: str, model: str, resume_text: str, job_text: str,
                analysis: AnalysisResult, history: list[dict]) -> Iterator[str]:
    if provider == "groq":
        from . import groq_llm as q
        yield from q.chat_stream(q.make_client(api_key), model, resume_text, job_text, analysis, history)
    elif provider == "gemini":
        from . import gemini_llm as g
        yield from g.chat_stream(g.make_client(api_key), model, resume_text, job_text, analysis, history)
    else:
        from . import claude_llm as c
        yield from c.chat_stream(c.make_client(api_key), resume_text, job_text, analysis, history)
