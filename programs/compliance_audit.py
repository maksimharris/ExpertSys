# -*- coding: utf-8 -*-
"""Аудит соответствия: 12 автоматических проверок, учебная оценка 0-100, план исправлений.

Проверки работают общими правилами по данным (сравнения и валидация), без заранее
известных идентификаторов дефектов.
"""

import datetime

from programs.common import PROJECT_ROOT  # noqa: F401
from programs.level_calculation import calculate_level, INSUFFICIENT

COMPLIANT = "соответствует"
REMARK = "замечание"
NONCOMPLIANCE = "несоответствие"
INSUFFICIENT_DATA = "недостаточно_данных"

# Баллы статуса для учебной оценки (внутренняя метрика, не оценка регулятора).
STATUS_SCORES = {COMPLIANT: 100, REMARK: 60, INSUFFICIENT_DATA: 50, NONCOMPLIANCE: 0}
SEVERITY_ORDER = [NONCOMPLIANCE, INSUFFICIENT_DATA, REMARK, COMPLIANT]
PRIORITY_BY_STATUS = {NONCOMPLIANCE: "высокий", INSUFFICIENT_DATA: "средний", REMARK: "низкий"}
DEADLINE_DAYS = {"высокий": 14, "средний": 30, "низкий": 60}


def _finding(status, obj, fact, reason, recommendation, system=None, document="", expected="", dependency="-"):
    return {"status": status, "obj": obj, "system": system, "fact": fact, "reason": reason,
            "recommendation": recommendation, "document": document, "expected": expected, "dependency": dependency}


def _check(check_id, title, findings, summary_if_clean):
    status = COMPLIANT
    for n_ in findings:
        if SEVERITY_ORDER.index(n_["status"]) < SEVERITY_ORDER.index(status):
            status = n_["status"]
    if findings:
        fact = "; ".join("%s: %s" % (n_["obj"], n_["fact"]) for n_ in findings)
        reason = findings[0]["reason"] if len(findings) == 1 else "Выявлено замечаний: %d" % len(findings)
        recommendation = "; ".join(sorted({n_["recommendation"] for n_ in findings}))
    else:
        fact, reason, recommendation = summary_if_clean, "Отклонений не выявлено", "-"
    return {"id": check_id, "title": title, "status": status, "fact": fact,
            "reason": reason, "recommendation": recommendation, "findings": findings}


# ----------------------------------------------------------------- отдельные проверки

def _check_a01_completeness(ctx):
    findings = []
    for o_ in ctx["data_errors"]:
        status = NONCOMPLIANCE if o_["critical"] else REMARK
        findings.append(_finding(status, o_["field"], "%s (%s)" % (o_["message"], o_["file"]),
                                "Нарушена полнота или формат данных", "Исправить поле в файле данных",
                                document=o_["file"], expected="Данные проходят проверку исходных данных"))
    return _check("A01", "Полнота паспорта и реестра ИСПДн", findings,
                     "Обязательные поля паспорта и реестра заполнены, идентификаторы уникальны")


def _check_a02_validity(ctx):
    findings = []
    for sys_ in ctx["data"]["SYSTEMS"]:
        for p_ in ctx["calculations"][sys_["id"]]["contours"]:
            for error in p_["calculation"]["input_errors"]:
                findings.append(_finding(INSUFFICIENT_DATA, "%s / %s" % (sys_["id"], p_["contour"]["title"]), error,
                                        "Параметр недопустим или не задан - уровень не рассчитывается",
                                        "Задать допустимое значение параметра", system=sys_["id"],
                                        document="data/systems.py", expected="Уровень рассчитывается без ошибок ввода"))
    return _check("A02", "Допустимость категории, группы субъектов, количества и типа угроз", findings,
                     "Все контуры имеют допустимые параметры расчёта")


def _check_a03_subject_counts(ctx):
    d = ctx["data"]
    org, systems = d["ORGANIZATION"], d["SYSTEMS"]
    findings = []
    sums = {}
    for sys_ in systems:
        sums[sys_["id"]] = sum(
            (p_["contour"].get("subject_count") or 0) for p_ in ctx["calculations"][sys_["id"]]["contours"]
            if isinstance(p_["contour"].get("subject_count"), int))
        if sys_.get("subject_type") == "сотрудники" and isinstance(sys_.get("subject_count"), int) \
                and isinstance(org.get("employee_count"), int) and sys_["subject_count"] > org["employee_count"]:
            findings.append(_finding(NONCOMPLIANCE, sys_["id"], "сотрудников в системе %d больше штата %d" % (sys_["subject_count"], org["employee_count"]),
                                    "Численность сотрудников не согласуется", "Привести число сотрудников в соответствие",
                                    system=sys_["id"], document="data/organization.py"))
    repeats = 0
    for p_ in org.get("subject_overlaps", []):
        a_, b_ = p_["systems"]
        if a_ not in sums or b_ not in sums:
            findings.append(_finding(NONCOMPLIANCE, "пересечение %s/%s" % (a_, b_), "ссылка на несуществующую систему",
                                    "Пересечение описано некорректно", "Исправить идентификаторы в пересечениях"))
            continue
        if p_["shared_count"] > min(sums[a_], sums[b_]):
            findings.append(_finding(NONCOMPLIANCE, "пересечение %s/%s" % (a_, b_), "общих субъектов %d больше численности одной из систем" % p_["shared_count"],
                                    "Пересечение превышает численность системы", "Уточнить число общих субъектов"))
        repeats += p_["shared_count"]
    expected_total = sum(sums.values()) - repeats
    if org.get("total_unique_subjects") != expected_total:
        findings.append(_finding(NONCOMPLIANCE, "ORGANIZATION.total_unique_subjects",
                                "в паспорте %s, по реестру %d (сумма %d минус повторные учёты %d)" % (org.get("total_unique_subjects"), expected_total, sum(sums.values()), repeats),
                                "Общее число уникальных субъектов не согласуется с реестром", "Пересчитать число уникальных субъектов",
                                document="data/organization.py", expected="Число уникальных субъектов совпадает с реестром"))
    return _check("A03", "Согласованность численности в паспорте и реестре", findings,
                     "Уникальных субъектов %d = сумма по контурам минус повторные учёты" % expected_total)


def _check_a04_declared_level(ctx):
    findings = []
    for sys_ in ctx["data"]["SYSTEMS"]:
        calculated = ctx["calculations"][sys_["id"]]["level"]
        declared = sys_.get("declared_level")
        if calculated == INSUFFICIENT:
            findings.append(_finding(INSUFFICIENT_DATA, sys_["id"], "уровень не рассчитан", "Нет данных для расчёта",
                                    "Заполнить параметры расчёта", system=sys_["id"]))
        elif not declared:
            findings.append(_finding(REMARK, sys_["id"], "заявленный уровень не присвоен, расчёт даёт %s" % calculated,
                                    "Уровень организацией не фиксировался", "Утвердить уровень актом", system=sys_["id"],
                                    document="Акт определения УЗ"))
        elif declared != calculated:
            findings.append(_finding(NONCOMPLIANCE, sys_["id"], "заявлено %s, рассчитано %s" % (declared, calculated),
                                    "Заявленный уровень расходится с расчётом по матрице",
                                    "Пересмотреть заявленный уровень и набор мер, переутвердить акт", system=sys_["id"],
                                    document="Акт определения УЗ (новая редакция)", expected="Заявленный уровень равен расчётному"))
    return _check("A04", "Совпадение заявленного и рассчитанного УЗ", findings, "Заявленные и рассчитанные уровни совпадают")


def _check_a05_threshold(ctx):
    d = ctx["data"]
    findings = []
    threshold = d["SUBJECT_THRESHOLD"]
    included = d["THRESHOLD_IN_LARGE_GROUP"]
    expected_groups = ("малая", "большая" if included else "малая", "большая")
    complete_rules = 0
    for category in d["PD_CATEGORIES"]:
        for threat in d["THREAT_TYPES"]:
            for group in ("малая", "большая"):
                if (category, group, threat) not in d["LEVEL_MATRIX"]:
                    findings.append(_finding(NONCOMPLIANCE, "матрица", "нет правила %s|%s|%d" % (category, group, threat),
                                            "Матрица неполна", "Дополнить матрицу", document="data/level_matrix.py"))
                else:
                    complete_rules += 1
    for subject_type in ("не_сотрудники",):
        results = [calculate_level("специальные", subject_type, number, 2) for number in (threshold - 1, threshold, threshold + 1)]
        groups = [r_["matrix_ground"].split("|")[1] if r_["matrix_ground"] else None for r_ in results]
        if tuple(groups) != expected_groups:
            findings.append(_finding(NONCOMPLIANCE, "level_calculation", "группы на границе %s, ожидалось %s" % (groups, list(expected_groups)),
                                    "Порог обрабатывается некорректно", "Исправить сравнение с порогом", document="programs/level_calculation.py"))
    return _check("A05", "Корректная обработка порога 100 000 субъектов", findings,
                     "Значения %d / %d / %d попадают в группы %s; матрица полна (%d правил)" % (threshold - 1, threshold, threshold + 1, "/".join(expected_groups), complete_rules))


def _check_a06_equipment_links(ctx):
    findings = []
    for n_ in ctx["equipment_findings"]:
        if n_["kind"] in ("нет_связи", "ссылка_на_несуществующую_систему", "связь_не_взаимная", "система_без_оборудования"):
            findings.append(_finding(NONCOMPLIANCE if n_["severity"] == "несоответствие" else REMARK,
                                    n_["equipment"] or n_["system"], n_["description"], "Нарушена связь оборудования с ИСПДн",
                                    n_["recommendation"], system=n_["system"], document="data/equipment.py",
                                    expected="Каждый элемент оборудования связан с существующей ИСПДн"))
    return _check("A06", "Ссылки оборудования на существующие системы", findings, "Все ссылки оборудования корректны и взаимны")


def _check_a07_classification(ctx):
    findings = []
    for n_ in ctx["equipment_findings"]:
        if n_["kind"] in ("нет_классификации", "недопустимый_класс", "нет_обоснования", "противоречие"):
            findings.append(_finding(NONCOMPLIANCE if n_["severity"] == "несоответствие" else REMARK,
                                    n_["equipment"], n_["description"], "Классификация ОТСС/ВТСС не заполнена или противоречива",
                                    n_["recommendation"], system=n_["system"], document="Перечень оборудования",
                                    expected="Каждый элемент классифицирован и обоснован"))
    return _check("A07", "Заполненность и непротиворечивость классификации ОТСС/ВТСС", findings, "Классификация заполнена и непротиворечива")


def _check_a08_measures(ctx):
    findings = []
    for sys_ in ctx["data"]["SYSTEMS"]:
        m_ = ctx["measures"][sys_["id"]]
        if m_["error"]:
            findings.append(_finding(INSUFFICIENT_DATA, sys_["id"], m_["error"], "Уровень не определён", "Определить уровень", system=sys_["id"]))
        for measure in m_["gaps"]:
            findings.append(_finding(NONCOMPLIANCE, "%s / %s" % (sys_["id"], measure["code"]), "требуется, но не реализована: %s" % measure["title"],
                                    "Мера входит в набор для %s, в фактических мерах отсутствует" % m_["level"],
                                    "Реализовать меру %s и подтвердить: %s" % (measure["code"], measure["confirmation_method"]),
                                    system=sys_["id"], document="Подтверждение меры %s" % measure["code"],
                                    expected="Мера %s реализована и подтверждена" % measure["code"]))
    total_required = sum(len(ctx["measures"][sys_["id"]]["required"]) for sys_ in ctx["data"]["SYSTEMS"])
    return _check("A08", "Сравнение требуемых и фактически реализованных мер", findings, "Все %d требуемых мер реализованы" % total_required)


def _check_a09_protection_tools(ctx):
    d = ctx["data"]
    numbers = {sys_["id"] for sys_ in d["SYSTEMS"]}
    findings = []
    for item in d["PROTECTION_TOOLS"]:
        obj = item.get("id")
        if item.get("tool_type") not in d["TOOL_TYPES"]:
            findings.append(_finding(NONCOMPLIANCE, obj, "недопустимый тип средства %r" % (item.get("tool_type"),), "Тип не СЗИ/СКЗИ", "Указать СЗИ или СКЗИ", document="data/protection_tools_ref.py"))
        equipment_class = item.get("tool_class") if item.get("tool_type") == "СЗИ" else item.get("crypto_class")
        foreign_class = item.get("crypto_class") if item.get("tool_type") == "СЗИ" else item.get("tool_class")
        if foreign_class:
            findings.append(_finding(REMARK, obj, "заполнен класс чужого типа средств", "Классы СЗИ и СКЗИ нельзя смешивать", "Убрать чужой класс", document="data/protection_tools_ref.py"))
        if (equipment_class or item.get("certificate_or_status")) and not (item.get("information_source") or "").strip():
            findings.append(_finding(NONCOMPLIANCE, obj, "класс/статус указан без источника", "Нет источника сведений", "Указать источник (реестр ФСТЭК/ФСБ)", document="data/protection_tools_ref.py"))
        if not equipment_class or not (item.get("certificate_or_status") or "").strip():
            findings.append(_finding(INSUFFICIENT_DATA, obj, "не заполнен класс или статус", "Нет сведений о классе/статусе", "Уточнить по документации и реестру", document="data/protection_tools_ref.py"))
        for sys_ in item.get("linked_system", []):
            if sys_ not in numbers:
                findings.append(_finding(NONCOMPLIANCE, obj, "связанная система %s не существует" % sys_, "Неверная ссылка", "Исправить идентификатор", document="data/protection_tools_ref.py"))
    for sys_ in d["SYSTEMS"]:
        if any(m_["code"] == "ЗИС.3" for m_ in ctx["measures"][sys_["id"]]["required"]) and not any(
                item.get("tool_type") == "СКЗИ" and sys_["id"] in item.get("linked_system", []) for item in d["PROTECTION_TOOLS"]):
            findings.append(_finding(REMARK, sys_["id"], "мера ЗИС.3 требуется, но СКЗИ для системы не указано", "Нет сведений о СКЗИ",
                                    "Внести СКЗИ в справочник", system=sys_["id"], document="data/protection_tools_ref.py"))
    return _check("A09", "Сведения о СЗИ/СКЗИ и источник класса/статуса", findings, "Сведения о СЗИ/СКЗИ полны, источники указаны")


def _check_a10_gis_order_17(ctx):
    d = ctx["data"]
    findings = []
    present = any(sys_.get("is_gis") == "да" for sys_ in d["SYSTEMS"])
    if (d["ORGANIZATION"].get("has_gis") == "да") != present:
        findings.append(_finding(NONCOMPLIANCE, "ORGANIZATION.has_gis", "признак в паспорте не совпадает с реестром систем", "Признак ГИС противоречив",
                                "Согласовать признак ГИС", document="data/organization.py"))
    for sys_ in d["SYSTEMS"]:
        if sys_.get("is_gis") != "да":
            continue
        order17 = ctx["order_17"].get(sys_["id"])
        if not order17 or not order17["applicable"] or not order17["considered"]:
            findings.append(_finding(NONCOMPLIANCE, sys_["id"], "применимость приказа № 17 не рассмотрена", "ГИС без отдельной проверки", "Выполнить проверку приказа № 17", system=sys_["id"]))
            continue
        for r_ in order17["considered"]:
            if r_["status"] != COMPLIANT:
                findings.append(_finding(INSUFFICIENT_DATA, "%s / %s" % (sys_["id"], r_["code"]), r_["fact"], "Требуется ручное решение специалиста",
                                        "Определить класс ГИС и сверить меры по приказу № 17: " + r_["verification"], system=sys_["id"],
                                        document="Акт классификации ГИС", expected="Класс ГИС определён, набор мер сверен"))
    return _check("A10", "Рассмотрение применимости приказа № 17 для ГИС", findings, "ГИС нет либо проверка приказа № 17 полностью выполнена")


def _check_a11_justifications(ctx):
    findings = []
    for sys_ in ctx["data"]["SYSTEMS"]:
        m_ = ctx["measures"][sys_["id"]]
        for n_ in m_["inapplicable"]:
            if not (n_.get("inapplicability_justification") or "").strip():
                findings.append(_finding(NONCOMPLIANCE, "%s / %s" % (sys_["id"], n_["code"]), "условная мера признана неприменимой без обоснования",
                                        "Неприменимость не обоснована", "Записать обоснование неприменимости", system=sys_["id"], document="data/systems.py"))
        for n_ in m_["clarify"]:
            findings.append(_finding(INSUFFICIENT_DATA, "%s / %s" % (sys_["id"], n_["code"]), n_["inclusion_reason"], "Условие применимости не заполнено",
                                    "Заполнить особенности системы", system=sys_["id"], document="data/systems.py"))
        extra_codes = [code for code in sys_.get("inapplicability_justifications", {}) if code not in {n_["code"] for n_ in m_["inapplicable"]}]
        for code in extra_codes:
            findings.append(_finding(REMARK, "%s / %s" % (sys_["id"], code), "обоснование есть, но мера по условиям применима или не входит в набор",
                                    "Обоснование не соответствует условиям", "Удалить или пересмотреть обоснование", system=sys_["id"], document="data/systems.py"))
    return _check("A11", "Обоснование условных и неприменимых мер", findings, "Все неприменимые меры обоснованы")


def _check_a12_documents(ctx):
    findings = []
    documents = ctx["generated"]
    for name, description in (("level_determination_acts", "акт определения УЗ"), ("remediation_plan", "план исправлений")):
        if name not in documents:
            findings.append(_finding(NONCOMPLIANCE, name, "документ «%s» не сформирован" % description, "Документ отсутствует", "Сформировать документ", document=name))
    if not ctx.get("report_date"):
        findings.append(_finding(NONCOMPLIANCE, "report_date", "дата отчёта не указана", "Нет даты", "Указать дату формирования"))
    return _check("A12", "Наличие акта определения УЗ, плана исправлений и даты отчёта", findings, "Акты, план исправлений и дата отчёта есть")


CHECKS = [_check_a01_completeness, _check_a02_validity, _check_a03_subject_counts, _check_a04_declared_level, _check_a05_threshold, _check_a06_equipment_links,
            _check_a07_classification, _check_a08_measures, _check_a09_protection_tools, _check_a10_gis_order_17, _check_a11_justifications, _check_a12_documents]


# ----------------------------------------------------------------- результаты аудита

def training_score(checks):
    """Среднее баллов статусов по проверкам, 0-100 (внутренняя учебная метрика)."""
    return round(sum(STATUS_SCORES[p_["status"]] for p_ in checks) / len(checks))


def run_audit(context):
    """Выполняет все проверки. Контекст - словарь, подготовленный главным симулятором."""
    checks = [func(context) for func in CHECKS]
    defects = [dict(n_, check=p_["id"]) for p_ in checks for n_ in p_["findings"]]
    return {"checks": checks, "score": training_score(checks), "defects": defects}


def _responsible(finding, data):
    if finding.get("system"):
        for sys_ in data["SYSTEMS"]:
            if sys_["id"] == finding["system"]:
                return sys_["responsible"]
    return data["ORGANIZATION"]["pd_protection_officer"]


def build_remediation_plan(audit, data, on_date=None):
    """План устранения реальных пробелов: по одной записи на каждую находку аудита."""
    on_date = on_date or datetime.date.today()
    records = []
    for d in audit["defects"]:
        priority = PRIORITY_BY_STATUS[d["status"]]
        records.append({
            "violation": "[%s] %s: %s" % (d["check"], d["obj"], d["fact"]),
            "action": d["recommendation"],
            "priority": priority,
            "responsible": _responsible(d, data),
            "deadline": (on_date + datetime.timedelta(days=DEADLINE_DAYS[priority])).isoformat(),
            "dependency": d["dependency"],
            "confirming_document": d["document"] or "Протокол проверки",
            "expected_result": d["expected"] or "Находка аудита снята при повторной проверке",
            "finding_status": d["status"],
        })
    order = {"высокий": 0, "средний": 1, "низкий": 2}
    return sorted(records, key=lambda item: order[item["priority"]])


def priority_recommendations(plan, data, on_date=None, minimum=3, maximum=5):
    """3-5 приоритетных действий: сначала несоответствия, затем недостаточность данных и замечания."""
    on_date = on_date or datetime.date.today()
    selected, seen = [], set()
    for record in plan:
        if record["action"] in seen:
            continue
        seen.add(record["action"])
        selected.append({"action": record["action"], "responsible": record["responsible"], "deadline": record["deadline"],
                          "ground": record["violation"]})
        if len(selected) == maximum:
            break
    fallback = [
        ("Сверить матрицу УЗ и набор мер с действующими редакциями постановления № 1119 и приказов ФСТЭК № 21 и № 17",
         "Провести ручную проверку нормативных оснований (раздел 6.4)"),
        ("Подтвердить статус сертификатов СЗИ/СКЗИ по официальным реестрам ФСТЭК и ФСБ", "Проверка реестров"),
        ("Провести повторный аудит после устранения замечаний", "Контрольный запуск симулятора"),
    ]
    for action, ground in fallback:
        if len(selected) >= minimum:
            break
        selected.append({"action": action, "responsible": data["ORGANIZATION"]["pd_protection_officer"],
                          "deadline": (on_date + datetime.timedelta(days=30)).isoformat(), "ground": ground})
    return selected
