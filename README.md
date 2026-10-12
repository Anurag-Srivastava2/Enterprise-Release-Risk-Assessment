# Enterprise Release Risk Assessment

A Streamlit application that uses four CrewAI agents to assess release
readiness across release/deployment, QA, security, and release management.
CrewAI traces and model/token usage can be sent to Langfuse.

## Configure

Install the dependencies into a Python 3.10+ environment:

```powershell
python -m pip install -r requirements.txt
```

Fill in the local `.env` file (if setting up a fresh checkout, first copy
`.env.example` to `.env`). The app loads `.env` at startup, and `.env` is
excluded from Git. Do not commit API keys or put them in source files:

```dotenv
GEMINI_API_KEY=your_google_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite-preview
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

Langfuse variables are optional as a group. When all are configured, the app
checks Langfuse authentication and records a root assessment observation and
CrewAI child/LLM observations. Root input/output, session ID, and assessment
metadata are included. When none are configured, assessments can run without
tracing.

## Deploy to Streamlit Community Cloud

Deploy `app.py` from the root of the `main` branch. In the app's **Manage app**
settings, add the following TOML under **Secrets**, replacing the placeholders
with your own credentials:

```toml
GEMINI_API_KEY = "your_google_gemini_api_key"
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
LANGFUSE_PUBLIC_KEY = "your_langfuse_public_key"
LANGFUSE_SECRET_KEY = "your_langfuse_secret_key"
LANGFUSE_BASE_URL = "https://us.cloud.langfuse.com"
```

The app reads these values from Streamlit Secrets and uses them for the
environment-based CrewAI and Langfuse configuration. Keep credentials in
Streamlit Secrets or a local `.env`; never commit either to GitHub.

## Run

```powershell
streamlit run app.py
```

Enter the release scope, dependency information, QA counts, defects,
vulnerabilities, deployment risks, and rollback status. Test counts must add up
to the entered total. Four agents produce specialist assessments and a
consolidated GO, CONDITIONAL GO, or NO-GO report.

The report is decision support, not a substitute for accountable release,
quality, security, and engineering approvals. Verify facts and evidence before
making a production decision. Release data is sent to the configured Gemini
provider and, when enabled, Langfuse.
