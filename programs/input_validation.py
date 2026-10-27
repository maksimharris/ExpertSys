# -*- coding: utf-8 -*-
"""Проверка обязательных полей, типов, допустимых значений и согласованности идентификаторов.

Каждая запись об ошибке: {"файл", "поле", "сообщение", "критично"}.
Критичными считаются ошибки, при которых дальнейший расчёт невозможен.
"""

from programs.common import PROJECT_ROOT  # noqa: F401

ORGANIZATION_FIELDS = {
    "title": str, "industry": str, "founded_year": int, "city": str,
    "employee_count": int, "total_unique_subjects": int,
    "pd_protection_officer": str, "project_manager": str,
    "organization_type": str, "has_gis": str, "main_technologies": str,
    "external_integrations": str, "infrastructure_description": str, "processing_features": str,
}
ORGANIZATION_TYPES = ("коммерческая", "государственная", "муниципальная")

SYSTEM_FIELDS = {
    "id": str, "title": str, "purpose": str, "boundaries": str,
    "pd_category": str, "data_examples": str, "subject_type": str,
    "subject_count": int, "threat_type_given": int, "is_gis": str,
    "actual_measures": list, "declared_level": str, "linked_equipment": list, "responsible": str,
}

EQUIPMENT_FIELDS = {
    "id": str, "title": str, "type": str, "linked_ispdn": list,
    "processes_pd": bool, "location": str, "role": str, "equipment_class": str, "justification": str,
}


def _error(file, field, message, critical=True):
    return {"file": file, "field": field, "message": message, "critical": critical}


def _check_types(record, fields, file, prefix, errors, allow_empty=()):
    for field, type_ in fields.items():
        name = "%s.%s" % (prefix, field)
        if field not in record:
            errors.append(_error(file, name, "обязательное поле отсутствует"))
            continue
        value = record[field]
        if type_ is int and (isinstance(value, bool) or not isinstance(value, int)):
            errors.append(_error(file, name, "ожидалось целое число, получено %r" % (value,)))
        elif type_ is not int and not isinstance(value, type_):
            errors.append(_error(file, name, "ожидался тип %s, получено %r" % (type_.__name__, value)))
        elif type_ is str and not value.strip() and field not in allow_empty:
            errors.append(_error(file, name, "поле не заполнено"))


def validate_input_data(data):
    """Возвращает список ошибок (пустой, если всё корректно)."""
    errors = []
    org = data["ORGANIZATION"]
    _check_types(org, ORGANIZATION_FIELDS, "data/organization.py", "ORGANIZATION", errors)
    if org.get("organization_type") not in ORGANIZATION_TYPES:
        errors.append(_error("data/organization.py", "ORGANIZATION.organization_type",
                              "недопустимое значение %r (допустимо: %s)" % (org.get("organization_type"), ", ".join(ORGANIZATION_TYPES))))
    if org.get("has_gis") not in ("да", "нет"):
        errors.append(_error("data/organization.py", "ORGANIZATION.has_gis", "допустимо «да» или «нет»"))

    systems = data["SYSTEMS"]
    if len(systems) < 3:
        errors.append(_error("data/systems.py", "SYSTEMS", "требуется не менее трёх ИСПДн, найдено %d" % len(systems)))
    system_numbers = []
    catalog_codes = {m_["code"] for m_ in data["MEASURES_CATALOG"]}
    for position, sys_ in enumerate(systems):
        label = "SYSTEMS[%d]" % position
        # Для заявленного УЗ допускается пустая строка (ранее не присваивался)
        _check_types(sys_, SYSTEM_FIELDS, "data/systems.py", label, errors, allow_empty=("declared_level",))
        system_numbers.append(sys_.get("id"))
        if sys_.get("is_gis") not in ("да", "нет"):
            errors.append(_error("data/systems.py", label + ".is_gis", "допустимо «да» или «нет»"))
        if sys_.get("declared_level") and sys_["declared_level"] not in data["LEVELS"]:
            errors.append(_error("data/systems.py", label + ".declared_level", "недопустимое значение %r" % (sys_["declared_level"],)))
        for code in sys_.get("actual_measures", []) if isinstance(sys_.get("actual_measures"), list) else []:
            if code not in catalog_codes:
                errors.append(_error("data/systems.py", label + ".actual_measures", "мера %r отсутствует в каталоге" % (code,), critical=False))
        for extra in sys_.get("extra_contours", []):
            for field in ("pd_category", "subject_type", "subject_count", "threat_type_given"):
                if field not in extra:
                    errors.append(_error("data/systems.py", label + ".extra_contours." + field, "обязательное поле отсутствует"))
    duplicates = {n_ for n_ in system_numbers if system_numbers.count(n_) > 1}
    for n_ in sorted(d for d in duplicates if d):
        errors.append(_error("data/systems.py", "SYSTEMS.id", "повторяющийся идентификатор %s" % n_))

    equipment_numbers = []
    for position, o_ in enumerate(data["EQUIPMENT"]):
        label = "EQUIPMENT[%d]" % position
        # Пустая классификация и пустой список связей - предмет проверки оборудования, а не критичная ошибка
        _check_types(o_, EQUIPMENT_FIELDS, "data/equipment.py", label, errors, allow_empty=("equipment_class",))
        equipment_numbers.append(o_.get("id"))
    for n_ in sorted({n_ for n_ in equipment_numbers if equipment_numbers.count(n_) > 1 and n_}):
        errors.append(_error("data/equipment.py", "EQUIPMENT.id", "повторяющийся идентификатор %s" % n_))

    for sys_ in data["SHARED_CONTOURS"]:
        for n_ in sys_.get("systems", []):
            if n_ not in system_numbers:
                errors.append(_error("data/systems.py", "SHARED_CONTOURS." + str(sys_.get("id")), "ссылка на несуществующую систему %s" % n_))
    return errors


def critical_only(errors):
    return [o_ for o_ in errors if o_["critical"]]
