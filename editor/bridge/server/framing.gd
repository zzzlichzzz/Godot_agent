# editor/bridge/server/framing.gd - кадрирование сообщений моста.
# Кадр: 4 байта длины big-endian + JSON UTF-8, лимит 1 МиБ (ADR-0007).
# Неполный кадр - не ошибка: `decode` отвечает `partial` и просит ещё байт.
@tool
extends RefCounted

const HEADER := 4
const MAX_FRAME := 1048576


static func encode(obj: Dictionary) -> Dictionary:
	var payload := JSON.stringify(obj).to_utf8_buffer()
	if payload.is_empty():
		return {"ok": false, "reason": "truncated", "message": "пустой кадр"}
	if payload.size() > MAX_FRAME:
		return {"ok": false, "reason": "frame_too_big",
			"message": "кадр больше лимита: %d > %d" % [payload.size(), MAX_FRAME]}
	var frame := PackedByteArray()
	frame.resize(HEADER)
	_put_u32_be(frame, payload.size())
	frame.append_array(payload)
	return {"ok": true, "frame": frame}


static func _put_u32_be(frame: PackedByteArray, value: int) -> void:
	# Заголовок строго big-endian (`contract/editor_verbs.json` → `frame`): у
	# `PackedByteArray.encode_u32` порядок little-endian, поэтому байты пишутся явно.
	frame.encode_u8(0, (value >> 24) & 0xFF)
	frame.encode_u8(1, (value >> 16) & 0xFF)
	frame.encode_u8(2, (value >> 8) & 0xFF)
	frame.encode_u8(3, value & 0xFF)


static func _get_u32_be(frame: PackedByteArray) -> int:
	return ((frame[0] << 24) | (frame[1] << 16) | (frame[2] << 8) | frame[3]) & 0xFFFFFFFF


static func decode(buffer: PackedByteArray) -> Dictionary:
	if buffer.size() < HEADER:
		return {"ok": false, "partial": true, "rest": buffer}
	var size := _get_u32_be(buffer)
	if size == 0:
		return {"ok": false, "reason": "truncated", "message": "пустой кадр"}
	if size > MAX_FRAME:
		return {"ok": false, "reason": "frame_too_big",
			"message": "кадр больше лимита: %d > %d" % [size, MAX_FRAME]}
	if buffer.size() < HEADER + size:
		return {"ok": false, "partial": true, "rest": buffer}
	var text := buffer.slice(HEADER, HEADER + size).get_string_from_utf8()
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return {"ok": false, "reason": "truncated", "message": "мусор в JSON"}
	return {"ok": true, "object": parsed, "rest": buffer.slice(HEADER + size)}
