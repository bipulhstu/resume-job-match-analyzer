"""Structured output schema returned by the LLM analysis."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class CategoryScore(BaseModel):
    category: Literal["Skills", "Experience", "Education", "Keywords", "ATS Formatting"]
    score: int = Field(description="0-100")
    comment: str = Field(description="One or two sentences explaining the score")


class SkillGap(BaseModel):
    skill: str
    importance: Literal["critical", "important", "nice-to-have"]
    how_to_address: str = Field(description="Concrete advice: a course, project, or how to surface existing experience")


class KeywordHit(BaseModel):
    keyword: str = Field(description="Important keyword or phrase from the job description")
    found: bool = Field(description="True if the resume contains it or a clear equivalent")


class SectionFeedback(BaseModel):
    section: str = Field(description="Resume section, e.g. Summary, Experience, Projects, Skills, Education")
    score: int = Field(description="0-100")
    feedback: str
    suggestions: List[str]


class BulletRewrite(BaseModel):
    original: str = Field(description="Bullet copied verbatim from the resume")
    improved: str = Field(description="Rewritten bullet: action verb, measurable impact, job-relevant keywords")
    reason: str


class AnalysisResult(BaseModel):
    candidate_name: str = Field(description="Name from the resume, or 'Candidate' if not found")
    target_role: str = Field(description="Job title from the job description")
    overall_match_score: int = Field(description="0-100 overall fit for this job")
    ats_score: int = Field(description="0-100 likelihood of passing an applicant tracking system screen")
    verdict: Literal["Excellent match", "Strong match", "Moderate match", "Weak match", "Poor match"]
    executive_summary: str = Field(description="3-5 sentence summary of fit for a hiring manager")
    category_scores: List[CategoryScore] = Field(description="Exactly one entry per category")
    matched_skills: List[str]
    missing_skills: List[SkillGap]
    keywords: List[KeywordHit] = Field(description="15-25 most important job keywords")
    strengths: List[str]
    weaknesses: List[str]
    section_feedback: List[SectionFeedback]
    bullet_rewrites: List[BulletRewrite] = Field(description="4-8 of the weakest or most improvable bullets")
    ats_issues: List[str] = Field(description="Formatting or wording issues that could hurt ATS parsing")
    interview_questions: List[str] = Field(description="6-8 questions the candidate should prepare for, tailored to the gaps")
    action_plan: List[str] = Field(description="Prioritized, concrete next steps to improve the application")
