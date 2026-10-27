# -*- coding: utf-8 -*-
"""Цепочка обработки без вывода и записи файлов: данные -> расчёт -> меры -> оборудование -> аудит."""

import datetime

from programs.common import PROJECT_ROOT  # noqa: F401
from programs.input_validation import validate_input_data, critical_only
from programs.level_calculation import calculate_system, calculate_shared_contour
from programs.measures_selection import select_measures, check_order_17
from programs.equipment_check import check_equipment
from programs.compliance_audit import run_audit, build_remediation_plan, priority_recommendations


def build_context(data, date=None, system_numbers=None):
    """Шаги 2-5 симулятора. Возвращает контекст для аудита и отчётов.

    номера_систем - ограничить расчёт выбранными системами (команда «система»).
    """
    date = date or datetime.date.today()
    errors = validate_input_data(data)
    context = {"data": data, "report_date": date.isoformat(), "data_errors": errors,
                "calculations": {}, "shared_contours": {}, "measures": {}, "order_17": {},
                "equipment_findings": [], "generated": set()}
    if critical_only(errors):
        return context
    systems = [sys_ for sys_ in data["SYSTEMS"] if system_numbers is None or sys_["id"] in system_numbers]
    for sys_ in systems:
        context["calculations"][sys_["id"]] = calculate_system(sys_)
        context["measures"][sys_["id"]] = select_measures(sys_, context["calculations"][sys_["id"]], data["MEASURES_CATALOG"])
        context["order_17"][sys_["id"]] = check_order_17(sys_, data["GIS_GROUNDS"])
    for shared in data["SHARED_CONTOURS"]:
        if all(n_ in context["calculations"] for n_ in shared["systems"]):
            context["shared_contours"][shared["id"]] = calculate_shared_contour(shared, context["calculations"])
    context["equipment_findings"] = check_equipment(data["EQUIPMENT"], systems, data["EQUIPMENT_CLASSES"])
    return context


def perform_audit(context, acts_ready=True):
    """Шаг 6: аудит, план исправлений, приоритеты. Проверка А12 видит план после его построения."""
    data = context["data"]
    date = datetime.date.fromisoformat(context["report_date"])
    if acts_ready:
        context["generated"].add("level_determination_acts")
    preliminary = run_audit(context)
    plan = build_remediation_plan(preliminary, data, date)
    context["generated"].add("remediation_plan")
    audit = run_audit(context)
    # Пересоздаём план по итоговому аудиту (А12 теперь соответствует)
    plan = build_remediation_plan(audit, data, date)
    return audit, plan, priority_recommendations(plan, data, date)
