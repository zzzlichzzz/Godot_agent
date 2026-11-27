"""conftest.py - корень Python-части для тестов.

Тесты лежат глубже (`python/modules/.../tests/`, `tests/py/...`), а импорты в них
абсолютные (`from python.kernel...`). Корень аддона добавляется в `sys.path` один
раз здесь, чтобы одинаково работали unit-, contract- и integration-прогоны
(`python -m pytest`). Логики и фикстур тут нет: им место в `tests/py/conftest.py`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
