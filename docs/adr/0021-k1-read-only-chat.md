# ADR-0021 — K1 read-only public chat (D70–D73)

D72 заменяет противоречивый bootstrap freeze D70.3/5; D73 заменяет
STRING-only envelope D71.2. Это санкционированная интеграция, не изменение
kernel/protocol и не расширение write/exec/browser/editor/HTTP/MCP/NN.

- Public MODULE assistant.chat, provides chat, requires chat_gateway, corpus.
- Domain возвращает финальную STRING; app единственный object boundary.
  Required closed object: text, turns_used, actions_executed, judge_summary.
- Gateway ленив, использует pinned native ApiBackend/agent_prompts/parser,
  shared lock и profile-only storage по D53/D55, finally восстановления.
- Native judge вызывается с raw STRING; read действия идут через dispatcher.
  Явный read allowlist плюс registry effects, нет plan/confirm/apply/rollback.
- Без real-provider авторизации проверяется только synthetic offline SSE.
  Обёртка внешнего runner изолирует транспорт; checker и public route настоящие.
- Bootstrap: ровно две вставки D72, D65 окружение byte-exact. Eight D73 B-list
  public count/advertisement deltas и scoped D70 AST site только после genuine RED.

Текущая стадия6: RED→code→same-ID GREEN; ordinary corpus10×2/byte-equal,
selfcheck assistant.chat ok/exit0×2 (29unit/10corpus),4mutants killed/0survivors
с exact restore, final gates×2 и full7973pass+2historic skips×2/52new.
Frozen230/API253/project288 ×2;7actual CLI/probes exit0/no project writes.
D73 seven named token-only updates; eighth selector unchanged (count already45).
D72 additional resource_ops port-order token отдельно RED→GREEN/bytes exact.
Classification new/MODULE_ready=true, независимое принятие ещё **не** произошло.
Готовится seal LAST/полный byte+CRC ZIP; real-provider/editor/browser verification
не выполнялось и отдельно не санкционировано.
