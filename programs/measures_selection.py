# -*- coding: utf-8 -*-
"""Подбор мер защиты по уровню, сопоставление с фактическими мерами, проверка приказа № 17."""

from programs.common import PROJECT_ROOT  # noqa: F401

GIS_CLASSES = ("К1", "К2", "К3")


def _describe(measure, reason):
    return {
        "code": measure["code"],
        "title": measure["title"],
        "group": measure["group"],
        "inclusion_reason": reason,
        "confirmation_method": measure["verification"],
        "source": measure["source"],
    }


def select_measures(system, level, measures_catalog):
    """Возвращает словарь со списками: требуемые, реализованные, пробелы (+ неприменимые, уточнить).

    уровень - результат рассчитать_уз / рассчитать_систему (словарь) или строка «УЗ-n».
    """
    level_value = level.get("level") if isinstance(level, dict) else level
    result = {"system": system.get("id"), "level": level_value, "required": [],
                 "implemented": [], "gaps": [], "inapplicable": [], "clarify": [], "error": None}
    allowed_levels = {u_ for m_ in measures_catalog for u_ in m_["levels"]}
    if level_value not in allowed_levels:
        result["error"] = "Уровень %r не определён: меры не подбираются" % (level_value,)
        return result

    actual = set(system.get("actual_measures", []))
    features = system.get("features", {})
    justifications = system.get("inapplicability_justifications", {})
    for measure in measures_catalog:
        if level_value not in measure["levels"]:
            continue
        flag = measure["condition_flag"]
        if flag is None:
            reason = "Обязательная мера для %s (%s)" % (level_value, measure["obligation"])
        else:
            value = features.get(flag)
            if value is None:
                result["clarify"].append(_describe(measure, "Условие «%s» не заполнено в особенностях системы" % flag))
                continue
            if not value:
                record = _describe(measure, "Условие не выполнено: %s" % measure["condition_text"])
                record["inapplicability_justification"] = justifications.get(measure["code"], "")
                result["inapplicable"].append(record)
                continue
            reason = "Условная мера для %s, условие выполнено: %s" % (level_value, measure["condition_text"])
        record = _describe(measure, reason)
        result["required"].append(record)
        (result["implemented"] if measure["code"] in actual else result["gaps"]).append(record)
    return result


def check_order_17(system, grounds):
    """Отдельная проверка применимости приказа № 17 для ГИС (не подменяется приказом № 21)."""
    if system.get("is_gis") != "да":
        return {"system": system.get("id"), "applicable": False, "considered": [],
                "summary": "Система не является ГИС: приказ № 17 не применяется (основание - признак в реестре)."}
    considered = []
    for ground in grounds:
        code = ground["code"]
        if code == "П17-ПРИМЕНИМОСТЬ":
            status, fact = "соответствует", "Признак ГИС = да: применимость приказа № 17 рассмотрена"
        elif code == "П17-КЛАСС":
            equipment_class = system.get("gis_class")
            if equipment_class in GIS_CLASSES:
                status, fact = "соответствует", "Класс ГИС: %s" % equipment_class
            else:
                status, fact = "недостаточно_данных", "Класс ГИС (К1-К3) в данных не задан; не выдумывается"
        else:
            status, fact = "недостаточно_данных", "Состав мер приказа № 17 требует ручной сверки специалистом"
        considered.append({"code": code, "requirement": ground["requirement"], "status": status,
                            "fact": fact, "verification": ground["verification"]})
    return {"system": system.get("id"), "applicable": True, "considered": considered,
            "summary": "Приказ № 17 применим; требуется определить класс и подтвердить набор мер вручную."}
