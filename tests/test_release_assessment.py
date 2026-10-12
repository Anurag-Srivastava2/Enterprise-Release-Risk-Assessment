import contextlib
import os
import unittest
from unittest.mock import patch

import langfuse

from release_assessment import (
    build_release_data,
    create_release_crew,
    run_traced_assessment,
    validate_release_data,
)


def sample_values():
    return {
        "release_name": "Customer Platform v4.2",
        "planned_release_date": "2026-10-19",
        "release_scope": "Payment API enhancement and database schema update",
        "dependencies": "Payment Gateway; Identity Service; Customer Database",
        "deployment_risks": "Validate schema migration and monitor error rates",
        "total_tests": 520,
        "passed_tests": 505,
        "failed_tests": 10,
        "blocked_tests": 5,
        "regression_completion": 97,
        "critical_defects": 0,
        "high_defects": 2,
        "medium_defects": 7,
        "low_defects": 15,
        "critical_vulnerabilities": 0,
        "high_vulnerabilities": 1,
        "medium_vulnerabilities": 3,
        "rollback_available": "Available",
        "rollback_tested": "Tested successfully",
    }


class ReleaseAssessmentTests(unittest.TestCase):
    def test_builds_valid_release_data(self):
        release_data = build_release_data(**sample_values())

        self.assertEqual(validate_release_data(release_data), [])
        self.assertEqual(release_data["qa"]["passed"], 505)
        self.assertEqual(
            release_data["security"]["vulnerabilities"]["high"],
            1,
        )

    def test_rejects_test_count_mismatch(self):
        values = sample_values()
        values["blocked_tests"] = 4

        errors = validate_release_data(build_release_data(**values))

        self.assertTrue(any("must sum to the total" in error for error in errors))

    def test_rejects_missing_scope_and_negative_counts(self):
        values = sample_values()
        values["release_scope"] = " "
        values["critical_defects"] = -1

        errors = validate_release_data(build_release_data(**values))

        self.assertTrue(any("scope and changes" in error for error in errors))
        self.assertTrue(any("cannot be negative" in error for error in errors))

    def test_creates_four_specialist_and_manager_tasks(self):
        release_data = build_release_data(**sample_values())
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            crew = create_release_crew(release_data)

        self.assertEqual(
            [agent.role for agent in crew.agents],
            [
                "Release Analyst",
                "QA Analyst",
                "Security Analyst",
                "Release Manager",
            ],
        )
        self.assertEqual(len(crew.tasks), 4)
        self.assertEqual(crew.tasks[-1].agent.role, "Release Manager")
        self.assertIn("NO-GO", crew.tasks[-1].description)
        self.assertIn("CONDITIONAL GO", crew.tasks[-1].description)

    def test_traced_run_sets_root_io_and_propagates_session(self):
        observations = []
        propagated = []

        class RootObservation:
            def update(self, **kwargs):
                observations.append(("update", kwargs))

        class FakeLangfuse:
            @contextlib.contextmanager
            def start_as_current_observation(self, **kwargs):
                observations.append(("start", kwargs))
                yield RootObservation()

        class FakeCrew:
            def kickoff(self):
                return "Final readiness report"

        @contextlib.contextmanager
        def fake_propagate_attributes(**kwargs):
            propagated.append(kwargs)
            yield

        release_data = build_release_data(**sample_values())
        with patch.object(langfuse, "propagate_attributes", fake_propagate_attributes):
            result = run_traced_assessment(
                FakeLangfuse(),
                "session-123",
                release_data,
                lambda _data: FakeCrew(),
            )

        self.assertEqual(result, "Final readiness report")
        self.assertEqual(observations[0][0], "start")
        self.assertEqual(observations[0][1]["input"], release_data)
        self.assertEqual(
            propagated,
            [
                {
                    "session_id": "session-123",
                    "metadata": {
                        "release_name": "Customer Platform v4.2",
                        "release_date": "2026-10-19",
                    },
                }
            ],
        )
        self.assertEqual(
            observations[1],
            ("update", {"output": "Final readiness report"}),
        )


if __name__ == "__main__":
    unittest.main()
