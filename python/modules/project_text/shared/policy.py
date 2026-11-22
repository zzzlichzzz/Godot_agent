"""Pure native read classification from resolved identities; D20, SEC-24."""


def can_read_project_path(rel, policy, agent_rel):
    path = rel.casefold()
    agent = agent_rel.casefold() if agent_rel else None
    if path == ".agent_history" or path.startswith(".agent_history/"):
        return False
    if agent and (path == agent or path.startswith(agent + "/")):
        return bool(policy.allow_self_edit)
    if path == "addons" or path.startswith("addons/"):
        return bool(agent and policy.allow_addons)
    return True
