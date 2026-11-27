# editor/bridge/dispatch/error_codes.gd - коды ошибок редакторной стороны.
# Коды причин редакторной стороны: те же имена, что читает Python (`error_codes.gd`
# в подсказке `client.py`). R-15: отказ - типизированный, а не строка.
@tool
extends RefCounted

const BAD_TOKEN := "bad_token"
const UNKNOWN_VERB := "unknown_verb"
const FRAME_TOO_BIG := "frame_too_big"
const TRUNCATED := "truncated"
const TIMEOUT := "timeout"
const WRONG_PROJECT := "wrong_project"
const VERBS_MISMATCH := "verbs_mismatch"
const INVALID_ARGS := "invalid_args"
const UNKNOWN_OPERATION := "unknown_operation"
const SCENE_NOT_FOUND := "scene_not_found"
const REVISION_MISMATCH := "revision_mismatch"
const STALE_PLAN := "stale_plan"
const PLAN_INVALID := "plan_invalid"
const APPLY_FAILED := "apply_failed"
const NOTHING_TO_UNDO := "nothing_to_undo"

const KINDS := {
	BAD_TOKEN: "denied",
	UNKNOWN_VERB: "unknown_tool",
	FRAME_TOO_BIG: "engine_down",
	TRUNCATED: "engine_down",
	TIMEOUT: "engine_down",
	WRONG_PROJECT: "engine_down",
	VERBS_MISMATCH: "engine_down",
	INVALID_ARGS: "invalid_input",
	UNKNOWN_OPERATION: "invalid_input",
	PLAN_INVALID: "invalid_input",
	SCENE_NOT_FOUND: "not_found",
	REVISION_MISMATCH: "conflict",
	STALE_PLAN: "stale_plan",
	APPLY_FAILED: "internal",
	NOTHING_TO_UNDO: "conflict",
}


static func payload(reason: String, message: String) -> Dictionary:
	return {"ok": false,
		"error": {"kind": KINDS.get(reason, "engine_down"),
			"reason": reason, "message": message}}
