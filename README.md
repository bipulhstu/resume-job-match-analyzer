# 📄 Resume ↔ Job Match Analyzer

An LLM-powered web app that compares a resume against a job description and produces an interactive dashboard plus a downloadable, multi-page PDF report.

Built with **Streamlit**. It works with **Google Gemini** (free tier, the default), **Groq** (free tier, very fast open models) or **Anthropic Claude** (Claude Opus 5.5, needs API credits). Pick the provider in the sidebar.

## Features

| Area | What you get |
|---|---|
| **Inputs** | Upload a resume/JD as PDF, DOCX, TXT or MD, or paste text. One-click sample data. Optional "focus" question. |
| **Scores** | Overall match % and ATS score (gauges), verdict badge, per-category scores (radar chart). |
| **Skills** | Matched-skill chips, skill gaps ranked *critical / important / nice-to-have* with how to close each gap (filterable). |
| **Keywords** | Keyword coverage donut chart and found/missing keyword list. |
| **Section feedback** | Score and concrete suggestions for each resume section (bar chart + expanders). |
| **Bullet rewrites** | Before/after rewrites of weak bullets; tick the ones you like and download them. |
| **ATS check** | Formatting/wording issues that hurt ATS parsing; missing keywords to add. |
| **Action plan** | Interactive checklist with progress bar, plus tailored interview questions. |
| **Ask the Coach** | Streaming chat that knows your resume, the job and the analysis (e.g. "rewrite my summary", "draft a cover letter"). |
| **Report** | Professional 4-5 page PDF report and raw JSON export. |
| **Demo mode** | Explore the full UI with a pre-generated analysis, no API key needed. |

## How it works

```
Resume (PDF/DOCX/TXT) ─┐
                       ├─► text extraction ─► LLM (structured JSON output, Pydantic schema) ─► AnalysisResult
Job description ───────┘                     (Gemini/Groq/Claude)                                 │
                                         ┌────────────────────────────────────────────────────────┤
                                         ▼                         ▼                              ▼
                              Streamlit dashboard          PDF report (ReportLab)        Coach chat (streaming)
```

- `core/parser.py` extracts text from PDF (`pypdf`) and DOCX (`python-docx`).
- `core/schema.py` defines the analysis as a Pydantic model. Both providers use **structured JSON output** with this schema, so the UI never has to parse free text.
- `core/analyzer.py` routes each request to the selected provider:
  - `core/gemini_llm.py` uses the `google-genai` SDK. "Analysis depth" maps to Gemini's thinking level. If a model doesn't support thinking levels, the request is retried without them. The model list is fetched from your key, with Flash-Lite models first.
  - `core/groq_llm.py` uses the `groq` SDK in JSON mode (the schema is included in the prompt and the reply is validated with Pydantic). For `gpt-oss` models, "Analysis depth" maps to `reasoning_effort`.
  - `core/claude_llm.py` uses the `anthropic` SDK with adaptive thinking. "Analysis depth" maps to the `effort` setting. The coach chat uses prompt caching.
- `core/common.py` holds the prompts shared by both providers.
- `core/report.py` builds the PDF with ReportLab (score cards, bar chart, tables).
- `app.py` is the Streamlit UI.

## Setup

Requires Python 3.10+.

```bash
cd resume-job-match-analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Get a **free Gemini API key** at https://aistudio.google.com (click "Get API key"). Then either paste it into the sidebar at runtime, or save it in `.env`:

```bash
cp .env.example .env   # then set GEMINI_API_KEY=...
```

**Groq (optional, also free):** create a key at https://console.groq.com → API Keys, then choose "Groq" in the sidebar and paste it, or set `GROQ_API_KEY` in `.env`.

To use Claude instead, set `ANTHROPIC_API_KEY` (from https://console.anthropic.com; needs API credits) and choose "Anthropic Claude" in the sidebar.

## Run

```bash
streamlit run app.py
```

Open http://localhost:8501. Click **Use sample** on both inputs, then **Analyze match**. Or turn on **Demo mode** in the sidebar to try it without a key.

## Deploy (free) on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Choose this repository, branch `main`, main file `app.py`.
4. Open **Advanced settings** and pick Python **3.12**.
5. Click **Deploy**. After a few minutes the app is live at a `*.streamlit.app` link.

**API key:** don't add your own key to a public app, or every visitor will use your free quota. Visitors can paste their own free Gemini or Groq key in the sidebar, or use **Demo mode**. To build a key in anyway, add `GEMINI_API_KEY = "..."` under the app's **Settings → Secrets**.

A `Dockerfile` is also included if you want to run the app in a container (`docker build -t resume-analyzer . && docker run -p 8501:8501 resume-analyzer`).

## Project structure

```
resume-job-match-analyzer/
├── app.py                 # Streamlit UI
├── core/
│   ├── analyzer.py        # routes requests to the selected provider
│   ├── gemini_llm.py      # Google Gemini provider
│   ├── groq_llm.py        # Groq provider
│   ├── claude_llm.py      # Anthropic Claude provider
│   ├── common.py          # shared prompts
│   ├── parser.py          # PDF / DOCX / TXT text extraction
│   ├── report.py          # PDF report generation
│   └── schema.py          # Pydantic output schema
├── samples/               # sample resume, job description, demo analysis
├── requirements.txt
└── .env.example
```

## Cost and limits

- **Gemini free tier:** free. Each analysis is **one request**, and each coach message is one more. Free tiers have per-minute and per-day request limits per model. If you see "limit reached", wait a minute or switch to a Flash-Lite model in the sidebar (they have the highest free limits). Daily limits reset at midnight Pacific time. Note: on the free tier, Google may use your inputs to improve its products, so prefer sample data over real personal resumes.
- **Groq free tier:** free, with request and token limits per minute and per day for each model (see console.groq.com → Settings → Limits). One analysis is about 6-10k tokens, so smaller per-minute token limits can be hit; wait a minute or switch models.
- **Claude Opus 5.5:** about **$0.10-0.20 per analysis** at standard API pricing. A Claude Pro subscription does not include API credits.

## Limitations

- Scanned (image-only) PDFs have no extractable text. Use a text-based PDF or DOCX.
- Scores are AI judgements, not a real ATS. Treat them as guidance.
- Rewrites may contain placeholders like `[X%]`. Replace them with your real numbers; never add experience you don't have.
