"""Resume ↔ Job Match Analyzer — Streamlit UI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from core.analyzer import CLAUDE_MODEL, PROVIDERS, AnalyzerError, analyze, chat_stream
from core.gemini_llm import FALLBACK_MODELS
from core.gemini_llm import list_models as list_gemini_models
from core.groq_llm import PREFERRED_MODELS as GROQ_MODELS
from core.groq_llm import list_models as list_groq_models
from core.parser import SUPPORTED_TYPES, ParseError, extract_text
from core.report import build_pdf
from core.schema import AnalysisResult

load_dotenv()
ROOT = Path(__file__).parent
SAMPLES = ROOT / "samples"

st.set_page_config(page_title="Resume ↔ Job Match Analyzer", page_icon="📄", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.hero {background: linear-gradient(120deg,#2563EB,#7C3AED); color:white; padding:1.4rem 1.8rem;
       border-radius:14px; margin-bottom:1.2rem;}
.hero h1 {color:white; margin:0; font-size:2rem;}
.hero p {margin:.3rem 0 0; opacity:.9;}
.chip {display:inline-block; padding:.25rem .65rem; margin:.2rem; border-radius:999px; font-size:.85rem;}
.chip-good {background:#DCFCE7; color:#166534;}
.chip-bad {background:#FEE2E2; color:#991B1B;}
.verdict {display:inline-block; padding:.35rem .9rem; border-radius:8px; font-weight:600; color:white;}
.small-muted {color:#64748B; font-size:.85rem;}
</style>
""",
    unsafe_allow_html=True,
)

# ---------- state ----------
ss = st.session_state
ss.setdefault("analysis", None)
ss.setdefault("resume_text", "")
ss.setdefault("job_text", "")
ss.setdefault("chat", [])
ss.setdefault("done_steps", set())


@st.cache_data(ttl=3600, show_spinner=False)
def groq_models(key: str) -> list[str]:
    return list_groq_models(key)


@st.cache_data(ttl=3600, show_spinner=False)
def gemini_models(key: str) -> list[str]:
    return list_gemini_models(key)


def color_for(score: int) -> str:
    return "#16A34A" if score >= 75 else "#D97706" if score >= 50 else "#DC2626"


# ---------- sidebar ----------
with st.sidebar:
    st.header("⚙️ Settings")
    demo_mode = st.toggle("Demo mode (no API key needed)", value=False,
                          help="Shows a pre-generated analysis of the sample resume so you can explore the UI.")
    provider_label = st.selectbox("LLM provider", list(PROVIDERS), disabled=demo_mode)
    provider = PROVIDERS[provider_label]
    if provider == "gemini":
        api_key = st.text_input("Gemini API key", type="password",
                                value=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", ""),
                                disabled=demo_mode, help="Free key from aistudio.google.com. Stored only in this session.")
        model_options = gemini_models(api_key) if api_key else FALLBACK_MODELS
        model = st.selectbox("Gemini model", model_options, disabled=demo_mode,
                             help="Flash-Lite models have the highest free-tier limits.")
        st.caption("⚠️ Free-tier inputs may be used by Google to improve its products. Avoid sensitive personal data.")
    elif provider == "groq":
        api_key = st.text_input("Groq API key", type="password", value=os.getenv("GROQ_API_KEY", ""),
                                disabled=demo_mode, help="Free key from console.groq.com. Stored only in this session.")
        model = st.selectbox("Groq model", groq_models(api_key) if api_key else GROQ_MODELS, disabled=demo_mode,
                             help="Larger models give better reports; if you hit a limit, try another model.")
    else:
        api_key = st.text_input("Anthropic API key", type="password", value=os.getenv("ANTHROPIC_API_KEY", ""),
                                disabled=demo_mode, help="Get one at console.anthropic.com (needs API credits).")
        model = CLAUDE_MODEL
    depth_label = st.select_slider("Analysis depth", options=["Quick", "Standard", "Deep"], value="Standard",
                                   disabled=demo_mode, help="Deeper analysis is more thorough but slower.")
    effort = {"Quick": "low", "Standard": "medium", "Deep": "high"}[depth_label]
    st.divider()
    st.markdown("**How it works**\n1. Add your resume\n2. Add the job description\n3. Click **Analyze**\n"
                "4. Explore the results, chat with the coach, download the PDF report")
    st.caption(f"Model: {'demo data' if demo_mode else model}")
    if ss.analysis and st.button("🔄 Start over", width="stretch"):
        for k in ("analysis", "chat"):
            ss[k] = None if k == "analysis" else []
        ss.done_steps = set()
        st.rerun()

st.markdown(
    '<div class="hero"><h1>📄 Resume ↔ Job Match Analyzer</h1>'
    "<p>Upload your resume and a job description to get an ATS score, skill-gap analysis, "
    "rewritten bullet points, interview prep and a downloadable PDF report.</p></div>",
    unsafe_allow_html=True,
)

# ---------- inputs ----------
c1, c2 = st.columns(2, gap="large")


def _load_sample(key: str, sample_file: str) -> None:
    # Runs before widgets are drawn, so it may set their state.
    ss[f"{key}_mode"] = "Paste text"
    ss[f"{key}_paste"] = (SAMPLES / sample_file).read_text()


def text_input_block(col, title: str, key: str, sample_file: str, placeholder: str) -> str:
    with col:
        st.subheader(title)
        mode = st.radio("Input method", ["Upload file", "Paste text"], horizontal=True,
                        key=f"{key}_mode", label_visibility="collapsed")
        text = ""
        if mode == "Upload file":
            f = st.file_uploader(f"Upload ({', '.join(SUPPORTED_TYPES)})", type=SUPPORTED_TYPES, key=f"{key}_file")
            if f is not None:
                try:
                    text = extract_text(f.name, f.getvalue())
                    st.success(f"Extracted {len(text.split()):,} words from {f.name}")
                    with st.expander("Preview extracted text"):
                        st.text(text[:4000] + ("…" if len(text) > 4000 else ""))
                except ParseError as e:
                    st.error(str(e))
        else:
            text = st.text_area("Paste here", height=260, key=f"{key}_paste", placeholder=placeholder,
                                label_visibility="collapsed")
        st.button("Use sample", key=f"{key}_sample", on_click=_load_sample, args=(key, sample_file))
        return text.strip()


resume_text = text_input_block(c1, "1️⃣ Your resume", "resume", "sample_resume.txt",
                               "Paste your resume text…")
job_text = text_input_block(c2, "2️⃣ Job description", "job", "sample_job_description.txt",
                            "Paste the full job posting…")

focus = st.text_input("Optional: anything specific you want feedback on?",
                      placeholder="e.g. I'm switching from QA to backend — how do I position that?")

ready = demo_mode or (len(resume_text) >= 50 and len(job_text) >= 50)
if st.button("🔍 Analyze match", type="primary", width="stretch", disabled=not ready):
    ss.chat, ss.done_steps = [], set()
    if demo_mode:
        ss.analysis = AnalysisResult.model_validate_json((SAMPLES / "sample_analysis.json").read_text())
        ss.resume_text = (SAMPLES / "sample_resume.txt").read_text()
        ss.job_text = (SAMPLES / "sample_job_description.txt").read_text()
    else:
        with st.spinner(f"{model} is reviewing your resume ({depth_label.lower()} analysis)… this can take up to a minute."):
            try:
                ss.analysis = analyze(provider, api_key, model, resume_text, job_text, effort, focus)
                ss.resume_text, ss.job_text = resume_text, job_text
            except AnalyzerError as e:
                st.error(str(e))
if not ready:
    st.caption("Add both a resume and a job description (or turn on Demo mode) to enable analysis.")

r: AnalysisResult | None = ss.analysis
if r is None:
    st.stop()

# ---------- results header ----------
st.divider()
h1, h2 = st.columns([3, 1])
with h1:
    st.markdown(f"## Results for **{r.candidate_name}**")
    st.markdown(f'<span class="small-muted">Target role: {r.target_role}</span>', unsafe_allow_html=True)
with h2:
    st.markdown(f'<div style="text-align:right;margin-top:1.2rem"><span class="verdict" '
                f'style="background:{color_for(r.overall_match_score)}">{r.verdict}</span></div>',
                unsafe_allow_html=True)


def gauge(value: int, title: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, number={"suffix": "%"}, title={"text": title, "font": {"size": 15}},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": color_for(value)},
               "steps": [{"range": [0, 50], "color": "rgba(220,38,38,.15)"}, {"range": [50, 75], "color": "rgba(217,119,6,.15)"},
                         {"range": [75, 100], "color": "rgba(22,163,74,.15)"}]}))
    fig.update_layout(height=210, margin=dict(l=20, r=20, t=50, b=10))
    return fig


g1, g2, g3, g4 = st.columns(4)
g1.plotly_chart(gauge(r.overall_match_score, "Overall match"), width="stretch")
g2.plotly_chart(gauge(r.ats_score, "ATS score"), width="stretch")
kw_found = sum(k.found for k in r.keywords)
g3.metric("Skills matched", len(r.matched_skills))
g3.metric("Critical gaps", sum(g.importance == "critical" for g in r.missing_skills))
g4.metric("Keywords found", f"{kw_found}/{len(r.keywords)}")
g4.metric("Bullets to improve", len(r.bullet_rewrites))

st.info(r.executive_summary)

d1, d2, _ = st.columns([1, 1, 2])
d1.download_button("📥 Download PDF report", data=build_pdf(r), file_name=f"resume_report_{r.candidate_name.replace(' ', '_')}.pdf",
                   mime="application/pdf", width="stretch", type="primary")
d2.download_button("🧾 Download JSON", data=json.dumps(r.model_dump(), indent=2), file_name="resume_analysis.json",
                   mime="application/json", width="stretch")

tabs = st.tabs(["📊 Overview", "🧩 Skills", "📝 Sections", "✍️ Rewrites", "🤖 ATS",
                "🎯 Plan & Interview", "💬 Ask the Coach"])

# ---------- Overview ----------
with tabs[0]:
    a, b = st.columns([1, 1])
    with a:
        cats = [c.category for c in r.category_scores]
        vals = [c.score for c in r.category_scores]
        radar = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=cats + cats[:1], fill="toself",
                                          line_color="#2563EB", fillcolor="rgba(37,99,235,.25)"))
        radar.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(range=[0, 100])), height=380, showlegend=False,
                            margin=dict(l=40, r=40, t=30, b=30), title="Category profile")
        st.plotly_chart(radar, width="stretch")
    with b:
        st.markdown("#### Category scores")
        for c in r.category_scores:
            st.markdown(f"**{c.category}** — {c.score}/100")
            st.progress(c.score / 100)
            st.caption(c.comment)
    s1, s2 = st.columns(2)
    with s1:
        st.markdown("#### ✅ Strengths")
        for s in r.strengths:
            st.markdown(f"- {s}")
    with s2:
        st.markdown("#### ⚠️ Weaknesses")
        for w in r.weaknesses:
            st.markdown(f"- {w}")

# ---------- Skills ----------
with tabs[1]:
    st.markdown("#### Matched skills")
    st.markdown("".join(f'<span class="chip chip-good">✔ {s}</span>' for s in r.matched_skills) or "None",
                unsafe_allow_html=True)
    st.markdown("#### Skill gaps")
    levels = st.multiselect("Filter by importance", ["critical", "important", "nice-to-have"],
                            default=["critical", "important", "nice-to-have"])
    icon = {"critical": "🔴", "important": "🟠", "nice-to-have": "⚪"}
    for g in [g for g in r.missing_skills if g.importance in levels]:
        with st.expander(f"{icon[g.importance]} {g.skill} — {g.importance}"):
            st.write(g.how_to_address)
    st.markdown("#### Keyword coverage")
    k1, k2 = st.columns([1, 2])
    with k1:
        donut = go.Figure(go.Pie(labels=["Found", "Missing"], values=[kw_found, len(r.keywords) - kw_found],
                                 hole=.6, marker_colors=["#16A34A", "#DC2626"], sort=False))
        donut.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), showlegend=True)
        st.plotly_chart(donut, width="stretch")
    with k2:
        st.markdown("".join(
            f'<span class="chip {"chip-good" if k.found else "chip-bad"}">{"✔" if k.found else "✘"} {k.keyword}</span>'
            for k in sorted(r.keywords, key=lambda k: k.found)), unsafe_allow_html=True)

# ---------- Section feedback ----------
with tabs[2]:
    bar = go.Figure(go.Bar(x=[s.score for s in r.section_feedback], y=[s.section for s in r.section_feedback],
                           orientation="h", marker_color=[color_for(s.score) for s in r.section_feedback],
                           text=[s.score for s in r.section_feedback], textposition="outside"))
    bar.update_layout(height=60 + 45 * len(r.section_feedback), xaxis=dict(range=[0, 110]),
                      margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(autorange="reversed"))
    st.plotly_chart(bar, width="stretch")
    for s in r.section_feedback:
        with st.expander(f"{s.section} — {s.score}/100", expanded=s.score < 60):
            st.write(s.feedback)
            for tip in s.suggestions:
                st.markdown(f"- {tip}")

# ---------- Bullet rewrites ----------
with tabs[3]:
    st.caption("Tick the rewrites you like, then download them. Replace placeholders like [X%] with your real numbers.")
    chosen = []
    for i, b in enumerate(r.bullet_rewrites):
        with st.container(border=True):
            o, n = st.columns(2)
            o.markdown("**Before**")
            o.markdown(f"> {b.original}")
            n.markdown("**After**")
            n.markdown(f"> {b.improved}")
            st.caption(f"💡 {b.reason}")
            if st.checkbox("Use this rewrite", key=f"rw_{i}", value=True):
                chosen.append(b.improved)
    st.download_button("📋 Download selected bullets (.txt)", data="\n".join(f"• {c}" for c in chosen),
                       file_name="improved_bullets.txt", disabled=not chosen)

# ---------- ATS ----------
with tabs[4]:
    st.plotly_chart(gauge(r.ats_score, "ATS compatibility"), width="content")
    st.markdown("#### Issues that may hurt ATS parsing")
    for issue in r.ats_issues or ["No major issues found."]:
        st.warning(issue)
    missing_kw = [k.keyword for k in r.keywords if not k.found]
    if missing_kw:
        st.markdown("#### Keywords to add (only if you genuinely have the experience)")
        st.code(", ".join(missing_kw), language=None)

# ---------- Action plan ----------
with tabs[5]:
    a, b = st.columns(2)
    with a:
        st.markdown("#### 🎯 Your action plan")
        for i, step in enumerate(r.action_plan):
            if st.checkbox(step, key=f"plan_{i}", value=i in ss.done_steps):
                ss.done_steps.add(i)
            else:
                ss.done_steps.discard(i)
        st.progress(len(ss.done_steps) / max(len(r.action_plan), 1),
                    text=f"{len(ss.done_steps)}/{len(r.action_plan)} steps done")
    with b:
        st.markdown("#### 🎤 Interview questions to prepare")
        for i, q in enumerate(r.interview_questions, 1):
            st.markdown(f"**{i}.** {q}")
        st.caption("Tip: ask the coach in the next tab to draft an answer for any of these.")

# ---------- Chat ----------
with tabs[6]:
    st.markdown("Ask follow-up questions about your resume, the job, or how to close the gaps.")
    if demo_mode:
        st.info("The coach chat needs an API key. Turn off Demo mode and add your key in the sidebar.")
    else:
        suggestions = ["Rewrite my summary for this job", "Draft an answer to interview question 1",
                       "Write a short cover letter", "Which gap should I fix first?"]
        cols = st.columns(len(suggestions))
        clicked = next((s for c, s in zip(cols, suggestions) if c.button(s, width="stretch")), None)
        for m in ss.chat:
            st.chat_message(m["role"]).markdown(m["content"])
        prompt = st.chat_input("Ask the coach…") or clicked
        if prompt:
            ss.chat.append({"role": "user", "content": prompt})
            st.chat_message("user").markdown(prompt)
            with st.chat_message("assistant"):
                try:
                    reply = st.write_stream(chat_stream(provider, api_key, model, ss.resume_text, ss.job_text, r, ss.chat))
                    ss.chat.append({"role": "assistant", "content": reply})
                except AnalyzerError as e:
                    ss.chat.pop()
                    st.error(str(e))
