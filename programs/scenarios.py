# -*- coding: utf-8 -*-
"""Сценарии «что если», граничный тест и автоматические тесты (общие данные для pytest и отчётов)."""

from programs.common import PROJECT_ROOT, apply_patches, baseline_data  # noqa: F401
from programs.level_calculation import calculate_level, strictest, INSUFFICIENT
from programs.pipeline import build_context, perform_audit


def run_scenario(scenario):
    """Расчёт по каждому контуру сценария и итог по более строгому результату."""
    calculations = []
    for ctx in scenario["contours"]:
        calculations.append({"contour": ctx, "calculation": calculate_level(ctx["category"], ctx["subject_type"], ctx["count"], ctx["threat_type"])})
    levels = [r_["calculation"]["level"] for r_ in calculations]
    total = INSUFFICIENT if INSUFFICIENT in levels else strictest(levels)
    if len(calculations) > 1 and total != INSUFFICIENT:
        determining = [r_["contour"]["title"] for r_ in calculations if r_["calculation"]["level"] == total]
        explanation = ("Общая инфраструктура принимает более строгий результат %s (определяют: %s)%s." % (
            total, ", ".join(determining),
            "; уровни контуров совпали" if len(set(levels)) == 1 else ""))
    else:
        explanation = "Один контур: %s." % total
    return {"scenario": scenario, "calculations": calculations, "level": total, "explanation": explanation,
            "matched_expected": total == scenario["expected"]}


def run_boundary_test(boundary):
    results = []
    for number in boundary["counts"]:
        results.append((number, calculate_level(boundary["category"], boundary["subject_type"], number, boundary["threat_type"])))
    return results


def _error_fields(result):
    return sorted({e.split(":")[0] for e in result["input_errors"]})


def run_test(test, data):
    """Возвращает (фактический_результат_текстом, пройден). Эталонные данные берутся из «данные»."""
    expected = test["expected"]
    if test["kind"] == "calc":
        r_ = calculate_level(*test["input"])
        fields = _error_fields(r_)
        fact = "level=%s" % r_["level"] + (", ошибки в полях: %s" % ", ".join(fields) if fields else "")
        passed = r_["level"] == expected["level"] and ("error_field" not in expected or expected["error_field"] in fields)
        return fact, passed
    baseline = baseline_data(data)
    modified = apply_patches(baseline, test["input"])
    context = build_context(modified)
    audit, _, _ = perform_audit(context)
    statuses = {p_["id"]: p_["status"] for p_ in audit["checks"]}
    if "gap" in expected:
        system, code = expected["gap"]
        codes = [m_["code"] for m_ in context["measures"][system]["gaps"]]
        return "пробелы %s: %s" % (system, ", ".join(codes) or "нет"), code in codes
    if "gis" in expected:
        order17 = context["order_17"][expected["gis"]]
        return "применим=%s, рассмотрено оснований: %d" % (order17["applicable"], len(order17["considered"])), order17["applicable"] and len(order17["considered"]) >= 3
    fact = "%s: %s" % (expected["check"], statuses[expected["check"]])
    return fact, statuses[expected["check"]] == expected["status"]


def describe_input(test):
    if test["kind"] == "calc":
        ctx, t_, ch_, u_ = test["input"]
        return "категория=%r, субъекты=%r, количество=%r, угрозы=%r" % (ctx, t_, ch_, u_)
    return "правки: %s" % ("; ".join("%s %s=%r" % (o_, ".".join(p_), item) for o_, p_, item in test["input"]) or "без правок эталона")


def describe_expectation(test):
    return ", ".join("%s=%s" % (ctx, val) for ctx, val in test["expected"].items())
