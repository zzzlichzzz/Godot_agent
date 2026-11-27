# ADR-0074: T1 native tools, opt-in closure and exact-source process permission

Status: implemented under T1 §2 delegated conflict resolution; independent audit pending.

Accepted K1 registry (50 aliases/84 LF) and all native accepted bytes remain
unchanged. T1 has a separate lazy NativeBindings.register activation, with strict
identity and owned-alias rollback. Explicit function-card use requires the native
helper (corrected librarian1238–1246); therefore D48 exclusion is reversed only for
the helper, never for excluded ML/NN files. log_reader is scheduled from T-C early
because gather_context imports it unconditionally.

D74 permits only the exact split_gd path AND complete SHA256 AND native call byte
offset. A byte change, extra run/bind, changed argv, shell keyword, or renamed file
fails closed. SEC-02/PROC_ALLOWED/browser properties are unchanged. Five measured
exact-path line caps supplement, never modify, D60 caps/default/entry limits.

D75 adds exactly one scoped method-local import site to the existing activation
test. Base50 historical observations and unactivated bootstrap remain unchanged.
Native write executors are references, not public write tools; T-B must compile
effects into the existing confirmed journalled write funnel.

Evidence: external T1-20261121; native29×2, genuine missing-code/gate/import RED,
same-ID GREEN and mutations required before stage completion.
