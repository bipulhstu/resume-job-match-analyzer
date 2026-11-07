"""Prompts and helpers shared by every LLM provider."""

from __future__ import annotations

import json

from .schema import AnalysisResult

ANALYSIS_SYSTEM = """You are a senior technical recruiter and certified resume writer who has \
screened thousands of applications and knows how applicant tracking systems (ATS) parse resumes.

Evaluate the RESUME against the JOB DESCRIPTION honestly and specifically:
- Base every judgement on evidence in the resume text. Never invent experience the candidate does not have.
- Scores are 0-100. Be calibrated: 85+ only for candidates who meet nearly all requirements; below 50 when \
critical requirements are missing.
- "category_scores" must contain exactly one entry for each of: Skills, Experience, Education, Keywords, ATS Formatting.
- "matched_skills" are skills the job asks for that the resume demonstrates.
- "missing_skills" are job requirements absent or weakly evidenced in the resume.
- Bullet rewrites must keep the original facts; you may suggest where the candidate should add a real metric \
using a placeholder like [X%] rather than fabricating numbers.
- Write feedback the candidate can act on today. Be direct but encouraging."""

CHAT_SYSTEM = """You are a friendly, expert career coach. You have already analysed the candidate's resume \
against a specific job. Answer the candidate's questions using the resume, the job description and your \
analysis below. Be concrete and concise, use markdown, and never invent experience the candidate does not have."""


class AnalyzerError(Exception):
    """Error with a message that is safe to show to the user."""


def analysis_prompt(resume_text: str, job_text: str, extra_instructions: str = "") -> str:
    prompt = (
        f"<resume>\n{resume_text}\n</resume>\n\n"
        f"<job_description>\n{job_text}\n</job_description>\n\n"
        "Produce the full structured analysis."
    )
    if extra_instructions.strip():
        prompt += f"\n\nAdditional focus requested by the candidate: {extra_instructions.strip()}"
    return prompt


def chat_context(resume_text: str, job_text: str, analysis: AnalysisResult) -> str:
    return (
        f"<resume>\n{resume_text}\n</resume>\n\n"
        f"<job_description>\n{job_text}\n</job_description>\n\n"
        f"<analysis>\n{json.dumps(analysis.model_dump(), indent=1)}\n</analysis>"
    )
