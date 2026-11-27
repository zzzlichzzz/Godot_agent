"""A committed rename receipt can be reported once, independently of applying it."""
from flask import jsonify, request


def offer(session, plan, result, paths):
    session.report_ticket = None
    owner = session.pending_chat
    if not owner or not plan.get('rename_report') or result['state'] != 'COMMITTED':
        return {}
    url, names = plan['rename_report']
    ticket = dict(chat_id=owner, entry_id=result['entry_id'])
    facts = dict(names, state='COMMITTED', changed_files=len(paths), warnings=len(plan.get('warnings', [])))
    session.report_ticket = (ticket, url, facts)
    return {'rename_report_request': ticket}


def register(bp, session):
    @bp.post('/chat/rename/report')
    def report():
        body = request.get_json()
        key = body.get('turn_id')
        if key is not None and not session.turns.valid(key):
            return jsonify(error='Invalid turn_id'), 400
        with session.lock:
            issued = session.report_ticket
            if not issued or any(body.get(k) != v for k, v in issued[0].items()):
                return jsonify(error='Нет итога переименования для этого чата'), 409
            ticket, url, facts = issued
            session.report_ticket = None
            if (session.last_receipt or {}).get('entry_id') != ticket['entry_id'] or session.pending:
                return jsonify(error='Состояние проекта уже изменилось'), 409
            cid = ticket['chat_id']
            turn = session.turn_context.set((cid, None))
            token = session.turns.begin(key)
            session.start_turn(False)
            session.clock.data['kind'] = 'rename_report'
            answer = None
            try:
                if not session.turns.cancelled():
                    answer = session.rename_report(cid, url, facts)
            except Exception:
                pass  # Provider/navigation failure after commit must not invite a write retry.
            finally:
                if session.turns.finish(token): answer = None
                session.finish_turn('final' if answer else 'error')
                session.turn_context.reset(turn)
            if answer:
                return jsonify(ok=True, answer=answer, **session.remember(cid, [('agent', answer)]))
            note = 'Переименование применено. Итоговый ответ Qwen не получен.'
            return jsonify(ok=True, report_warning=note, **session.remember(cid, [('system', note)]))
