# -*- coding: utf-8 -*-
"""Проверка покрытия оборудования: связи с ИСПДн, классификация ОТСС/ВТСС, противоречия."""

from programs.common import PROJECT_ROOT  # noqa: F401


def _finding(eq, system, kind, description, recommendation, severity="несоответствие"):
    return {"equipment": eq.get("id"), "system": system, "kind": kind,
            "description": description, "recommendation": recommendation, "severity": severity}


def check_equipment(equipment, systems, classes=("ОТСС", "ВТСС")):
    """Возвращает список находок. Правила общие: по идентификаторам и полям, без жёстких номеров."""
    system_numbers = {sys_["id"] for sys_ in systems}
    by_number = {o_.get("id"): o_ for o_ in equipment}
    findings = []
    for eq in equipment:
        links = eq.get("linked_ispdn") or []
        if not links:
            findings.append(_finding(eq, None, "нет_связи", "Не указана связанная ИСПДн",
                                    "Указать систему, к которой относится оборудование"))
        for link in links:
            if link not in system_numbers:
                findings.append(_finding(eq, link, "ссылка_на_несуществующую_систему",
                                        "Ссылка на несуществующую ИСПДн %s" % link,
                                        "Исправить идентификатор системы в реестре оборудования"))
            else:
                system = next(sys_ for sys_ in systems if sys_["id"] == link)
                if eq.get("id") not in system.get("linked_equipment", []):
                    findings.append(_finding(eq, link, "связь_не_взаимная",
                                            "Система %s не перечисляет это оборудование в связанное_оборудование" % link,
                                            "Согласовать списки в data/systems.py и data/equipment.py", "замечание"))
        equipment_class = eq.get("equipment_class")
        if not equipment_class:
            findings.append(_finding(eq, ", ".join(links) or None, "нет_классификации", "Не заполнена классификация ОТСС/ВТСС",
                                    "Определить класс по учебной схеме и указать обоснование"))
        elif equipment_class not in classes:
            findings.append(_finding(eq, ", ".join(links) or None, "недопустимый_класс", "Недопустимый класс %r" % equipment_class,
                                    "Использовать значение ОТСС или ВТСС"))
        if not (eq.get("justification") or "").strip():
            findings.append(_finding(eq, ", ".join(links) or None, "нет_обоснования", "Не заполнено обоснование классификации",
                                    "Добавить обоснование", "замечание"))
        processes = eq.get("processes_pd")
        if equipment_class == "ВТСС" and processes:
            findings.append(_finding(eq, ", ".join(links) or None, "противоречие",
                                    "Оборудование обрабатывает ПДн, но отнесено к ВТСС",
                                    "Отнести к ОТСС или уточнить, что ПДн на нём не обрабатываются"))
        if equipment_class == "ОТСС" and processes is False:
            parent = by_number.get(eq.get("workstation_component"))
            if parent is None or not parent.get("processes_pd"):
                findings.append(_finding(eq, ", ".join(links) or None, "противоречие",
                                        "ОТСС не обрабатывает ПДн и не указан как компонент АРМ/ОТСС, обрабатывающего ПДн",
                                        "Указать компонент_арм либо пересмотреть класс (ВТСС)"))
    linked = {sys_ for eq in equipment for sys_ in (eq.get("linked_ispdn") or [])}
    for system in systems:
        if system["id"] not in linked:
            findings.append({"equipment": None, "system": system["id"], "kind": "система_без_оборудования",
                            "description": "К системе не привязано ни одного элемента оборудования",
                            "recommendation": "Провести инвентаризацию оборудования системы", "severity": "несоответствие"})
    return findings
