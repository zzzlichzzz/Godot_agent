"""modules/editing/scene_ops/module.py - манифест модуля editing.scene_ops.

Инструмент один: `scene_ops` с эффектом `write` (R-12): правка идёт не в файл,
а в открытую сцену редактора через мост GDScript, поэтому Python только собирает
запрос и проверяет квитанции. Профиль `editor`: вне редактора мост отвечает
`engine_down`, модуль в headless не загружается. Правила: R-02 (папка = фича),
R-03 (подключение сканированием), R-05 (манифест).
"""

from python.kernel.module_spec import ModuleSpec

from . import app, tools

MODULE = ModuleSpec(
    id="editing.scene_ops",
    description="Батч правок открытой сцены одним undo-шагом через мост редактора.",
    environment="editor",
    #: Корпус не снимается: исполнение в GDScript редактора, доказательство -
    #: живой тест `tests/py/live/test_editor_branch_live.py` (R-07, R-18).
    corpus="live",
    provides_tools=(tools.SCENE_OPS.name,),
    internal_services=("scene_executor",),
    requires_ports=("editor",),
    capabilities=("editing.scene_ops",),
    entrypoints={"call": app.call},
)
# contributes: write_preview, write_apply (операции сцены)
# Правила: R-02, R-03, R-05. Компилятор операций структурных правок сцены:
# схемы операций и staged-файл; сама запись - воронка (R-12) и примитивы редактора.
# TODO: ModuleSpec(id="editing.scene_ops", version="0.1.0", kernel_api="^1",
#                  godot="^4.6", environment="editor", entrypoints={"setup": setup},
#                  depends=[], provides_tools=[], contributes_to=["write_preview", "write_apply"],
#                  capabilities=["editing.scene_ops"], settings_schema={})
