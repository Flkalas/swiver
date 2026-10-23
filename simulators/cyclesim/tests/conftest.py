"""Pytest defaults — wall limits for CPU sim and per-test timeouts.

Every test must finish within a pytest-timeout budget (see ../pytest.ini).
Long or unbounded CPU loops must also use step caps (``MAX_CPU_STEPS``) and/or
``run_until_halt`` (already wall-bounded via ``_cpu_wall_limit``).

New tests: add ``@pytest.mark.timeout(N)`` when the default 30s is too tight;
never leave an unbounded ``while not runner.halted`` without a step limit.
"""

from __future__ import annotations

import pytest

# Default applied in pytest_collection_modifyitems when a test has no timeout mark.
DEFAULT_TEST_TIMEOUT_S = 30

# Explicit budgets for slow or hang-prone tests (must be >= measured runtime + margin).
TIMEOUT_OVERRIDES_S: dict[str, int] = {
    "test_cupl_recursive_program": 30,
    "test_ttl_recursive_fib": 60,
    "test_fib_upto_250": 120,
    "test_fib_recursive": 15,
    "test_jmp_to_zero": 10,
}


def pytest_configure(config: pytest.Config) -> None:
    if not config.pluginmanager.hasplugin("timeout"):
        msg = (
            "pytest-timeout is required for cyclesim tests. "
            "Install: pip install -r simulators/cyclesim/requirements-dev.txt"
        )
        raise pytest.UsageError(msg)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "timeout" in item.keywords:
            continue
        override = TIMEOUT_OVERRIDES_S.get(item.name)
        if override is not None:
            item.add_marker(pytest.mark.timeout(override))
        else:
            item.add_marker(pytest.mark.timeout(DEFAULT_TEST_TIMEOUT_S))


@pytest.fixture(autouse=True)
def _cpu_wall_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cap ProgramRunner.run_until_halt wall time at 15s per call."""
    from simulators.cyclesim import program

    orig = program.ProgramRunner.run_until_halt

    def bounded(self, max_steps: int = 500, *, wall_s: float = 15.0) -> int:
        return orig(self, max_steps, wall_s=min(wall_s, 15.0))

    monkeypatch.setattr(program.ProgramRunner, "run_until_halt", bounded)
