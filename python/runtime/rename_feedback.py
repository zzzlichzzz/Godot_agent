"""Bind a read-only completion to the Qwen conversation that proposed the rename."""
import json

from python.substrate.assistant.saved_page import site_for_record
from python.substrate.assistant.provider_conversation import permanent
from python.substrate.context.librarian_read import _LOCK


def install(session, gateway, selected, system):
    def destination(record, cid):
        if not record or record.get('id') != cid or record.get('kind') == 'api':
            return None
        site = site_for_record(record)
        return permanent(site, record.get('url')) if site and site['id'] == 'qwen' else None

    def report(cid, url, facts):
        with _LOCK:
            if destination(selected(), cid) != url or gateway.selected_page.cid != cid:
                return None
            prompt = ('Результат сервера после подтверждения rename_symbol. Операция уже применена. '
                      'Кратко сообщи пользователю результат по этим данным. Не повторяй действие, '
                      'не предлагай новых команд и не утверждай, что проверял игру или тип объекта.\n'
                      + json.dumps(facts, ensure_ascii=False))
            reply = gateway.send(prompt, system_text=system)
            if (reply.get('finish_reason') == 'stop' and reply.get('done') and not reply.get('parse_error')
                    and (reply.get('action') or {}).get('action') in (None, 'done', 'none')):
                return reply['text'].strip() or None
            return None  # Never dispatch an action from a receipt summary.

    session.rename_destination = lambda cid: destination(gateway._record, cid)
    session.rename_report = report
