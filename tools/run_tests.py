# tools/run_tests.py - unit- и contract-тесты с машинным вердиктом (R-18).
# Использование: python tools/run_tests.py [цели...] [--json]
# Зачем обёртка: сам pytest JSON-вердикта не печатает, а selfcheck без вердикта
# считает проверку невыполненной. Здесь к его выводу добавляется последняя
# строка {"status": "ok" | "fail" | "not_implemented", "detail": "..."}.

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("python/modules", "tests/py")


def verdict(status, detail):
    print(json.dumps({"status": status, "detail": detail}, ensure_ascii=False))
    return 0 if status == "ok" else 1


def main(argv):
    targets = [item for item in argv[1:] if not item.startswith("--")] or list(TARGETS)
    try:
        done = subprocess.run([sys.executable, "-B", "-m", "pytest"] + targets,
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=900)
    except OSError as exc:
        return verdict("not_implemented", "pytest не запускается: %s" % exc)
    output = (done.stdout or "").rstrip()
    if output:
        print(output)
    if "No module named pytest" in (done.stderr or "").lower():
        return verdict("not_implemented", "нет pytest (см. pyproject.toml, dev-зависимости)")
    summary = next((line.strip() for line in reversed(output.splitlines()) if line.strip()), "")
    if done.returncode == 0:
        return verdict("ok", summary or "тесты прошли")
    detail = summary or (done.stderr or "").strip().splitlines()[-1:] or ""
    if isinstance(detail, list):
        detail = detail[0] if detail else "код %d" % done.returncode
    return verdict("fail", str(detail) or "код %d" % done.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
