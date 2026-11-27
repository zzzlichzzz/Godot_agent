"""Pure public request policy; the frozen native engine owns ranking/formatting."""
from python.kernel.errors import AppError

DEFAULT_BUDGET = 8000
LIMITS = {"budget_chars_default": DEFAULT_BUDGET, "budget_chars_min": 400,
          "map_files": 8, "structure_files": 3, "signatures_per_file": 24,
          "scene_chars": 900, "fragments": 6, "fragment_tokens": 4,
          "fragments_per_file": 2, "fragment_pool": 12, "callers": 6,
          "caller_functions": 2, "autoloads": 12, "signals": 2, "signal_links": 6,
          "card_declarations": 4, "card_parameters": 10, "card_locals": 8,
          "card_uses": 8, "card_references": 8}


def build_request(args, policy):
    if not isinstance(args, dict) or set(args) - {"query", "budget_chars"}:
        raise AppError("invalid_input", "ask принимает query и budget_chars")
    query = args.get("query")
    if not isinstance(query, str) or not query.strip() or "\x00" in query:
        raise AppError("invalid_input", "query должен быть непустой строкой без NUL")
    budget = args.get("budget_chars", DEFAULT_BUDGET)
    if not isinstance(budget, int) or isinstance(budget, bool):
        raise AppError("invalid_input", "budget_chars должен быть целым числом")
    target = _literal_path(query.strip())
    if target is not None and not policy.can_read(target):
        raise AppError("denied", "путь запроса закрыт политикой проекта")
    return {"query": query, "budget_chars": budget,
            "allow_addons": bool(policy.allow_addons),
            "allow_self_edit": bool(policy.allow_self_edit), "target": target}


def _literal_path(query):
    if query.startswith("res://"):
        return query[6:]
    absolute = query.startswith(("/", "\\")) or (len(query) > 1 and query[1] == ":")
    separated = "/" in query or "\\" in query
    if absolute or (separated and not any(char.isspace() for char in query)):
        return query
    return None
