# editor/bridge/server/session.gd - одна сессия моста: запрос, ответ, таймаут.
# Одна сессия: handshake первым кадром, токен проверяется в каждом кадре,
# ответ отправляется в тот же сокет. Второй кадр до ответа не буферизуется -
# один in-flight держит Python-клиент (ADR-0007), сервер только отказывает.
@tool
extends RefCounted

const Framing := preload("framing.gd")
const ErrorCodes := preload("../dispatch/error_codes.gd")
const ContextSnapshot := preload("../verbs/editors/context_snapshot.gd")

const PROTOCOL := 1
const VERBS_VERSION := 3

var _peer: StreamPeerTCP
var _token: String
var _dispatcher
var _buffer := PackedByteArray()
var _greeted := false


func _init(peer: StreamPeerTCP, token: String, dispatcher) -> void:
	_peer = peer
	_token = token
	_dispatcher = dispatcher
	if _peer != null:
		_peer.set_no_delay(true)


func poll() -> bool:
	# Читает кадры; `false` - соединение закрыто.
	if _peer == null:
		return false
	_peer.poll()
	if _peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		return false
	var available := _peer.get_available_bytes()
	if available > 0:
		var chunk := _peer.get_partial_data(available)
		if int(chunk[0]) != OK:
			return false
		_buffer.append_array(chunk[1])
	while true:
		var frame := Framing.decode(_buffer)
		if bool(frame.get("partial", false)):
			return true
		if not bool(frame.get("ok", false)):
			_send(ErrorCodes.payload(str(frame.get("reason", "truncated")),
				str(frame.get("message", ""))))
			return false
		_buffer = frame["rest"]
		if not _handle(frame["object"]):
			return false
	return true


func close() -> void:
	if _peer != null and _peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		_peer.disconnect_from_host()


func _handle(message: Dictionary) -> bool:
	if not _greeted:
		return _handshake(message)
	if str(message.get("token", "")) != _token:
		_send(ErrorCodes.payload(ErrorCodes.BAD_TOKEN, "кадр без токена"))
		return false
	var answer = _dispatcher.handle(message)
	_send(answer if typeof(answer) == TYPE_DICTIONARY
		else ErrorCodes.payload(ErrorCodes.TRUNCATED, "нет ответа"))
	return true


func _handshake(message: Dictionary) -> bool:
	var hello = message.get("hello")
	if typeof(hello) != TYPE_DICTIONARY:
		_send(ErrorCodes.payload(ErrorCodes.TRUNCATED, "первый кадр - не hello"))
		return false
	if str(hello.get("token", "")) != _token:
		_send(ErrorCodes.payload(ErrorCodes.BAD_TOKEN, "токен не совпал"))
		return false
	if int(hello.get("protocol", 0)) != PROTOCOL:
		_send(ErrorCodes.payload(ErrorCodes.VERBS_MISMATCH, "protocol расходится"))
		return false
	if int(hello.get("verbs_version", 0)) != VERBS_VERSION:
		_send(ErrorCodes.payload(ErrorCodes.VERBS_MISMATCH, "verbs_version расходится"))
		return false
	_greeted = true
	_send({"hello": {"protocol": PROTOCOL, "verbs_version": VERBS_VERSION,
		"godot": str(Engine.get_version_info().get("string", "4")),
		"project_hash": ContextSnapshot.project_hash(), "token": _token}})
	return true


func _send(payload: Dictionary) -> void:
	var frame := Framing.encode(payload)
	if not bool(frame.get("ok", false)):
		if _peer != null:
			_peer.disconnect_from_host()
		return
	_peer.put_data(frame["frame"])
