# -*- coding: utf-8 -*-
"""Главный симулятор: точка сборки всех артефактов и консольный интерфейс.

Запуск из корня проекта:
    python programs/main_simulator.py            (интерактивный режим)
    python programs/main_simulator.py все        (одна команда и выход)

Команды: все | система <номер> | сценарий <номер> | сценарий импорт [<номер ИСПДн>] | эталон | выход
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from programs import common, scenarios  # noqa: E402
from programs import documents_builder as docs  # noqa: E402
from programs.common import DataError, DOCUMENTS_DIR, REPORTS_DIR, write_file  # noqa: E402
from programs.input_validation import critical_only  # noqa: E402
from programs.pipeline import build_context, perform_audit  # noqa: E402

HELP = "Команды: все | система <номер> | сценарий <номер> | сценарий импорт [<номер ИСПДн>] | эталон | выход"


def say(text=""):
    print(text)


def run_scenarios_and_tests(data):
    scenario_results = [scenarios.run_scenario(s) for s in data["SCENARIOS"]]
    boundary_results = scenarios.run_boundary_test(data["BOUNDARY_TEST"])
    test_rows = []
    for t in data["TESTS"]:
        fact, passed = scenarios.run_test(t, data)
        test_rows.append([t["id"], t["title"], scenarios.describe_input(t), scenarios.describe_expectation(t),
                          "пройден" if passed else "НЕ ПРОЙДЕН", fact])
    return scenario_results, boundary_results, test_rows


def load_and_check(system_numbers=None):
    """Шаги 1-2: загрузка и проверка исходных данных. Возвращает (data, context) или None."""
    say("Шаг 1. Загрузка паспорта, реестра, матрицы, каталога, оборудования, СЗИ/СКЗИ и сценариев...")
    data = common.load_data()
    say("Шаг 2. Проверка обязательных файлов, типов, допустимых значений и идентификаторов...")
    context = build_context(data, datetime.date.today(), system_numbers)
    critical = critical_only(context["data_errors"])
    for e in context["data_errors"]:
        say("  %s %s | поле %s: %s" % ("КРИТИЧНО" if e["critical"] else "замечание", e["file"], e["field"], e["message"]))
    if critical:
        say("Обработка остановлена: исправьте критичные ошибки данных (%d)." % len(critical))
        return None
    return data, context


def write_all_documents(data, context, audit, plan, recommendations):
    scenario_results, boundary_results, test_rows = run_scenarios_and_tests(data)
    docs_out = {
        "ispdn_registry.txt": docs.build_registry(data),
        "level_determination_acts.txt": docs.build_acts(context),
        "equipment_inventory.txt": docs.build_equipment_inventory(context),
        "measures_plan.txt": docs.build_measures_plan(context),
        "pdn_protection_spec.txt": docs.build_spec(context),
        "remediation_plan.txt": docs.build_remediation_plan(plan, audit, context),
    }
    reports_out = {
        "levels_report.txt": docs.build_levels_report(context),
        "measures_report.txt": docs.build_measures_report(context),
        "audit_report.txt": docs.build_audit_report(audit, context),
        "scenarios_results.txt": docs.build_scenarios_report(scenario_results, boundary_results),
        "tests_table.txt": docs.build_tests_table(test_rows),
        "final_report.txt": docs.build_final_report(context, audit, plan, recommendations, scenario_results, boundary_results, test_rows),
    }
    for name, text in docs_out.items():
        write_file(DOCUMENTS_DIR, name, text)
    for name, text in reports_out.items():
        write_file(REPORTS_DIR, name, text)
    for system in data["SYSTEMS"]:
        write_formal_act(context, system)
    baseline = common.baseline_data(data)
    base_context = build_context(baseline, datetime.date.today())
    base_audit, _, _ = perform_audit(base_context)
    write_file(DOCUMENTS_DIR, "baseline_state.txt", build_baseline_note(audit, base_audit))
    return test_rows


def build_baseline_note(audit, base_audit):
    def failing(a):
        return ", ".join("%s (%s)" % (c["id"], c["status"]) for c in a["checks"] if c["status"] != "соответствует") or "нет"
    return "\n".join([
        "ИСХОДНОЕ СОСТОЯНИЕ И КОНТРОЛЬНЫЕ НЕСООТВЕТСТВИЯ (задание 1.3)", "=" * 78,
        "Эталон (до внесения дефектов): оценка %d, проверки не в статусе «соответствует»: %s." % (base_audit["score"], failing(base_audit)),
        "Текущие данные (с тремя дефектами): оценка %d, проверки не в статусе «соответствует»: %s." % (audit["score"], failing(audit)),
        "Внесённые дефекты: (1) заявленный УЗ не равен расчётному; (2) у оборудования не заполнена классификация ОТСС/ВТСС;",
        "(3) в фактических мерах системы нет требуемой меры. Аудитор находит их общими правилами (проверки A04, A07, A08),",
        "без перечня заранее известных идентификаторов. Правки эталона описаны в BASELINE_FIXES (data/test_scenarios.py).", ""])


def write_formal_act(context, system):
    paragraphs = docs.build_formal_act(context, system)
    base = os.path.join(DOCUMENTS_DIR, "acts")
    stem = "act_" + system["id"].replace("ИСПДн-", "ispdn_")
    write_file(base, stem + ".txt", docs.formal_act_text(paragraphs))
    docs.write_docx(os.path.join(base, stem + ".docx"), paragraphs)
    return os.path.join(base, stem)


def command_all():
    loaded = load_and_check()
    if loaded is None:
        return
    data, context = loaded
    say("Шаг 3. Расчёт уровней и акты определения УЗ:")
    for s in data["SYSTEMS"]:
        say("  %s -> %s" % (s["id"], context["calculations"][s["id"]]["level"]))
    say("Шаг 4. Подбор мер, сопоставление с реализованными, пробелы:")
    for s in data["SYSTEMS"]:
        m = context["measures"][s["id"]]
        say("  %s: требуется %d, реализовано %d, пробелов %d" % (s["id"], len(m["required"]), len(m["implemented"]), len(m["gaps"])))
    say("Шаг 5. Проверка оборудования и СЗИ/СКЗИ; применимость приказа № 17:")
    say("  замечаний по оборудованию: %d" % len(context["equipment_findings"]))
    for sid, o17 in context["order_17"].items():
        if o17["applicable"]:
            say("  %s (ГИС): %s" % (sid, o17["summary"]))
    say("Шаг 6. Аудит и учебная оценка:")
    audit, plan, recommendations = perform_audit(context)
    for c in audit["checks"]:
        say("  %s %-22s %s" % (c["id"], c["status"], c["title"]))
    say("  Учебная оценка соответствия: %d / 100" % audit["score"])
    say("Шаг 7. Формирование документов и отчётов...")
    write_all_documents(data, context, audit, plan, recommendations)
    say("Готово: documents/, reports/ (итоговый отчёт - reports/final_report.txt).")
    say("Приоритетные действия:")
    for i, r in enumerate(recommendations, 1):
        say("  %d. %s | %s (ответственный: %s, срок: %s)" % (i, r["action"], r["ground"], r["responsible"], r["deadline"]))


def normalize_system_id(raw, data):
    ids = [s["id"] for s in data["SYSTEMS"]]
    if raw in ids:
        return raw
    if raw.isdigit():
        candidate = "ИСПДн-%02d" % int(raw)
        if candidate in ids:
            return candidate
    return None


def command_system(argument):
    if not argument:
        say("Не указан номер системы. Пример: система 1. Доступные: " + ", ".join(s["id"] for s in common.load_data()["SYSTEMS"]))
        return
    data = common.load_data()
    system_id = normalize_system_id(argument, data)
    if system_id is None:
        say("Система %r не найдена." % argument)
        return
    loaded = load_and_check([system_id])
    if loaded is None:
        return
    data, context = loaded
    system = next(s for s in data["SYSTEMS"] if s["id"] == system_id)
    calc = context["calculations"][system_id]
    say("%s - %s" % (system_id, system["title"]))
    for line in docs._contours_text(calc):
        say(line)
    say("Итог: %s. %s" % (calc["level"], calc["explanation"]))
    m = context["measures"][system_id]
    say("Меры: требуется %d, реализовано %d, пробелов %d" % (len(m["required"]), len(m["implemented"]), len(m["gaps"])))
    for g in m["gaps"]:
        say("  пробел %s %s" % (g["code"], g["title"]))
    for f in context["equipment_findings"]:
        if f["system"] == system_id or (f["equipment"] in system["linked_equipment"]):
            say("  оборудование %s: %s" % (f["equipment"], f["description"]))
    for line in docs._order17_lines(context, system):
        say(line)


def command_scenario(argument):
    data = common.load_data()
    parts = argument.split()
    if parts and parts[0] == "импорт":
        command_import(parts[1] if len(parts) > 1 else "")
        return
    if not parts or not parts[0].isdigit():
        say("Не указан номер сценария (1-%d) или слово «импорт»." % len(data["SCENARIOS"]))
        return
    chosen = [s for s in data["SCENARIOS"] if s["id"] == int(parts[0])]
    if not chosen:
        say("Сценария %s нет." % parts[0])
        return
    result = scenarios.run_scenario(chosen[0])
    say("Сценарий %s. %s: %s" % (chosen[0]["id"], chosen[0]["title"], chosen[0]["what_is_checked"]))
    for item in result["calculations"]:
        say("  %s: %s" % (item["contour"]["title"], item["calculation"]["justification"]))
    say("Итог: %s (ожидалось %s). %s" % (result["level"], chosen[0]["expected"], result["explanation"]))


def command_import(argument):
    data = common.load_data()
    if not argument:
        say("Не указан номер ИСПДн для акта. Пример: сценарий импорт 1. Доступные: " + ", ".join(s["id"] for s in data["SYSTEMS"]))
        return
    system_id = normalize_system_id(argument, data)
    if system_id is None:
        say("Система %r не найдена." % argument)
        return
    loaded = load_and_check()
    if loaded is None:
        return
    data, context = loaded
    system = next(s for s in data["SYSTEMS"] if s["id"] == system_id)
    path = write_formal_act(context, system)
    say("Акт определения уровня защищённости сформирован: %s.txt и %s.docx" % (path, path))


def command_baseline():
    data = common.load_data()
    context = build_context(common.baseline_data(data), datetime.date.today())
    audit, _, _ = perform_audit(context)
    say("Эталонное состояние (без трёх дефектов): оценка %d / 100" % audit["score"])
    for c in audit["checks"]:
        say("  %s %-22s %s" % (c["id"], c["status"], c["title"]))


def dispatch(line):
    parts = line.strip().split(None, 1)
    if not parts:
        return True
    command, argument = parts[0].lower(), (parts[1] if len(parts) > 1 else "")
    if command in ("выход", "exit", "quit"):
        return False
    if command in ("все", "all"):
        command_all()
    elif command in ("система", "system"):
        command_system(argument.strip())
    elif command in ("сценарий", "scenario"):
        command_scenario(argument.strip())
    elif command in ("эталон", "baseline"):
        command_baseline()
    else:
        say("Неизвестная команда. " + HELP)
    return True


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if argv:
            dispatch(" ".join(argv))
            return 0
        say(HELP)
        while True:
            try:
                line = input("> ")
            except EOFError:
                return 0
            if not dispatch(line):
                return 0
    except DataError as error:
        say("Ошибка данных: %s" % error)
        return 1
    except (KeyError, TypeError, ValueError) as error:
        say("Ошибка обработки данных (%s: %s). Проверьте файлы в data/." % (type(error).__name__, error))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
