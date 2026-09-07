from fenrys.policy import BudgetController
from fenrys.scope import ScopeChecker


def test_scope_and_budget():
    scope = ScopeChecker({"targets": ["example.test"], "cidrs": ["10.0.0.0/8"]})
    assert scope.is_allowed("example.test")
    assert scope.is_allowed("10.10.1.2")
    assert not scope.is_allowed("outside.test")
    budget = BudgetController({"max_tool_calls_per_task": 1, "max_total_tool_calls_per_session": 2})
    assert budget.allow_tool_call()[0]
    budget.record_tool_call(True)
    assert not budget.allow_tool_call()[0]


def test_scope_case_and_whitespace_insensitive():
    scope = ScopeChecker({"targets": ["Example.TEST"], "cidrs": [], "hostnames": [], "urls": []})
    assert scope.is_allowed("  example.test  ")
    assert scope.is_allowed("EXAMPLE.TEST")


def test_scope_host_port_without_scheme():
    scope = ScopeChecker({"targets": [], "cidrs": ["10.0.0.0/8"], "hostnames": [], "urls": []})
    assert scope.is_allowed("10.0.0.5:445")
    assert not scope.is_allowed("192.168.1.5:445")


def test_scope_cidr_as_target():
    scope = ScopeChecker({"targets": [], "cidrs": ["10.0.0.0/8"], "hostnames": [], "urls": []})
    assert scope.is_allowed("10.1.0.0/16")
    assert not scope.is_allowed("192.168.0.0/16")


def test_scope_same_host_url_matching():
    scope = ScopeChecker({"targets": [], "cidrs": [], "hostnames": [],
                          "urls": ["http://u/x"]})
    assert scope.is_allowed("http://u/other")
    assert scope.is_allowed("u")
    assert not scope.is_allowed("http://other/x")


def test_scope_invalid_cidr_no_crash_fail_closed():
    scope = ScopeChecker({"targets": ["example.test"], "cidrs": ["not-a-cidr"], "hostnames": [], "urls": []})
    assert scope.is_allowed("example.test")
    assert not scope.is_allowed("outside.test")
    assert not scope.is_allowed("")


async def test_budget_parallel_claims_hold_cap():
    import asyncio
    budget = BudgetController({"max_tool_calls_per_task": 3,
                               "max_total_tool_calls_per_session": 100,
                               "max_wallclock_per_task_seconds": 900,
                               "max_same_tool_same_target_retries": 100})
    results = await asyncio.gather(*[budget.claim("t", f"target-{i}") for i in range(10)])
    assert sum(1 for ok, _ in results if ok) == 3
    assert budget.tool_calls == 3
