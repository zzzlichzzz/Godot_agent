# ADR-0082 — plain proof существующего parent перед эффектом T-B

2026-11-21, R-12/R-20/R-22, дополнение ADR0080.

NativePlanner уже отвергает nonplain существующие ancestors при read-only
подготовке. AtomicFileWriter.directory_identity возвращает пустой proof для
reparse/symlink/non-directory. Но между prepare и apply проверялись только
созданные mkdir ancestors: ordinary proof существующего parent мог стать
недоступен, а tagged assistant plan продолжал file write.

Два самостоятельно написанных port-attack cases (empty proof/OSError) получили
на копии текущего B два настоящих failures через Agent/confirm. Это safety,
не native golden и не доказательство реальной junction-race на Windows.

Решение: только PREPARED detail.tool=assistant.write проверяет plain proof всех
ancestors перед forward/inverse файловым эффектом в существующем executor.
Пустой/unavailable proof даёт typed refusal до эффекта. Созданные ancestors
дополнительно обязаны совпадать с receipt; pre-existing parents никогда не
присваиваются агенту и не удаляются. Historical untagged plans не меняются.

До реализации production должны получить те же два RED IDs; затем same-ID
GREEN×2 и killed/exact-restored plain-proof mutant. Все финальные пары начинаются
снова после стабилизации; нет нового writer, native apply или общих exemptions.
