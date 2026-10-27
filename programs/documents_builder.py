# -*- coding: utf-8 -*-
"""Формирование текстовых документов и отчётов из данных и результатов расчётов.

Каждая функция возвращает строку; запись в файлы выполняет главный симулятор.
Ни одно значение здесь не вводится вручную: всё берётся из данных и результатов программ.
"""

import inspect
import os
import zipfile
from xml.sax.saxutils import escape

from programs.common import PROJECT_ROOT  # noqa: F401
from programs import level_calculation, measures_selection

SEPARATOR = "=" * 78
LINE = "-" * 78
LIMITATION = ("Результаты получены по УЧЕБНОЙ матрице и учебной раскладке мер; это не юридическое "
              "заключение о соответствии организации требованиям законодательства.")


def table(headers, rows):
    """Простая текстовая таблица с выравниванием по ширине колонок."""
    rows = [[str(c) for c in row] for row in rows]
    widths = [max(len(str(h)), *(len(r[i]) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)]
    def fmt(cells):
        return " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells))
    return "\n".join([fmt(headers), "-+-".join("-" * w for w in widths)] + [fmt(r) for r in rows])


def _system_by_id(data):
    return {s["id"]: s for s in data["SYSTEMS"]}


def _contours_text(calc):
    lines = []
    for item in calc["contours"]:
        c, r = item["contour"], item["calculation"]
        lines.append("  Контур «%s»: категория=%s, субъекты=%s, количество=%s, тип угроз=%s -> %s"
                     % (c["title"], c.get("pd_category"), c.get("subject_type"), c.get("subject_count"),
                        c.get("threat_type_given"), r["level"]))
        lines.append("    Обоснование: %s" % r["justification"])
        if r["matrix_ground"]:
            lines.append("    Ключ матрицы: %s" % r["matrix_ground"])
    return lines


# ---------------------------------------------------------------- документы

def build_registry(data):
    org = data["ORGANIZATION"]
    out = ["РЕЕСТР ИСПДн", SEPARATOR,
           "Организация: %s (%s, %s)" % (org["title"], org["industry"], org["city"]),
           "Тип организации: %s; признак ГИС в паспорте: %s" % (org["organization_type"], org["has_gis"]),
           "Уникальных субъектов (с учётом пересечений): %s" % org["total_unique_subjects"], ""]
    rows = []
    for s in data["SYSTEMS"]:
        rows.append([s["id"], s["title"], s["pd_category"], s["subject_type"], s["subject_count"],
                     s["threat_type_given"], s["is_gis"], s["declared_level"] or "-", s["responsible"]])
    out.append(table(["Номер", "Название", "Категория ПДн", "Субъекты", "Кол-во", "Угрозы", "ГИС", "Заявл. УЗ", "Ответственный"], rows))
    out.append("")
    out.append("Дополнительные контуры и подробности:")
    for s in data["SYSTEMS"]:
        out += ["", "%s. %s" % (s["id"], s["title"]), "  Назначение: %s" % s["purpose"],
                "  Границы: %s" % s["boundaries"], "  Примеры данных: %s" % s["data_examples"],
                "  Оборудование: %s" % ", ".join(s["linked_equipment"])]
        for extra in s.get("extra_contours", []):
            out.append("  Доп. контур «%s»: %s, %s, %s, угрозы %s" % (extra["title"], extra["pd_category"], extra["subject_type"],
                                                                      extra["subject_count"], extra["threat_type_given"]))
    out += ["", "Пересечения субъектов (не суммируются повторно):"]
    for o in org["subject_overlaps"]:
        out.append("  %s и %s: %d общих - %s" % (o["systems"][0], o["systems"][1], o["shared_count"], o["explanation"]))
    out += ["", "Общие контуры инфраструктуры:"]
    for sc in data["SHARED_CONTOURS"]:
        out.append("  %s (%s): %s - %s" % (sc["id"], sc["title"], ", ".join(sc["systems"]), sc["explanation"]))
    return "\n".join(out) + "\n"


def build_acts(context):
    data, date = context["data"], context["report_date"]
    out = ["АКТЫ ОПРЕДЕЛЕНИЯ УРОВНЕЙ ЗАЩИЩЁННОСТИ (сводный документ)", SEPARATOR, LIMITATION, ""]
    for s in data["SYSTEMS"]:
        calc = context["calculations"][s["id"]]
        declared = s["declared_level"]
        if calc["level"] == level_calculation.INSUFFICIENT:
            discrepancy = "уровень не рассчитан"
        elif not declared:
            discrepancy = "заявленный уровень отсутствует"
        elif declared != calc["level"]:
            discrepancy = "РАСХОЖДЕНИЕ: заявлено %s, рассчитано %s" % (declared, calc["level"])
        else:
            discrepancy = "расхождений нет"
        out += ["Система: %s - %s" % (s["id"], s["title"]), "Входные параметры и расчёт по контурам:"]
        out += _contours_text(calc)
        out += ["Итоговый рассчитанный уровень: %s" % calc["level"], "Объяснение: %s" % calc["explanation"],
                "Прежний заявленный уровень: %s" % (declared or "не присваивался"), "Расхождение: %s" % discrepancy,
                "Дата формирования: %s" % date, LINE]
    for sid, shared in context["shared_contours"].items():
        out += ["Общий контур %s: уровень %s. %s" % (sid, shared["level"], shared["explanation"])]
    return "\n".join(out) + "\n"


def build_equipment_inventory(context):
    data = context["data"]
    rows = [[e["id"], e["title"], e["type"], ", ".join(e["linked_ispdn"]) or "-", "да" if e["processes_pd"] else "нет",
             e["equipment_class"] or "НЕ ЗАПОЛНЕНО", e.get("workstation_component", "-")] for e in data["EQUIPMENT"]]
    out = ["ПЕРЕЧЕНЬ ОБОРУДОВАНИЯ (ОТСС / ВТСС по учебной схеме)", SEPARATOR,
           table(["Номер", "Название", "Тип", "ИСПДн", "ПДн", "Класс", "Компонент АРМ"], rows), "",
           "Обоснования классификации:"]
    out += ["  %s: %s (роль: %s; размещение: %s)" % (e["id"], e["justification"], e["role"], e["location"]) for e in data["EQUIPMENT"]]
    out += ["", "Результат проверки покрытия оборудования:"]
    if not context["equipment_findings"]:
        out.append("  Замечаний нет.")
    for f in context["equipment_findings"]:
        out.append("  [%s] %s / %s: %s. Рекомендация: %s" % (f["severity"], f["equipment"] or "-", f["system"] or "-",
                                                             f["description"], f["recommendation"]))
    return "\n".join(out) + "\n"


def _measure_rows(items):
    return [[m["code"], m["title"], m["inclusion_reason"], m["confirmation_method"]] for m in items]


def build_measures_plan(context):
    data = context["data"]
    out = ["ПЛАН МЕР ЗАЩИТЫ", SEPARATOR, LIMITATION, ""]
    for s in data["SYSTEMS"]:
        m = context["measures"][s["id"]]
        out += ["%s. %s - уровень %s" % (s["id"], s["title"], m["level"])]
        if m["error"]:
            out += ["  " + m["error"], ""]
            continue
        out.append("  Требуется мер: %d; реализовано: %d; пробелов: %d" % (len(m["required"]), len(m["implemented"]), len(m["gaps"])))
        if m["gaps"]:
            out.append("  ПРОБЕЛЫ:")
            out += ["    %s %s - %s (источник: %s)" % (g["code"], g["title"], g["confirmation_method"], g["source"]) for g in m["gaps"]]
        if m["inapplicable"]:
            out.append("  Неприменимые меры (обоснование сохранено):")
            out += ["    %s: %s" % (g["code"], g.get("inapplicability_justification") or "ОБОСНОВАНИЕ ОТСУТСТВУЕТ") for g in m["inapplicable"]]
        if m["clarify"]:
            out.append("  Требуют уточнения условий: " + ", ".join(g["code"] for g in m["clarify"]))
        out.append("")
    out += ["Минимизация данных (учебный пример, все записи вымышленные)", LINE]
    ex = data["MINIMIZATION_EXAMPLE"]
    out += ["Процесс: %s" % ex["process"], "До преобразования:"]
    out += ["  %s" % r for r in ex["before"]]
    out.append("После преобразования:")
    out += ["  %s" % r for r in ex["after"]]
    out += ["Риск повторной идентификации: %s" % ex["reidentification_risk"], "Меры снижения риска: " + "; ".join(ex["measures"])]
    return "\n".join(out) + "\n"


def build_spec(context):
    data = context["data"]
    org = data["ORGANIZATION"]
    out = ["ТЕХНИЧЕСКОЕ ЗАДАНИЕ НА СИСТЕМУ ЗАЩИТЫ ПДн (краткое)", SEPARATOR,
           "Заказчик: %s. Руководитель проекта: %s." % (org["title"], org["project_manager"]),
           "1. Назначение: обеспечить выполнение мер защиты ПДн по рассчитанным уровням для систем: %s."
           % ", ".join("%s (%s)" % (s["id"], context["calculations"][s["id"]]["level"]) for s in data["SYSTEMS"]), "",
           "2. Перечень мер к внедрению (пробелы):"]
    any_gap = False
    for s in data["SYSTEMS"]:
        for g in context["measures"][s["id"]]["gaps"]:
            any_gap = True
            tools = [t["title"] for t in data["PROTECTION_TOOLS"] if g["code"] in t.get("covers_measures", []) and s["id"] in t["linked_system"]]
            out.append("  %s / %s %s; СЗИ/СКЗИ: %s" % (s["id"], g["code"], g["title"], "; ".join(tools) or "организационная мера или средство не определено"))
    if not any_gap:
        out.append("  Пробелов нет.")
    out += ["", "3. Применяемые СЗИ/СКЗИ:"]
    for t in data["PROTECTION_TOOLS"]:
        out.append("  %s %s (%s): %s; статус: %s; источник: %s" % (t["id"], t["title"], t["tool_type"], t["purpose"],
                                                                  t["certificate_or_status"], t["information_source"]))
    out += ["", "4. Этапы внедрения: (1) устранение пробелов с высоким приоритетом; (2) настройка и тестирование;",
            "   (3) опытная эксплуатация; (4) приёмка; (5) подтверждающие документы.",
            "5. Ответственные и сроки: см. план исправлений (documents/remediation_plan.txt).",
            "6. Критерии приёмки: все требуемые меры подтверждены способом проверки из каталога; повторный аудит без несоответствий.",
            "7. Подтверждающие документы: акты определения УЗ, журналы, протоколы проверок, акт классификации ГИС (для ГИС).", "", LIMITATION]
    return "\n".join(out) + "\n"


def build_remediation_plan(plan, audit, context):
    out = ["ПЛАН ПОВЫШЕНИЯ СООТВЕТСТВИЯ (план исправлений)", SEPARATOR,
           "Учебная оценка по результатам аудита: %d из 100 (целевой ориентир: 90 и выше)." % audit["score"],
           "Баллы начисляются только за устранение пробела; наличие документа без устранения пробела оценку не повышает.", ""]
    if not plan:
        out.append("Находок нет.")
    for i, r in enumerate(plan, 1):
        out += ["%d. Несоответствие: %s" % (i, r["violation"]), "   Действие: %s" % r["action"],
                "   Приоритет: %s; ответственный: %s; срок: %s" % (r["priority"], r["responsible"], r["deadline"]),
                "   Зависимость: %s" % r["dependency"], "   Подтверждающий документ: %s" % r["confirming_document"],
                "   Ожидаемый результат: %s" % r["expected_result"], ""]
    return "\n".join(out)


# ---------------------------------------------------------------- отчёты

def build_levels_report(context):
    out = ["ОТЧЁТ ПО УРОВНЯМ ЗАЩИЩЁННОСТИ", SEPARATOR, "Дата: %s" % context["report_date"], LIMITATION, ""]
    rows = [[s["id"], s["pd_category"], s["subject_type"], s["subject_count"], s["threat_type_given"],
             context["calculations"][s["id"]]["level"], s["declared_level"] or "-"] for s in context["data"]["SYSTEMS"]]
    out += [table(["Система", "Категория", "Субъекты", "Кол-во", "Угрозы", "Рассчитано", "Заявлено"], rows), ""]
    for s in context["data"]["SYSTEMS"]:
        calc = context["calculations"][s["id"]]
        out += ["%s: %s" % (s["id"], calc["explanation"])] + _contours_text(calc) + [""]
    for sid, shared in context["shared_contours"].items():
        out.append("Общий контур %s: %s. %s" % (sid, shared["level"], shared["explanation"]))
    return "\n".join(out) + "\n"


def build_measures_report(context):
    out = ["ОТЧЁТ ПО МЕРАМ ЗАЩИТЫ", SEPARATOR, "Дата: %s" % context["report_date"], ""]
    for s in context["data"]["SYSTEMS"]:
        m = context["measures"][s["id"]]
        out += ["%s - %s (%s)" % (s["id"], s["title"], m["level"])]
        out += ["  Требуемые (%d):" % len(m["required"])] + ["    " + ", ".join(x["code"] for x in m["required"])]
        out += ["  Реализованные (%d):" % len(m["implemented"]), "    " + ", ".join(x["code"] for x in m["implemented"])]
        out += ["  Пробелы (%d):" % len(m["gaps"])] + ["    %s: %s" % (x["code"], x["inclusion_reason"]) for x in m["gaps"]]
        out += ["  Неприменимые (%d):" % len(m["inapplicable"])]
        out += ["    %s: %s" % (x["code"], x.get("inapplicability_justification") or "нет обоснования") for x in m["inapplicable"]]
        out += _order17_lines(context, s)
        out.append("")
    return "\n".join(out) + "\n"


def _order17_lines(context, system):
    o17 = context["order_17"].get(system["id"])
    if not o17 or not o17["applicable"]:
        return []
    lines = ["  Приказ ФСТЭК № 17: %s" % o17["summary"]]
    for c in o17["considered"]:
        lines.append("    %s [%s]: %s" % (c["code"], c["status"], c["fact"]))
    return lines


def build_audit_report(audit, context):
    rows = [[c["id"], c["title"], c["status"], c["fact"][:90]] for c in audit["checks"]]
    out = ["ОТЧЁТ АУДИТА СООТВЕТСТВИЯ", SEPARATOR, "Дата: %s" % context["report_date"],
           "Учебная оценка соответствия: %d / 100 (внутренняя метрика проекта, не оценка регулятора)" % audit["score"], "",
           table(["ID", "Проверка", "Статус", "Факт"], rows), "", "Подробности по проверкам:"]
    for c in audit["checks"]:
        out += ["", "%s %s: %s" % (c["id"], c["title"], c["status"]), "  Исходный факт: %s" % c["fact"],
                "  Причина: %s" % c["reason"], "  Рекомендация: %s" % c["recommendation"]]
    out += ["", "Обнаруженные дефекты (%d):" % len(audit["defects"])]
    out += ["  [%s] %s %s: %s" % (d["status"], d["check"], d["obj"], d["fact"]) for d in audit["defects"]]
    return "\n".join(out) + "\n"


def build_final_report(context, audit, plan, recommendations, scenario_results, boundary_results, test_rows):
    data, org = context["data"], context["data"]["ORGANIZATION"]
    out = ["ИТОГОВЫЙ ОТЧЁТ: ОПРЕДЕЛЕНИЕ УРОВНЕЙ ЗАЩИЩЁННОСТИ ИСПДн", SEPARATOR, "Дата формирования: %s" % context["report_date"], LIMITATION, "",
           "1. ОРГАНИЗАЦИЯ", LINE,
           "%s, %s, г. %s, основана в %s. Сотрудников: %s. Уникальных субъектов: %s." % (
               org["title"], org["industry"], org["city"], org["founded_year"], org["employee_count"], org["total_unique_subjects"]),
           "Тип: %s; ГИС: %s. Технологии: %s. Интеграции: %s." % (org["organization_type"], org["has_gis"], org["main_technologies"], org["external_integrations"]),
           "Особенности обработки: %s" % org["processing_features"], "Перечень ИСПДн:"]
    out += ["  %s - %s" % (s["id"], s["title"]) for s in data["SYSTEMS"]]
    out += ["", "2. УРОВНИ ЗАЩИЩЁННОСТИ ПО СИСТЕМАМ", LINE]
    for s in data["SYSTEMS"]:
        calc = context["calculations"][s["id"]]
        out += ["%s %s: итог %s. %s" % (s["id"], s["title"], calc["level"], calc["explanation"])] + _contours_text(calc)
    for sid, shared in context["shared_contours"].items():
        out.append("Общий контур %s: %s. %s" % (sid, shared["level"], shared["explanation"]))
    out += ["", "3. МЕРЫ ЗАЩИТЫ", LINE]
    for s in data["SYSTEMS"]:
        m = context["measures"][s["id"]]
        out.append("%s: требуется %d, реализовано %d, пробелов %d, неприменимых %d (с обоснованием: %d)" % (
            s["id"], len(m["required"]), len(m["implemented"]), len(m["gaps"]), len(m["inapplicable"]),
            sum(1 for x in m["inapplicable"] if x.get("inapplicability_justification"))))
        out += ["    пробел %s: %s" % (g["code"], g["title"]) for g in m["gaps"]]
    out += ["", "4. ОТСС/ВТСС, СЗИ/СКЗИ, ГИС", LINE]
    classes = {}
    for e in data["EQUIPMENT"]:
        classes[e["equipment_class"] or "НЕ ЗАПОЛНЕНО"] = classes.get(e["equipment_class"] or "НЕ ЗАПОЛНЕНО", 0) + 1
    out.append("Оборудование: %d ед.; по классам: %s; замечаний проверки: %d" % (len(data["EQUIPMENT"]), classes, len(context["equipment_findings"])))
    out += ["  СЗИ/СКЗИ: %s" % "; ".join("%s (%s)" % (t["title"], t["tool_type"]) for t in data["PROTECTION_TOOLS"])]
    for s in data["SYSTEMS"]:
        out += _order17_lines(context, s)
    out += ["", "5. РЕЗУЛЬТАТЫ АУДИТА", LINE,
            table(["ID", "Проверка", "Статус"], [[c["id"], c["title"], c["status"]] for c in audit["checks"]]), "",
            "Обнаруженные дефекты:"]
    out += ["  [%s] %s: %s" % (d["status"], d["obj"], d["fact"]) for d in audit["defects"] if d["status"] in ("несоответствие", "замечание")]
    out += ["", "6. УЧЕБНАЯ ОЦЕНКА И ПРИОРИТЕТНЫЕ ДЕЙСТВИЯ", LINE,
            "Оценка соответствия: %d из 100 (внутренняя учебная метрика; цель - 90 и выше)." % audit["score"]]
    for i, r in enumerate(recommendations, 1):
        out.append("  %d. %s | ответственный: %s | срок: %s | основание: %s" % (i, r["action"], r["responsible"], r["deadline"], r["ground"]))
    out += ["", "7. СЦЕНАРИИ, ГРАНИЧНЫЙ ТЕСТ, ТЕСТЫ (см. отдельные отчёты)", LINE]
    out += scenario_summary_lines(scenario_results, boundary_results)
    out.append("Автоматических тестов (по таблице): %d, пройдено: %d" % (len(test_rows), sum(1 for r in test_rows if r[4] == "пройден")))
    out += ["", "8. ПРОВЕРКА НОРМАТИВНЫХ ОСНОВАНИЙ (задание 6.4)", LINE,
            "Сначала приведён результат учебной матрицы; соответствие действующим нормам НЕ подтверждалось автоматически."]
    for r in data["REGULATORY_SOURCES"]:
        out.append("  - %s | для: %s | статус: %s" % (r["document"], r["used_for"], r["verification_status"]))
    out += ["", "9. ВЫВОДЫ (задание 6.5)", LINE] + conclusions(context, audit)
    out += ["", "10. СХЕМА ВЗАИМОСВЯЗЕЙ МОДУЛЕЙ", LINE, MODULE_SCHEME, "",
            "11. ФРАГМЕНТЫ КЛЮЧЕВЫХ ФУНКЦИЙ", LINE, inspect.getsource(level_calculation.size_group),
            inspect.getsource(measures_selection.select_measures)]
    return "\n".join(out) + "\n"


MODULE_SCHEME = """data/*.py (организация, системы, матрица, каталог мер, оборудование, СЗИ/СКЗИ, сценарии)
        |
        v
programs/common.py (загрузка) -> programs/input_validation.py (шаг 2)
        |
        v
programs/pipeline.py: level_calculation (шаг 3) -> measures_selection (шаг 4) -> equipment_check (шаг 5)
        |
        v
programs/compliance_audit.py (шаг 6) -> programs/documents_builder.py (шаг 7) -> documents/, reports/
        ^
programs/main_simulator.py (консольный интерфейс, точка сборки)"""


def scenario_summary_lines(scenario_results, boundary_results):
    lines = ["Сценарии: " + "; ".join("№%s %s -> %s%s" % (r["scenario"]["id"], r["scenario"]["title"], r["level"],
                                                            "" if r["matched_expected"] else " (НЕ СОВПАЛО)") for r in scenario_results)]
    lines.append("Граница 99 999 / 100 000 / 100 001: " + " / ".join("%s -> %s" % (n, r["level"]) for n, r in boundary_results))
    return lines


def conclusions(context, audit):
    data = context["data"]
    levels = ", ".join("%s=%s" % (s["id"], context["calculations"][s["id"]]["level"]) for s in data["SYSTEMS"])
    gaps = [(s["id"], g["code"]) for s in data["SYSTEMS"] for g in context["measures"][s["id"]]["gaps"]]
    auto = [c["id"] for c in audit["checks"] if c["status"] != "недостаточно_данных"]
    manual = [c["title"] for c in audit["checks"] if c["status"] == "недостаточно_данных"]
    return [
        "- Уровни: %s. На результат повлияли категория ПДн, группа субъектов (сотрудники / не сотрудники и порог 100 000) и заданный тип угроз." % levels,
        "- Отсутствующие меры: %s." % (", ".join("%s/%s" % g for g in gaps) or "нет"),
        "- Автоматизированы проверки: %s." % ", ".join(auto),
        "- Ручной проверки специалистом требуют: сверка матрицы и каталога мер с действующими редакциями норм; класс и меры ГИС по приказу № 17 (%s); "
        "статусы сертификатов СЗИ/СКЗИ по реестрам; тип угроз (задан условием); трактовка ровно 100 000 субъектов." % ("; ".join(manual) or "-"),
    ]


def build_scenarios_report(scenario_results, boundary_results):
    out = ["РЕЗУЛЬТАТЫ ШЕСТИ СЦЕНАРИЕВ «ЧТО ЕСЛИ»", SEPARATOR, LIMITATION, ""]
    for r in scenario_results:
        sc = r["scenario"]
        out += ["Сценарий %s. %s" % (sc["id"], sc["title"]), "  Проверяется: %s" % sc["what_is_checked"]]
        for item in r["calculations"]:
            c, res = item["contour"], item["calculation"]
            out += ["  Контур «%s»: %s, %s, %s, угрозы %s -> %s" % (c["title"], c["category"], c["subject_type"], c["count"], c["threat_type"], res["level"]),
                    "    %s" % res["justification"]]
        out += ["  Итог: %s (ожидалось %s: %s). %s" % (r["level"], sc["expected"], "совпало" if r["matched_expected"] else "НЕ СОВПАЛО", r["explanation"]), ""]
    out += ["ГРАНИЧНЫЙ ТЕСТ (одинаковые остальные параметры)", LINE]
    for n, res in boundary_results:
        out += ["  %s субъектов -> %s" % (n, res["level"]), "    %s" % res["justification"]]
    levels = [res["level"] for _, res in boundary_results]
    out.append("Вывод: уровень меняется между 99 999 и 100 000, так как матрица различает группы «менее порога» и «порог и более»; "
               "для 100 000 и 100 001 результат %s. Граница 100 000 отнесена к большой группе (консервативное допущение)."
               % ("одинаков" if levels[1] == levels[2] else "различается"))
    return "\n".join(out) + "\n"


def build_tests_table(test_rows):
    return "\n".join(["ТАБЛИЦА АВТОМАТИЧЕСКИХ ТЕСТОВ", SEPARATOR,
                      table(["№", "Название", "Вход", "Ожидаемый результат", "Статус", "Фактический результат"],
                            [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in test_rows])]) + "\n"


# ---------------------------------------------------------------- формальный акт

def build_formal_act(context, system):
    """Структурированный акт определения уровня защищённости (абзацы для txt/docx)."""
    data, org = context["data"], context["data"]["ORGANIZATION"]
    calc = context["calculations"][system["id"]]
    measures = context["measures"][system["id"]]
    paragraphs = [
        ("АКТ", "title"),
        ("определения уровня защищённости персональных данных при их обработке в информационной системе персональных данных", "title"),
        ("«%s»" % system["title"], "title"),
        ("г. %s                                                                  %s" % (org["city"], context["report_date"]), "text"),
        ("Оператор: %s." % org["title"], "text"),
        ("Комиссия в составе: председатель - %s (ответственный за защиту ПДн); члены - %s (руководитель проекта), %s (ответственный за систему)."
         % (org["pd_protection_officer"], org["project_manager"], system["responsible"]), "text"),
        ("1. Основание", "heading"),
        ("Постановление Правительства РФ от 01.11.2012 № 1119 (пп. 9-12), учебная матрица определения уровней защищённости. Редакция нормы подлежит сверке.", "text"),
        ("2. Общие сведения об ИСПДн", "heading"),
        ("Номер: %s. Назначение: %s. Границы: %s. Признак ГИС: %s." % (system["id"], system["purpose"], system["boundaries"], system["is_gis"]), "text"),
        ("3. Исходные данные и результат расчёта по контурам", "heading"),
    ]
    for item in calc["contours"]:
        c, r = item["contour"], item["calculation"]
        paragraphs.append(("Контур «%s»: категория ПДн - %s; субъекты - %s; количество - %s; тип угроз (задан условием) - %s; уровень - %s. %s"
                           % (c["title"], c.get("pd_category"), c.get("subject_type"), c.get("subject_count"), c.get("threat_type_given"),
                              r["level"], r["justification"]), "text"))
    paragraphs += [
        ("4. Решение комиссии", "heading"),
        ("Для ИСПДн «%s» установить уровень защищённости: %s. %s" % (system["title"], calc["level"], calc["explanation"]), "text"),
        ("Ранее заявленный уровень: %s." % (system["declared_level"] or "не присваивался"), "text"),
        ("5. Необходимые меры", "heading"),
        ("Требуется мер: %d; реализовано: %d; не реализовано: %s." % (len(measures["required"]), len(measures["implemented"]),
                                                                       ", ".join(g["code"] for g in measures["gaps"]) or "нет"), "text"),
    ]
    o17 = context["order_17"].get(system["id"])
    if o17 and o17["applicable"]:
        paragraphs.append(("Приказ ФСТЭК России № 17: %s" % o17["summary"], "text"))
    paragraphs += [
        ("6. Примечание", "heading"),
        (LIMITATION + " Тип угроз принят по условию и не выводился из состава программного обеспечения.", "text"),
        ("Председатель комиссии: ____________ / %s" % org["pd_protection_officer"], "text"),
        ("Члены комиссии: ____________ / %s ; ____________ / %s" % (org["project_manager"], system["responsible"]), "text"),
    ]
    return paragraphs


def formal_act_text(paragraphs):
    return "\n\n".join(text.upper() if kind == "title" else text for text, kind in paragraphs) + "\n"


def write_docx(path, paragraphs):
    """Минимальный .docx без внешних библиотек (заголовки - жирным, по центру)."""
    body = []
    for text, kind in paragraphs:
        props = ""
        if kind == "title":
            props = '<w:pPr><w:jc w:val="center"/></w:pPr>'
        run_props = "<w:rPr><w:b/></w:rPr>" if kind in ("title", "heading") else ""
        body.append('<w:p>%s<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (props, run_props, escape(text)))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>%s</w:body></w:document>' % "".join(body))
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
