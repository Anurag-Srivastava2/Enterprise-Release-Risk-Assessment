from crewai import Agent, Crew, LLM, Process, Task


def build_release_data(**values):
    return {
        "release_name": str(values["release_name"]).strip(),
        "planned_release_date": str(values["planned_release_date"]),
        "release_scope": str(values["release_scope"]).strip(),
        "dependencies": str(values["dependencies"]).strip(),
        "deployment_risks": str(values["deployment_risks"]).strip(),
        "qa": {
            "total_tests": int(values["total_tests"]),
            "passed": int(values["passed_tests"]),
            "failed": int(values["failed_tests"]),
            "blocked": int(values["blocked_tests"]),
            "regression_completion_percent": int(
                values["regression_completion"]
            ),
            "defects": {
                "critical": int(values["critical_defects"]),
                "high": int(values["high_defects"]),
                "medium": int(values["medium_defects"]),
                "low": int(values["low_defects"]),
            },
        },
        "security": {
            "vulnerabilities": {
                "critical": int(values["critical_vulnerabilities"]),
                "high": int(values["high_vulnerabilities"]),
                "medium": int(values["medium_vulnerabilities"]),
            }
        },
        "rollback": {
            "plan": str(values["rollback_available"]),
            "test_status": str(values["rollback_tested"]),
        },
    }


def validate_release_data(release_data):
    errors = []
    if not release_data["release_name"]:
        errors.append("Release name is required.")
    if not release_data["release_scope"]:
        errors.append("Describe the release scope and changes.")
    if not release_data["dependencies"]:
        errors.append("List dependencies or explicitly enter 'None'.")

    qa = release_data["qa"]
    test_total = qa["passed"] + qa["failed"] + qa["blocked"]
    if test_total != qa["total_tests"]:
        errors.append(
            "Passed, failed, and blocked test counts must sum to the total "
            f"({test_total} entered, {qa['total_tests']} total)."
        )

    if not 0 <= qa["regression_completion_percent"] <= 100:
        errors.append("Regression completion must be between 0 and 100.")

    numeric_values = [
        qa["total_tests"],
        qa["passed"],
        qa["failed"],
        qa["blocked"],
        *qa["defects"].values(),
        *release_data["security"]["vulnerabilities"].values(),
    ]
    if any(value < 0 for value in numeric_values):
        errors.append("Test, defect, and vulnerability counts cannot be negative.")

    return errors


def run_traced_assessment(langfuse, session_id, release_data, crew_factory):
    from langfuse import propagate_attributes

    with langfuse.start_as_current_observation(
        as_type="span",
        name="release-risk-assessment",
        input=release_data,
    ) as root_observation:
        with propagate_attributes(
            session_id=session_id,
            metadata={
                "release_name": release_data["release_name"],
                "release_date": release_data["planned_release_date"],
            },
        ):
            result = crew_factory(release_data).kickoff()
        root_observation.update(output=str(result))

    return result


def create_release_crew(release_data):
    import json
    import os

    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is required to run the release assessment.")

    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    llm = LLM(
        model=f"gemini/{model}",
        api_key=os.environ["GEMINI_API_KEY"],
        temperature=0.2,
    )
    evidence = json.dumps(release_data, indent=2)

    release_analyst = Agent(
        role="Release Analyst",
        goal=(
            "Assess release scope, dependencies, deployment risks, and rollback "
            "readiness from the supplied evidence."
        ),
        backstory=(
            "You are an experienced enterprise release analyst. Distinguish "
            "verified evidence from assumptions and call out missing information."
        ),
        llm=llm,
        verbose=True,
    )
    qa_analyst = Agent(
        role="QA Analyst",
        goal=(
            "Evaluate regression completion, test outcomes, defects, and "
            "production quality risk."
        ),
        backstory=(
            "You are a careful software quality engineer. Reconcile test counts "
            "and identify failed or blocked coverage without minimizing it."
        ),
        llm=llm,
        verbose=True,
    )
    security_analyst = Agent(
        role="Security Analyst",
        goal=(
            "Review vulnerability severity and determine production security risk."
        ),
        backstory=(
            "You are an enterprise application security specialist. Treat "
            "unremediated critical and high vulnerabilities as explicit blockers "
            "unless an approved mitigation or exception is documented."
        ),
        llm=llm,
        verbose=True,
    )
    release_manager = Agent(
        role="Release Manager",
        goal=(
            "Consolidate specialist findings into a defensible release decision "
            "of GO, CONDITIONAL GO, or NO-GO."
        ),
        backstory=(
            "You are accountable for production release readiness. Base the "
            "decision on evidence and the specialist assessments, state "
            "uncertainties, and never invent approvals or mitigations."
        ),
        llm=llm,
        verbose=True,
    )

    release_task = Task(
        description=f"""
Review this release evidence:
{evidence}

Assess the release scope, dependency readiness and owners, deployment and
monitoring risks, and rollback availability and test status. Do not assume a
dependency is ready if its status is missing. Report:
1. Release risk: Low, Medium, or High
2. Dependency and deployment risks
3. Rollback assessment
4. Evidence gaps and recommended actions
""",
        expected_output=(
            "A structured release assessment covering risk level, dependencies, "
            "deployment, rollback, evidence gaps, and actions."
        ),
        agent=release_analyst,
    )
    qa_task = Task(
        description=f"""
Review the QA and defect evidence:
{evidence}

Reconcile total/passed/failed/blocked tests, regression completion, and defect
severity. Identify test failures, blocked tests, incomplete regression, and
critical/high defects. Report:
1. QA risk: Low, Medium, or High
2. Key quality concerns
3. Required actions and accountable evidence to obtain
4. Production recommendation
""",
        expected_output=(
            "A structured QA risk assessment with test evidence, defect impact, "
            "actions, and a production recommendation."
        ),
        agent=qa_analyst,
    )
    security_task = Task(
        description=f"""
Review the vulnerability evidence:
{evidence}

Assess critical, high, and medium vulnerabilities. The input contains severity
counts only; do not claim a finding is remediated or exploitable without
supporting details. Report:
1. Security risk: Low, Medium, or High
2. Severity-based production concerns
3. Required remediation, mitigation, or approved exception
4. Production security recommendation
""",
        expected_output=(
            "A structured security risk assessment with severity counts, "
            "limitations, required actions, and a production recommendation."
        ),
        agent=security_analyst,
    )
    decision_task = Task(
        description="""
Consolidate the Release Analyst, QA Analyst, and Security Analyst findings.
Do not invent facts, approvals, owners, or mitigations. Resolve conflicts
conservatively and clearly distinguish facts from assumptions.

Decision guardrails:
- NO-GO when any critical vulnerability or critical defect is open, or when
  specialist evidence identifies an unresolved release-blocking risk.
- CONDITIONAL GO when there are high-severity findings, failed or blocked
  tests, incomplete regression, unverified dependencies, or a rollback plan
  that is missing, untested, or failed; state conditions that must be met
  before deployment.
- GO only when no critical/high blockers remain, testing and dependencies are
  ready, and rollback readiness is demonstrated.
- If the supplied evidence is insufficient to establish readiness, do not
  issue an unconditional GO.

Return a Markdown report with exactly these sections:
1. Management summary
2. Final decision: GO, CONDITIONAL GO, or NO-GO
3. Overall release risk: Low, Medium, or High
4. QA risk: Low, Medium, or High
5. Security risk: Low, Medium, or High
6. Key blockers
7. Recommended actions (include each condition that must be met before release)
8. Evidence gaps and assumptions
""",
        expected_output=(
            "A concise, evidence-based Markdown readiness report containing "
            "all requested risk levels, blockers, actions, decision, and summary."
        ),
        agent=release_manager,
        context=[release_task, qa_task, security_task],
    )

    return Crew(
        agents=[
            release_analyst,
            qa_analyst,
            security_analyst,
            release_manager,
        ],
        tasks=[release_task, qa_task, security_task, decision_task],
        process=Process.sequential,
        verbose=True,
    )
