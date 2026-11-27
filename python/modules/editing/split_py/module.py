"""editing.split_py: reference scan, native plan and WAL-backed apply."""
from python.kernel.module_spec import ModuleSpec

from .app import call

MODULE = ModuleSpec(id='editing.split_py',description='Карта, план и применение разбиения .py',
                    provides_tools=('split_scan','split_plan','split_apply'),
                    requires_ports=('fs','journal'),requires=('editing.write_apply',),
                    capabilities=('editing.split_py',),entrypoints={'call':call},corpus='corpus')
