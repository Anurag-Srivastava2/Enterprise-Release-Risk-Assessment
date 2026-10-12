import os
from datetime import date, timedelta
from uuid import uuid4

from dotenv import load_dotenv
import streamlit as st

from release_assessment import (
    build_release_data,
    create_release_crew,
    run_traced_assessment,
    validate_release_data,
)

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
LANGFUSE_ENV_VARS = (
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_BASE_URL",
)

st.set_page_config(
    page_title="Enterprise Release Risk Assessment",
    page_icon=":material/fact_check:",
    layout="wide",
)

st.title("Enterprise Release Risk Assessment")
st.write(
    "Four CrewAI agents assess release, QA, security, and management readiness."
)
st.caption(f"Model: {GEMINI_MODEL}")

if all(os.getenv(name) for name in LANGFUSE_ENV_VARS):
    st.caption("Langfuse tracing is configured.")
elif any(os.getenv(name) for name in LANGFUSE_ENV_VARS):
    st.warning(
        "Langfuse tracing is partially configured. Set all three Langfuse "
        "environment variables or remove the partial configuration."
    )
else:
    st.info(
        "Langfuse tracing is disabled. Configure its environment variables "
        "to record agent traces."
    )


@st.cache_resource
def initialize_langfuse():
    from langfuse import get_client
    from openinference.instrumentation.crewai import CrewAIInstrumentor

    CrewAIInstrumentor().instrument(
        skip_dep_check=True,
        use_event_listener=True,
        create_llm_spans=True,
    )
    return get_client()


with st.form("release_inputs"):
    st.subheader("Release overview")
    release_name = st.text_input(
        "Release name",
        value="Customer Platform v4.2",
    )
    planned_release_date = st.date_input(
        "Planned release date",
        value=date.today() + timedelta(days=7),
    )
    release_scope = st.text_area(
        "Release changes and scope",
        value=(
            "- New customer onboarding workflow\n"
            "- Payment API enhancement\n"
            "- Authentication performance improvement\n"
            "- Customer database schema update"
        ),
        height=120,
    )
    dependencies = st.text_area(
        "Dependencies and owners/status",
        value="- Payment Gateway\n- Identity Service\n- Customer Database",
        height=100,
    )
    deployment_risks = st.text_area(
        "Known deployment risks and mitigations",
        value="Database schema update; verify backward compatibility and migration monitoring.",
        height=90,
    )

    st.subheader("Quality assurance")
    qa_cols = st.columns(4)
    total_tests = qa_cols[0].number_input(
        "Total test cases", min_value=0, value=520, step=1
    )
    passed_tests = qa_cols[1].number_input(
        "Passed", min_value=0, value=505, step=1
    )
    failed_tests = qa_cols[2].number_input(
        "Failed", min_value=0, value=10, step=1
    )
    blocked_tests = qa_cols[3].number_input(
        "Blocked", min_value=0, value=5, step=1
    )
    regression_completion = st.slider(
        "Regression completion (%)",
        min_value=0,
        max_value=100,
        value=97,
    )

    with st.expander("Defects and security findings"):
        defect_cols = st.columns(4)
        critical_defects = defect_cols[0].number_input(
            "Critical defects", min_value=0, value=0, step=1
        )
        high_defects = defect_cols[1].number_input(
            "High defects", min_value=0, value=2, step=1
        )
        medium_defects = defect_cols[2].number_input(
            "Medium defects", min_value=0, value=7, step=1
        )
        low_defects = defect_cols[3].number_input(
            "Low defects", min_value=0, value=15, step=1
        )

        security_cols = st.columns(3)
        critical_vulnerabilities = security_cols[0].number_input(
            "Critical vulnerabilities", min_value=0, value=0, step=1
        )
        high_vulnerabilities = security_cols[1].number_input(
            "High vulnerabilities", min_value=0, value=1, step=1
        )
        medium_vulnerabilities = security_cols[2].number_input(
            "Medium vulnerabilities", min_value=0, value=3, step=1
        )

    st.subheader("Rollback readiness")
    rollback_cols = st.columns(2)
    rollback_available = rollback_cols[0].selectbox(
        "Rollback plan",
        ["Available", "Not available", "Unknown"],
    )
    rollback_tested = rollback_cols[1].selectbox(
        "Rollback test status",
        ["Tested successfully", "Test failed", "Not tested", "Unknown"],
    )

    submitted = st.form_submit_button(
        "Assess release readiness",
        type="primary",
    )

if submitted:
    release_data = build_release_data(
        release_name=release_name,
        planned_release_date=planned_release_date.isoformat(),
        release_scope=release_scope,
        dependencies=dependencies,
        deployment_risks=deployment_risks,
        total_tests=int(total_tests),
        passed_tests=int(passed_tests),
        failed_tests=int(failed_tests),
        blocked_tests=int(blocked_tests),
        regression_completion=int(regression_completion),
        critical_defects=int(critical_defects),
        high_defects=int(high_defects),
        medium_defects=int(medium_defects),
        low_defects=int(low_defects),
        critical_vulnerabilities=int(critical_vulnerabilities),
        high_vulnerabilities=int(high_vulnerabilities),
        medium_vulnerabilities=int(medium_vulnerabilities),
        rollback_available=rollback_available,
        rollback_tested=rollback_tested,
    )
    validation_errors = validate_release_data(release_data)
    if validation_errors:
        for error in validation_errors:
            st.error(error)
    elif not os.getenv("GEMINI_API_KEY"):
        st.error(
            "Set the GEMINI_API_KEY environment variable before running an assessment."
        )
    elif any(os.getenv(name) for name in LANGFUSE_ENV_VARS) and not all(
        os.getenv(name) for name in LANGFUSE_ENV_VARS
    ):
        st.error(
            "Set LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, and LANGFUSE_BASE_URL "
            "to enable tracing, or remove the partial Langfuse configuration."
        )
    else:
        try:
            with st.spinner("Release, QA, security, and management agents are reviewing the evidence..."):
                if all(os.getenv(name) for name in LANGFUSE_ENV_VARS):
                    langfuse = initialize_langfuse()
                    if not langfuse.auth_check():
                        st.error(
                            "Langfuse authentication failed. Check the configured "
                            "credentials and base URL."
                        )
                        st.stop()
                    session_id = st.session_state.setdefault(
                        "langfuse_session_id",
                        str(uuid4()),
                    )
                    try:
                        assessment = run_traced_assessment(
                            langfuse,
                            session_id,
                            release_data,
                            create_release_crew,
                        )
                    finally:
                        langfuse.flush()
                else:
                    assessment = create_release_crew(release_data).kickoff()
        except Exception as exc:
            st.error(f"Assessment failed: {exc}")
        else:
            st.subheader("Release readiness report")
            st.markdown(str(assessment))
            st.caption(
                "AI-generated assessment supports—but does not replace—review "
                "and approval by accountable release, QA, security, and engineering owners."
            )
