# -*- coding: utf-8 -*-
"""Общие функции: пути проекта, загрузка данных, применение правок, запись файлов."""

import copy
import importlib
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, "documents")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")

# Модуль данных -> имена переменных, которые он обязан содержать
DATA_FILES = {
    "organization": ["ORGANIZATION"],
    "systems": ["SYSTEMS", "SHARED_CONTOURS"],
    "level_matrix": ["LEVEL_MATRIX", "PD_CATEGORIES", "SUBJECT_TYPES", "THREAT_TYPES", "LEVELS", "SUBJECT_THRESHOLD"],
    "measures_catalog": ["MEASURES_CATALOG", "MEASURE_GROUPS", "GIS_GROUNDS", "MINIMIZATION_EXAMPLE", "REGULATORY_SOURCES"],
    "equipment": ["EQUIPMENT", "EQUIPMENT_CLASSES"],
    "protection_tools_ref": ["PROTECTION_TOOLS", "TOOL_TYPES"],
    "test_scenarios": ["SCENARIOS", "BOUNDARY_TEST", "TESTS", "BASELINE_FIXES"],
}


class DataError(Exception):
    """Критическая ошибка загрузки данных; сообщение содержит файл и поле."""


def load_data():
    """Загружает все файлы данных и возвращает глубокие копии (исходные модули не меняются)."""
    result = {}
    for module, names in DATA_FILES.items():
        file = "data/%s.py" % module
        try:
            m = importlib.import_module("data." + module)
        except ModuleNotFoundError as error:
            raise DataError("Файл %s не найден или не загружается (%s)" % (file, error))
        except SyntaxError as error:
            raise DataError("Файл %s: синтаксическая ошибка в строке %s" % (file, error.lineno))
        for name in names:
            if not hasattr(m, name):
                raise DataError("Файл %s: отсутствует обязательная переменная %s" % (file, name))
            result[name] = copy.deepcopy(getattr(m, name))
        if module == "level_matrix":
            result["THRESHOLD_IN_LARGE_GROUP"] = getattr(m, "THRESHOLD_IN_LARGE_GROUP", True)
    return result


def _find(container, key):
    """Элемент словаря по ключу или элемент списка по полю «номер»."""
    if isinstance(container, dict):
        return container[key]
    for element in container:
        if isinstance(element, dict) and element.get("id") == key:
            return element
    raise KeyError(key)


_PATCH_ROOTS = {"systems": "SYSTEMS", "equipment": "EQUIPMENT", "organization": "ORGANIZATION"}


def apply_patches(data, patches):
    """Применяет правки вида (операция, путь, значение) к копии данных и возвращает её."""
    copy_ = copy.deepcopy(data)
    for operation, path, value in patches:
        obj = copy_[_PATCH_ROOTS[path[0]]]
        for key in path[1:-1]:
            obj = _find(obj, key)
        last = path[-1]
        if operation == "set_op":
            obj[last] = value
        elif operation == "add_op":
            obj[last].append(value)
        elif operation == "remove_op":
            obj[last].remove(value)
        else:
            raise ValueError("Неизвестная операция правки: %s" % operation)
    return copy_


def baseline_data(data):
    """Состояние данных до внесения трёх намеренных дефектов."""
    return apply_patches(data, data["BASELINE_FIXES"])


def write_file(folder, name, text):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(text)
    return path
