# -*- coding: utf-8 -*-
"""Полная проверка: прогон aistudio_2_stream.raw через настоящий AiStudioChatMonitor."""
import sys
import pathlib
import base64

_HERE = pathlib.Path(__file__).resolve().parent.parent
for _d in (_HERE, _HERE / "browser", _HERE / "parsers", _HERE / "godot_tools", _HERE / "server"):
    if _d.is_dir() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from browser.ai_studio_net import AiStudioChatMonitor


class DummyCDP:
    """Минимум CDP-интерфейса для монитора: streamResourceContent падает -> фоллбэк на getResponseBody."""
    def __init__(self, raw_bytes):
        self._raw = raw_bytes

    def send_command(self, method, params, timeout=15.0):
        if method == "Network.getResponseBody":
            b64 = base64.b64encode(self._raw).decode("ascii")
            return {"body": b64, "base64Encoded": True}
        if method == "Network.streamResourceContent":
            raise Exception("streamResourceContent unavailable")  # форсируем фоллбэк
        return {}

    def on_event(self, method, callback):
        pass

    def is_alive(self):
        return True

    def close(self):
        pass


CHAT_URL = "https://alkalimakersuite-pa.clients6.google.com/$rpc/google.internal.alkali.applications.makersuite.v1.MakerSuiteService/GenerateContent"


def main():
    raw_file = _HERE.parent.parent / "временно" / "aistudio_2_stream.raw"
    if not raw_file.exists():
        print("Файл не найден:", raw_file)
        return 1

    raw = raw_file.read_bytes()
    print(f"Загружено {len(raw)} байт из {raw_file}")

    dummy = DummyCDP(raw)
    monitor = AiStudioChatMonitor(dummy)

    # 1) requestWillBeSent
    monitor._on_request_will_be_sent({
        "request": {"url": CHAT_URL, "method": "POST", "requestId": "test-req-1"}
    })
    print(f"chat_request_count = {monitor.chat_request_count()}")

    # 2) responseReceived
    monitor._on_response_received({
        "response": {"url": CHAT_URL, "mimeType": "application/json+protobuf", "status": 200},
        "requestId": "test-req-1"
    })
    print(f"responseReceived обработан, generating = {monitor.is_generating()}")

    # 3) loadingFinished -> фоллбэк getResponseBody
    monitor._on_loading_finished({"requestId": "test-req-1"})

    # Результаты
    answer = monitor.current_text()
    thoughts = monitor.thought_text()
    finished = monitor.is_finished()
    gen = monitor.is_generating()
    msg_count = monitor.assistant_message_count()
    status = monitor.message_status()

    print("\n=== РЕЗУЛЬТАТЫ МОНИТОРА ===")
    print(f"answer_len = {len(answer)}")
    print(f"thoughts_len = {len(thoughts)}")
    print(f"finished = {finished}")
    print(f"generating = {gen}")
    print(f"message_count = {msg_count}")
    print(f"status = {status}")
    print(f"\n--- ОТВЕТ (первые 2000 символов) ---")
    print(answer[:2000])
    print(f"\n--- МЫСЛИ (первые 500 символов) ---")
    print(thoughts[:500])

    if answer and "Exploring Trade Tensions" not in answer:
        print("\n[OK] УСПЕХ: ответ извлечён, мысли отфильтрованы")
        return 0
    else:
        print("\n[FAIL] ПРОБЛЕМА: ответ пуст или содержат мысли")
        return 1


if __name__ == "__main__":
    sys.exit(main())