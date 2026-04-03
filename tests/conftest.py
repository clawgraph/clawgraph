"""Pytest configuration shared across the test suite."""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

settings.register_profile(
    "dev",
    settings(
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    ),
)
settings.register_profile(
    "ci",
    settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    ),
)
settings.register_profile(
    "thorough",
    settings(
        max_examples=500,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    ),
)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))
