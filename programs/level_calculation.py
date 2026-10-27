# -*- coding: utf-8 -*-
"""Расчёт уровня защищённости по учебной матрице (data/level_matrix.py)."""

import copy

from programs.common import PROJECT_ROOT  # noqa: F401  (добавляет корень проекта в sys.path)
from data import level_matrix as m_

INSUFFICIENT = "недостаточно_данных"


def _is_valid_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def size_group(subject_type, count):
    """Группа численности по матрице: малая / большая."""
    if subject_type == "сотрудники":
        return m_.GROUP_SMALL
    if m_.THRESHOLD_IN_LARGE_GROUP:
        reached = count >= m_.SUBJECT_THRESHOLD
    else:
        reached = count > m_.SUBJECT_THRESHOLD
    return m_.GROUP_LARGE if reached else m_.GROUP_SMALL


def calculate_level(category, subject_type, count, threat_type):
    """Возвращает словарь: уровень, обоснование, проверенные_параметры, основание_матрицы, ошибки_ввода.

    Не угадывает результат и не вызывает исключений при неверном вводе.
    """
    params = {"category": category, "subject_type": subject_type,
                 "count": count, "threat_type": threat_type}
    errors = []
    if category in (None, ""):
        errors.append("category: значение не задано")
    elif category not in m_.PD_CATEGORIES:
        errors.append("category: недопустимое значение %r (допустимо: %s)" % (category, ", ".join(m_.PD_CATEGORIES)))
    if subject_type in (None, ""):
        errors.append("subject_type: значение не задано")
    elif subject_type not in m_.SUBJECT_TYPES:
        errors.append("subject_type: недопустимое значение %r (допустимо: %s)" % (subject_type, ", ".join(m_.SUBJECT_TYPES)))
    if count is None or count == "":
        errors.append("count: значение не задано")
    elif not _is_valid_count(count):
        errors.append("count: нужно целое положительное число, получено %r" % (count,))
    if threat_type is None or threat_type == "":
        errors.append("threat_type: значение не задано")
    elif isinstance(threat_type, bool) or threat_type not in m_.THREAT_TYPES:
        errors.append("threat_type: недопустимое значение %r (допустимо: 1, 2, 3)" % (threat_type,))

    result = {
        "level": INSUFFICIENT,
        "justification": "",
        "checked_params": copy.deepcopy(params),
        "matrix_ground": None,
        "input_errors": errors,
    }
    if errors:
        result["justification"] = "Уровень не определён: " + "; ".join(errors)
        return result

    group = size_group(subject_type, count)
    key = (category, group, threat_type)
    record = m_.LEVEL_MATRIX.get(key)
    if record is None:
        result["input_errors"].append("matrix: нет правила для сочетания %r" % (key,))
        result["justification"] = "Уровень не определён: в матрице нет правила для %r" % (key,)
        return result

    if subject_type == "сотрудники":
        group_explanation = "субъекты - сотрудники оператора, порог %d не применяется" % m_.SUBJECT_THRESHOLD
    elif group == m_.GROUP_LARGE:
        group_explanation = "не сотрудники, %d >= порога %d (граница отнесена к большой группе)" % (count, m_.SUBJECT_THRESHOLD)
    else:
        group_explanation = "не сотрудники, %d < порога %d" % (count, m_.SUBJECT_THRESHOLD)
    result["level"] = record["level"]
    result["matrix_ground"] = "%s|%s|%d" % key
    result["justification"] = "Категория «%s», %s, тип угроз %d -> %s по правилу: %s" % (
        category, group_explanation, threat_type, record["level"], record["ground"])
    return result


def strictest(levels):
    """Самый строгий из списка УЗ (УЗ-1 строже УЗ-4); None, если допустимых нет."""
    valid_levels = [u_ for u_ in levels if u_ in m_.LEVELS]
    return min(valid_levels, key=m_.LEVELS.index) if valid_levels else None


def system_contours(system):
    """Основной контур записи и дополнительные - в едином формате расчётных записей."""
    main_contour = {
        "title": "Основной контур",
        "pd_category": system.get("pd_category"),
        "subject_type": system.get("subject_type"),
        "subject_count": system.get("subject_count"),
        "threat_type_given": system.get("threat_type_given"),
    }
    return [main_contour] + list(system.get("extra_contours", []))


def calculate_system(system):
    """Расчёт по каждому контуру системы и итог по более строгому результату."""
    calculations = []
    for contour in system_contours(system):
        result = calculate_level(contour.get("pd_category"), contour.get("subject_type"),
                                  contour.get("subject_count"), contour.get("threat_type_given"))
        calculations.append({"contour": contour, "calculation": result})
    levels = [r_["calculation"]["level"] for r_ in calculations]
    if any(u_ == INSUFFICIENT for u_ in levels):
        total = INSUFFICIENT
        explanation = "Хотя бы один контур не рассчитан (недостаточно данных), общий уровень не определяется."
    else:
        total = strictest(levels)
        if len(calculations) == 1:
            explanation = "Один контур обработки: %s." % total
        else:
            strictest_names = [r_["contour"]["title"] for r_ in calculations if r_["calculation"]["level"] == total]
            explanation = ("Контуров: %d. Для системы принят более строгий результат %s (определяют: %s): "
                         "один набор мер защищает все данные контура." % (len(calculations), total, ", ".join(strictest_names)))
    return {"id": system.get("id"), "contours": calculations, "level": total, "explanation": explanation}


def calculate_shared_contour(shared_contour, system_calculations):
    """Уровень общей инфраструктуры - по наиболее строгому УЗ входящих систем."""
    levels = {n_: system_calculations[n_]["level"] for n_ in shared_contour["systems"] if n_ in system_calculations}
    total = strictest(list(levels.values()))
    if total is None or any(u_ == INSUFFICIENT for u_ in levels.values()):
        return {"id": shared_contour["id"], "level": INSUFFICIENT, "by_system": levels,
                "explanation": "Не у всех систем контура определён уровень."}
    determining = [n_ for n_, u_ in levels.items() if u_ == total]
    return {"id": shared_contour["id"], "level": total, "by_system": levels,
            "explanation": "Общий контур принимает наиболее строгий уровень %s (определяют: %s)." % (total, ", ".join(determining))}
