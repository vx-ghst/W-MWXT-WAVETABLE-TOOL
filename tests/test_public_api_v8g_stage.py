import w_mwxt_wavetable_tool as package
from w_mwxt_wavetable_tool import wavetable


def test_v8g_symbols_are_public_at_both_levels():
    for name in (
        "AdaptiveSlotBudgetPlan",
        "PerceptualProgressPlan",
        "TransitionIntervalDecision",
        "ContinuityRepairReport",
        "CodeV8GAnalysis",
        "build_code_v8g",
    ):
        assert hasattr(package, name)
        assert hasattr(wavetable, name)
