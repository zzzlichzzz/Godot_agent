"""Pure project/policy binding for plans requiring explicit confirmation."""
from python.kernel.errors import AppError

def policy_snapshot(policy):
    return {'project_root':str(policy.project_root).replace('\\','/').casefold(),
            'agent_dir':str(policy.agent_dir).replace('\\','/').casefold(),
            'allow_addons':bool(policy.allow_addons),'allow_self_edit':bool(policy.allow_self_edit)}

def require_explicit_confirmation(entries, policy):
    prepared=next((r for r in entries if r.get('state')=='PREPARED'),{})
    detail=prepared.get('detail') or {}
    if detail.get('requires_confirmation') is not True: return
    if detail.get('policy')!=policy_snapshot(policy):
        raise AppError('denied','проект или политика изменились после предпросмотра')
    digest=(prepared.get('plan') or {}).get('digest')
    approved=any(r.get('state')=='USER_CONFIRMED' and r.get('digest')==digest and r.get('approved') is True for r in entries)
    if not approved:
        raise AppError('denied','план требует явного подтверждения пользователя')
