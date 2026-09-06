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
