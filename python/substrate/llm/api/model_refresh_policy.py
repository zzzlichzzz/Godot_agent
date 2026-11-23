"""D108: an explicit provider key gates model refresh and automatic discovery."""
MISSING_KEY = 'Нужен ключ провайдера'


def has_key(provider_id, registry, keys):
    return keys.has_key(provider_id, registry.env_names_for(provider_id))


def can_fetch(provider_id, registry, keys):
    return (has_key(provider_id, registry, keys) and bool(registry.models_url(provider_id))
            and not registry.unavailable_reason(provider_id))


def refusal():
    return dict(error=MISSING_KEY, error_code='no_key', kind='denied',
                hint='Введите ключ выбранного провайдера в настройках API.')
