import copy

import pytest

from data import test_scenarios
from programs import scenarios
from programs.common import apply_patches
from programs.level_calculation import calculate_level, INSUFFICIENT
from programs.pipeline import build_context, perform_audit
from programs.equipment_check import check_equipment


@pytest.mark.parametrize("test", test_scenarios.TESTS, ids=lambda t: "test_%s" % t["id"])
def test_documented_case(test, data):
    """Каждый случай из таблицы тестов: вход, ожидаемый и фактический результат."""
    fact, passed = scenarios.run_test(test, data)
    assert passed, fact


@pytest.mark.parametrize("scenario", test_scenarios.SCENARIOS, ids=lambda s: "scenario_%s" % s["id"])
def test_six_scenarios(scenario):
    result = scenarios.run_scenario(scenario)
    assert result["level"] == scenario["expected"]


def test_boundary_levels_and_explanations_differ():
    results = scenarios.run_boundary_test(test_scenarios.BOUNDARY_TEST)
    levels = [r["level"] for _, r in results]
    assert levels == ["УЗ-2", "УЗ-1", "УЗ-1"]
    assert results[0][1]["justification"] != results[1][1]["justification"]


def test_all_four_results_and_error_status_are_reachable():
    got = {calculate_level("иные", "не_сотрудники", 10, 3)["level"],
           calculate_level("общедоступные", "не_сотрудники", 10, 2)["level"],
           calculate_level("биометрические", "сотрудники", 10, 2)["level"],
           calculate_level("специальные", "сотрудники", 10, 1)["level"]}
    assert got == {"УЗ-1", "УЗ-2", "УЗ-3", "УЗ-4"}
    assert calculate_level(None, None, None, None)["level"] == INSUFFICIENT


def test_calculation_never_raises_on_garbage():
    result = calculate_level(object(), 5, "много", True)
    assert result["level"] == INSUFFICIENT and result["input_errors"]


def test_boolean_count_is_rejected():
    assert calculate_level("иные", "не_сотрудники", True, 2)["level"] == INSUFFICIENT


def test_three_seeded_defects_found_by_general_rules(data):
    audit, plan, recs = perform_audit(build_context(data))
    failed = {c["id"] for c in audit["checks"] if c["status"] == "несоответствие"}
    assert failed == {"A04", "A07", "A08"}
    assert 3 <= len(recs) <= 5


def test_baseline_has_no_noncompliance_and_reaches_target(baseline):
    audit, _, _ = perform_audit(build_context(baseline))
    assert all(c["status"] != "несоответствие" for c in audit["checks"])
    assert audit["score"] >= 90


def test_shared_contour_takes_strictest_level(data):
    context = build_context(data)
    shared = context["shared_contours"]["КОНТУР-ЦОД"]
    assert shared["level"] == "УЗ-2"


def test_multi_contour_system_uses_stricter_result(data):
    calc = build_context(data)["calculations"]["ИСПДн-01"]
    assert [c["calculation"]["level"] for c in calc["contours"]] == ["УЗ-2", "УЗ-3"]
    assert calc["level"] == "УЗ-2"


def test_equipment_without_system_link_is_reported(data):
    equipment = [dict(data["EQUIPMENT"][0], linked_ispdn=[])]
    kinds = {f["kind"] for f in check_equipment(equipment, data["SYSTEMS"])}
    assert "нет_связи" in kinds


def test_ups_as_workstation_component_is_not_a_contradiction(data):
    findings = check_equipment(data["EQUIPMENT"], data["SYSTEMS"])
    assert not [f for f in findings if f["equipment"] == "ОБ-09" and f["kind"] == "противоречие"]


def test_gis_system_has_order_17_review(data):
    context = build_context(data)
    assert context["order_17"]["ИСПДн-05"]["applicable"]
    assert not context["order_17"]["ИСПДн-01"]["applicable"]


def test_inapplicable_measure_keeps_justification(data):
    context = build_context(data)
    inapplicable = {m["code"]: m for m in context["measures"]["ИСПДн-02"]["inapplicable"]}
    assert inapplicable["ЗНИ.1"]["inapplicability_justification"]


def test_missing_justification_is_flagged(baseline):
    broken = apply_patches(baseline, [("set_op", ["systems", "ИСПДн-02", "inapplicability_justifications"], {})])
    audit, _, _ = perform_audit(build_context(broken))
    assert {c["id"]: c["status"] for c in audit["checks"]}["A11"] == "несоответствие"


def test_headcount_mismatch_is_flagged(baseline):
    broken = copy.deepcopy(baseline)
    broken["ORGANIZATION"]["total_unique_subjects"] += 1
    audit, _, _ = perform_audit(build_context(broken))
    assert {c["id"]: c["status"] for c in audit["checks"]}["A03"] == "несоответствие"
