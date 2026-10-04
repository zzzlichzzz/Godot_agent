# -*- coding: utf-8 -*-
"""Синтетический тест подэтапа 4.4: панель не создаёт HTTPRequest.

Короткие запросы панели (живой ввод, опрос прогресса, остановка чата,
автосинхронизация переименований) раньше держали на себе четыре отдельных
HTTPRequest. Теперь они идут через узел связи: у него и заголовки уже
собраны, и таймаут короче. Проверяется именно это — иначе панель снова
начнёт ходить в сеть мимо транспорта.

Запуск:
    python -B python/tests/test_panel_short_channel.py
"""
import argparse
from pathlib import Path
import re
import sys


class StaticChecks:
    """Панель не создаёт HTTPRequest: короткие запросы идут через узел связи."""

    def __init__(self, addon: Path):
        self.addon = addon
        self.failures = []
        self.checks = 0
        self.panel_path = addon / "agent_panel.gd"
        self.link_path = addon / "agent_server_link.gd"

    def check(self, name, condition, detail=""):
        self.checks += 1
        if condition:
            print("%s -> OK" % name)
        else:
            print("%s -> FAIL" % name)
            if detail:
                print("     %s" % (detail,))
            self.failures.append((name, detail))

    def run(self):
        for name, path in (("панель", self.panel_path), ("транспорт", self.link_path)):
            self.check("%s на месте" % name, path.is_file(), str(path))
        if not (self.panel_path.is_file() and self.link_path.is_file()):
            return
        panel = self.panel_path.read_text(encoding="utf-8")
        link = self.link_path.read_text(encoding="utf-8")

        self.check("панель не создаёт HTTPRequest",
                   "HTTPRequest.new()" not in panel,
                   "остались собственные HTTPRequest мимо узла связи")
        for api in ("post_now", "get_now", "is_short_busy"):
            self.check("транспорт даёт %s()" % api, ("func %s(" % api) in link)
        self.check("транспорт отдаёт короткие ответы",
                   "signal short_response(" in link and "short_response.emit(" in link)
        self.check("панель слушает короткие ответы",
                   "_link.short_response.connect(" in panel)
        self.check("панель раздаёт короткие ответы по id",
                   re.search(r"func\s+_on_short_response\b.*?match\s+id\s*:",
                             panel, re.DOTALL) is not None)
        for kind in ("progress", "live_input", "chat_stop", "post_move_sync"):
            self.check("короткий запрос %s идёт через узел связи" % kind,
                       ('"%s"' % kind) in panel)
        self.check("канал не пускает второй запрос молча",
                   "_short_busy" in link)
        self.check("панель больше не держит полей HTTPRequest",
                   not re.search(r"var\s+_(progress|live)_http\s*:", panel))


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    addon = Path(__file__).resolve().parents[2]
    static = StaticChecks(addon)
    static.run()
    print("СТАТИКА: %d проверок, %d провалов" % (static.checks, len(static.failures)))
    raise SystemExit(0 if not static.failures else 1)


if __name__ == "__main__":
    main()