# -*- coding: utf-8 -*-
"""Хранилище ключей API и настроек прокси.

ГДЕ ЛЕЖИТ. Ключи ОБЩИЕ для всех проектов Godot: пользователь вводит ключ
один раз, а не в каждой игре заново. Поэтому файл живёт не в user:// (это
папка КОНКРЕТНОГО проекта) и тем более не рядом с аддоном, а в личной папке
настроек пользователя:
    Windows: %APPDATA%\\Godot_agent\\api_keys.json
    Linux:   ~/.config/godot_agent/api_keys.json
    macOS:   ~/Library/Application Support/godot_agent/api_keys.json

ПОЧЕМУ НЕ В ПРОЕКТЕ. Папка проекта — это git-репозиторий пользователя и
источник экспортируемой игры. Ключ, попавший туда, рано или поздно уедет
в публичный коммит или в собранную игру. Правило простое: ничего секретного
внутри рабочей области, даже временно.

ЧТО ЭТО НЕ ДЕЛАЕТ. Ключ хранится ОТКРЫТЫМ ТЕКСТОМ — так же, как это делают
большинство инструментов разработчика. Привязка шифротекста к аккаунту ОС
(DPAPI на Windows, keychain на macOS/Linux) описана в ОТЛОЖЕНО.md как
следующий шаг: она защищает от бытовых утечек (случайный коммит, синхронизация
AppData в облако, передача папки другому человеку), но не от программы,
запущенной под тем же пользователем. Своё шифрование с зашитым в код ключом
писать НЕЛЬЗЯ: оно не защищает ни от чего и создаёт ложную уверенность.

ГЛАВНЫЙ ИНВАРИАНТ МОДУЛЯ. Наружу (в панель, в HTTP-ответ, в лог, в консоль)
уходит только маска вида "sk-or-…3f9a". Сырой ключ отдаёт единственная
функция resolve_key(), и её результат имеет право видеть только транспорт.
Причина конкретная: dashboard.py дублирует весь stdout сервера на HTTP-страницу
/dashboard, поэтому напечатанный ключ мгновенно становится доступен по сети.
Для страховки есть redact() — им прогоняются любые тексты ошибок от провайдера
перед печатью.
"""
import copy
import json
import os
import sys
import time

_FILE_NAME = "api_keys.json"
_APP_DIR_NAME = "Godot_agent"

# Переменная окружения, задающая папку настроек в обход системной. Нужна
# тестам (чтобы не трогать настоящие ключи разработчика) и переносимым сборкам.
ENV_CONFIG_DIR = "GODOT_AGENT_CONFIG_DIR"
DEFAULT_DOH_URL = "https://xbox-dns.ru/dns-query"

_DEFAULT_CONFIG = {
    # 2: ключ на провайдера стал СПИСКОМ ключей (см. _normalize_keys).
    # Поле рядом с данными, а не в коде: файл общий для всех проектов Godot и
    # переживает обновления аддона, поэтому по нему видно, чем он записан.
    "version": 2,
    # provider_id -> {"keys": [{"key", "cooldown_until", "cooldown_reason"}],
    #                 "model": str, "base_url": str}
    #
    # ПОЧЕМУ СПИСОК, А НЕ ОДИН КЛЮЧ. У бесплатных тарифов квота считается НА
    # КЛЮЧ, а не на модель: когда OpenRouter или Groq говорит «суточный лимит
    # исчерпан», второй ключ того же провайдера работает как ни в чём не бывало.
    # С одним ключом единственным выходом было ждать до сброса квоты — часы
    # простоя при полностью рабочем втором ключе в кармане.
    #
    # cooldown_until хранится РЯДОМ С КЛЮЧОМ намеренно: так удаление ключа
    # автоматически убирает и память о его исчерпании. Отдельная таблица,
    # ссылающаяся на ключи по индексу или хэшу, однажды разошлась бы со списком.
    "providers": {},
    # Что предложить при создании НОВОГО чата (у самого чата провайдер и
    # модель хранятся в его записи и потом не меняются).
    "defaults": {"provider": "", "model": ""},
    "proxy": {"enabled": False, "host": "", "port": 0, "user": "", "password": ""},
    # DNS over HTTPS: адрес доверенного резолвера. Помогает, когда провайдер
    # не разрешается системным DNS (подмена/NXDOMAIN у интернет-провайдера).
    # От блокировки по IP или SNI не спасает — там нужен прокси.
    "dns": {"enabled": True, "url": DEFAULT_DOH_URL},
    # ЧТО ЗДЕСЬ. Наблюдения о провайдерах, полученные НА ЭТОЙ МАШИНЕ: сколько
    # у провайдера моделей и сколько из них бесплатных, чем закончилась
    # последняя проверка подключения. Не секреты — уходит в панель целиком.
    #
    # ЗАЧЕМ ХРАНИТЬ. Панель показывает провайдеров списком и должна как-то
    # сказать «здесь 57 бесплатных моделей». Считать это на месте нельзя:
    # /models у большинства провайдеров требует ключа, а ключа у ещё не
    # выбранного провайдера по определению нет. Опрашивать всех подряд при
    # открытии списка — это десяток запросов ради подписи под названием.
    # Поэтому число берётся из последнего РЕАЛЬНОГО обновления списка моделей
    # и показывается вместе с датой: «57 бесплатных, проверено 3 дня назад»
    # честно, а «57 бесплатных» без даты — уже обещание за сервис.
    #
    # ОТКУДА БЕРЁТСЯ. Из обновления списка моделей: и по кнопке «Обновить», и
    # автоматически (providers.autoscan_targets + маршрут /api/models/scan).
    # Автообновление появилось потому, что без него числа были ТОЛЬКО у
    # провайдеров, которых пользователь открывал руками, а фильтр «с
    # бесплатными» показывал ровно их — то есть выглядел как утверждение, что
    # у остальных бесплатных моделей нет.
    #
    # ДВА СЧЁТЧИКА БЕСПЛАТНЫХ, А НЕ ОДИН. models_free — измерено по ОТВЕТУ
    # ПРОВАЙДЕРА (суффикс :free/-free, нулевая цена в pricing).
    # models_free_catalog — то же число по справочнику models.dev
    # (catalog.py). Они расходятся, и это не шум: у Opencode Zen модель
    # big-pickle имеет в каталоге нулевую цену, а по суффиксу выглядит
    # платной. Свести их в одно число значит потерять ответ на вопрос «кто
    # это утверждает», а именно он и решает, верить ли подписи.
    #
    # provider_id -> {"models_total": int, "models_free": int,
    #                 "models_free_catalog": int,
    #                 "models_at": float, "models_error": str,
    #                 "models_try_at": float, "test_ok": bool,
    #                 "test_at": float, "test_ms": int}
    "provider_stats": {},
    # ПОЛНЫЙ СПИСОК ПРОВАЙДЕРОВ ИЗ КАТАЛОГА models.dev — по явному включению.
    #
    # enabled=False по умолчанию НАМЕРЕННО. Наши семь записей разобраны руками:
    # у AgentRouter известен белый список клиентов, у Opencode Zen известна
    # ловушка api.opencode.ai (отвечает 200 с текстом «Not Found»), у посредника
    # выставлен connect_timeout=150. Про остальные 163 записи каталога не
    # проверено НИЧЕГО. Показывать их вперемешку с разобранными значит стереть
    # разницу между «проверено» и «взято из справочника»; поэтому они
    # включаются осознанно и живут в отдельной группе с пометкой.
    #
    # Выбранные из каталога отдельным списком НЕ хранятся: провайдер становится
    # «своим», как только у него появляется запись в разделе providers выше
    # (ключ, модель или адрес). Второй список дублировал бы это состояние и
    # однажды разошёлся бы с ним.
    "catalog": {"enabled": False},
    # НЕДАВНО ВЫБРАННЫЕ МОДЕЛИ — [{"provider": str, "model": str}], свежие
    # первыми. Нужны, чтобы в списке из четырёхсот моделей то, чем человек
    # работает, стояло сверху и не искалось заново каждый раз.
    #
    # Отдельный список, а не флажок на записи модели: моделей у провайдера
    # сотни, они приходят из кэша живого ответа и переписываются при каждом
    # обновлении списка — пометка «недавняя» на них не выжила бы. И это ПАРЫ:
    # одно и то же имя модели бывает у нескольких провайдеров.
    "recent": [],
}



# ---------------------------------------------------------------------------
# Расположение файла
# ---------------------------------------------------------------------------

def config_dir():
    u"""Личная папка настроек агента (создаётся при первом обращении).

    ПОЧЕМУ ТУТ ЗАПОМИНАНИЕ, А НЕ makedirs КАЖДЫЙ РАЗ. Эта функция стоит в самом
    низу горячего пути: через неё идут config_path(), catalog.catalog_path() и
    model_cache.cache_path(), а их дёргают на каждую проверку готовности
    провайдера. С полным списком каталога это сто шестьдесят пять провайдеров за
    один запрос настроек, то есть под тысячу вызовов makedirs — замерено 0.3 мс
    на вызов и почти секунда на сборку списка провайдеров.
    """
    override = (os.environ.get(ENV_CONFIG_DIR) or "").strip()
    cached = _dirs_ready.get(override)
    if cached is not None:
        return cached
    if override:
        base = override
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA")
                            or os.path.expanduser("~"), _APP_DIR_NAME)
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/godot_agent")
    else:
        xdg = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
        base = os.path.join(xdg or os.path.expanduser("~/.config"), "godot_agent")
    try:
        os.makedirs(base, exist_ok=True)
        # Запоминаем ТОЛЬКО после удачного создания: иначе неудача закрепилась бы
        # на всю сессию и папка не появилась бы уже никогда.
        _dirs_ready[override] = base
    except Exception as e:
        print("[api_keys] Не удалось создать папку настроек %s (%s)" % (base, e))
    return base


# Папка настроек по значению переменной окружения (см. config_dir). Ключ —
# значение ENV_CONFIG_DIR, поэтому тесты, подменяющие его на ходу, получают свою
# папку, а не запомненную чужую.
_dirs_ready = {}


def config_path():
    """Полный путь к файлу настроек — панель показывает его пользователю,
    чтобы было видно, где лежит ключ, и можно было удалить руками."""
    return os.path.join(config_dir(), _FILE_NAME)


# ---------------------------------------------------------------------------
# Чтение и запись
# ---------------------------------------------------------------------------

def _int_or(value, default=-1):
    try:
        return int(value)
    except Exception:
        return default


def _float_or(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _clean_stats(rec):
    """Одна запись наблюдений о провайдере в известном виде.

    Через эту функцию проходят и чтение с диска, и запись: иначе набор полей
    в файле и набор полей, уходящий в панель, со временем разъедутся.

    -1 в счётчиках означает «не измеряли» и отличается от честного 0
    («моделей нет» или «бесплатных нет»). Пустое значение вместо этого не
    подошло бы: панель не смогла бы отличить «не проверяли» от «проверили и
    ничего не нашли», а это разные подписи под провайдером.
    """
    rec = rec if isinstance(rec, dict) else {}
    out = {
        "models_total": _int_or(rec.get("models_total"), -1),
        "models_free": _int_or(rec.get("models_free"), -1),
        # Бесплатные ПО КАТАЛОГУ models.dev — отдельным счётчиком от
        # measured-по-ответу-провайдера models_free. Не «уточнение» и не
        # «замена»: это утверждение другого источника о том же списке моделей,
        # и панель подписывает его отдельно («по каталогу»). Тот же -1
        # означает «не считали»: пока каталог не загружен, у провайдера просто
        # нет второго мнения, и врать нулём нельзя.
        #
        # ВНИМАНИЕ: новое поле обязано появиться ЗДЕСЬ, а не только в
        # _DEFAULT_CONFIG. _load() собирает конфигурацию заново по известным
        # полям и раздел provider_stats пропускает через эту функцию — поле,
        # добавленное мимо неё, исправно сохранялось бы и молча пропадало при
        # каждом чтении.
        "models_free_catalog": _int_or(rec.get("models_free_catalog"), -1),
        "models_at": _float_or(rec.get("models_at"), 0.0),
    }
    # НЕУДАЧНАЯ попытка получить список моделей. Отдельно от отсутствия
    # наблюдений: «список ещё не загружался» и «список загрузить не удалось,
    # вот почему» — разные подписи, и вторая избавляет от самого частого
    # вывода «плагин просто ничего не делает». Поля нет, пока попытки не было
    # или пока последняя попытка была успешной (record_models_stats их
    # снимает) — иначе старая ошибка висела бы рядом со свежими числами.
    if rec.get("models_error"):
        out["models_error"] = str(rec.get("models_error"))
        out["models_try_at"] = _float_or(rec.get("models_try_at"), 0.0)
    # Результата проверки подключения может не быть вовсе — тогда полей нет,
    # а не стоит False: «проверка не удалась» и «проверки не было» для
    # пользователя означают совершенно разное.
    if rec.get("test_at"):
        out["test_ok"] = bool(rec.get("test_ok"))
        out["test_at"] = _float_or(rec.get("test_at"), 0.0)
        out["test_ms"] = _int_or(rec.get("test_ms"), 0)
    return out


def _normalize_keys(rec):
    """Список ключей провайдера из записи файла, в любом из двух форматов.

    МИГРАЦИЯ БЕЗ ОТДЕЛЬНОГО ШАГА. Файл версии 1 хранил один ключ строкой
    ("key": "sk-..."). Здесь он превращается в список из одного элемента прямо
    при чтении, поэтому обновление аддона ничего не спрашивает у пользователя и
    ничего не теряет. Обратной миграции нет и не будет: старая версия увидела бы
    в новом файле пустой "key" и решила, что ключа нет вовсе — поэтому поле
    "key" на запись больше не выводится, чтобы не выглядело, будто им ещё
    можно пользоваться.

    Порядок ключей сохраняется: это порядок, в котором их пробуют, и
    пользователь вправе им управлять (первым ставит основной).

    Дубликаты убираются: два одинаковых ключа в списке означали бы два
    гарантированно провальных запроса вместо одного при исчерпании квоты.
    """
    out = []
    seen = set()

    def _add(raw, until=0.0, reason=""):
        k = str(raw or "").strip()
        if not k or k in seen:
            return
        seen.add(k)
        out.append({"key": k,
                    "cooldown_until": _float_or(until, 0.0),
                    "cooldown_reason": str(reason or "")})

    raw_list = rec.get("keys")
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict):
                _add(item.get("key"), item.get("cooldown_until"),
                     item.get("cooldown_reason"))
            else:
                # Список простых строк тоже принимаем: файл мог быть поправлен
                # руками, и отказываться от такого ключа было бы неуважением к
                # человеку, который его туда вписал.
                _add(item)
    # Поле старого формата читается ПОСЛЕ списка и только как ещё один ключ:
    # если файл писали и новой, и старой версией, потерять ни один нельзя.
    _add(rec.get("key"))
    return out


def _load():
    """Настройки с диска. Любая проблема чтения — пустая конфигурация:
    сервер обязан подняться даже с испорченным файлом настроек.

    ВНИМАНИЕ ПРИ ДОБАВЛЕНИИ НОВЫХ РАЗДЕЛОВ. Конфигурация здесь не
    объединяется с файлом, а СОБИРАЕТСЯ ЗАНОВО по полям, которые эта функция
    знает: всё прочее из файла отбрасывается. Так сделано намеренно (испорченное
    или чужое поле не доедет до кода), но у этого есть следствие: раздел,
    добавленный только в _DEFAULT_CONFIG и в запись, будет исправно
    сохраняться и молча пропадать при каждом чтении. Новый раздел надо
    разобрать ЗДЕСЬ.

    ПОЧЕМУ ТУТ КЭШ. Функция вызывается по несколько раз на КАЖДОГО провайдера
    (ключ, модель, адрес, наблюдения), и с полным списком каталога это шестьсот
    с лишним чтений файла за один запрос настроек — замерено 0.176 мс на вызов,
    то есть больше сотни миллисекунд на пустом месте. Ключ кэша — время
    изменения и размер файла, поэтому правка настроек любым другим процессом
    видна сразу; _save() вдобавок сбрасывает кэш явно, чтобы запись и чтение в
    пределах одного тика часов не разошлись.
    """
    p = config_path()
    key = _stat_key(p)
    if _cfg_cache["key"] == key:
        # Копия ОБЯЗАТЕЛЬНА: вызывающие меняют результат и передают в _save
        # (set_key, set_model, _update_stats). Без копии они правили бы кэш.
        return copy.deepcopy(_cfg_cache["value"])
    cfg = copy.deepcopy(_DEFAULT_CONFIG)
    if not os.path.isfile(p):
        _cfg_cache["key"] = key
        _cfg_cache["value"] = cfg
        return copy.deepcopy(cfg)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("[api_keys] Файл настроек не читается (%s) — работаю с пустым." % e)
        return cfg
    if not isinstance(data, dict):
        return cfg
    if isinstance(data.get("providers"), dict):
        for pid, rec in data["providers"].items():
            if isinstance(rec, dict):
                cfg["providers"][str(pid)] = {
                    "keys": _normalize_keys(rec),
                    "model": str(rec.get("model") or ""),
                    "base_url": str(rec.get("base_url") or ""),
                }
    if isinstance(data.get("provider_stats"), dict):
        for pid, rec in data["provider_stats"].items():
            if isinstance(rec, dict):
                cfg["provider_stats"][str(pid)] = _clean_stats(rec)
    if isinstance(data.get("defaults"), dict):
        cfg["defaults"]["provider"] = str(data["defaults"].get("provider") or "")
        cfg["defaults"]["model"] = str(data["defaults"].get("model") or "")
    if isinstance(data.get("proxy"), dict):
        pr = data["proxy"]
        try:
            port = int(pr.get("port") or 0)
        except Exception:
            port = 0
        cfg["proxy"] = {
            "enabled": bool(pr.get("enabled")),
            "host": str(pr.get("host") or "").strip(),
            "port": port,
            "user": str(pr.get("user") or ""),
            "password": str(pr.get("password") or ""),
        }
    if isinstance(data.get("dns"), dict):
        cfg["dns"] = {
            "enabled": bool(data["dns"].get("enabled")),
            "url": str(data["dns"].get("url") or "").strip(),
        }
    if isinstance(data.get("catalog"), dict):
        # Раздел разбирается ЗДЕСЬ, а не только в _DEFAULT_CONFIG: см.
        # предупреждение в начале функции. Добавленный мимо этого места он
        # исправно сохранялся бы и молча пропадал при каждом чтении, то есть
        # переключатель сбрасывался бы сам собой после перезапуска редактора.
        cfg["catalog"] = {"enabled": bool(data["catalog"].get("enabled"))}
    if isinstance(data.get("recent"), list):
        # Тоже разбирается ЗДЕСЬ (см. предупреждение в начале функции). Пары без
        # обоих полей отбрасываются молча: список подсказок не то место, где
        # стоит спорить с испорченным файлом.
        recent = []
        for item in data["recent"][:RECENT_LIMIT]:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("provider") or "").strip()
            mid = str(item.get("model") or "").strip()
            if pid and mid:
                recent.append({"provider": pid, "model": mid})
        cfg["recent"] = recent
    _cfg_cache["key"] = key
    _cfg_cache["value"] = cfg
    return copy.deepcopy(cfg)


def _stat_key(path):
    """(время изменения, размер) файла или None — этим кэш узнаёт, что файл
    переписали, не читая его целиком."""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except Exception:
        return None


# Разобранные настройки из прошлого чтения. key=False означает «ещё ни разу»:
# None — законное значение для отсутствующего файла.
_cfg_cache = {"key": False, "value": None}


def _invalidate_cfg():
    _cfg_cache["key"] = False
    _cfg_cache["value"] = None


def _cfg():
    u"""Настройки ТОЛЬКО ДЛЯ ЧТЕНИЯ, без копии.

    ЗАЧЕМ ОТДЕЛЬНАЯ ФУНКЦИЯ. _load() отдаёт глубокую копию, потому что
    вызывающие её меняют и передают в _save(). Копия стоит 0.1 мс (замерено), а
    геттеры ниже дёргают настройки по несколько раз на КАЖДОГО провайдера: с
    полным списком каталога это шестьсот вызовов за один запрос настроек, то
    есть больше семидесяти миллисекунд на копирование того, что никто не менял.

    КТО ЭТИМ ПОЛЬЗУЕТСЯ, НЕ ИМЕЕТ ПРАВА МЕНЯТЬ РЕЗУЛЬТАТ. Изменение уедет в
    кэш и будет жить до следующей записи файла — то есть настройки разойдутся с
    диском, и понять это по симптомам почти невозможно. Меняете — берите
    _load().
    """
    p = config_path()
    key = _stat_key(p)
    if _cfg_cache["key"] == key and _cfg_cache["value"] is not None:
        return _cfg_cache["value"]
    _load()  # он заполнит кэш
    return _cfg_cache["value"] or copy.deepcopy(_DEFAULT_CONFIG)


def _save(cfg):
    """Запись через временный файл + os.replace: обрыв на середине не
    оставляет полуфабрикат вместо настроек. На posix права 0600."""
    p = config_path()
    tmp = p + ".tmp"
    # Кэш чтения сбрасываем ДО записи: если сохранение упадёт на середине,
    # следующее чтение обязано пойти на диск, а не отдать то, что мы собирались
    # записать. Время изменения файла тоже сторож, но в пределах одного тика
    # часов оно может не измениться — это как раз случай двух сохранений подряд.
    _invalidate_cfg()
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        if os.name != "nt":
            try:
                os.chmod(tmp, 0o600)
            except Exception:
                pass
        os.replace(tmp, p)
        return True
    except Exception as e:
        print("[api_keys] Не удалось сохранить настройки (%s)" % e)
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Маскирование
# ---------------------------------------------------------------------------

def mask(key):
    """Безопасное представление ключа: начало и последние 4 символа.

    Начало у ключей осмысленное ("sk-or-", "gsk_", "AIza") — по нему
    пользователь узнаёт свой ключ, а восстановить его по маске нельзя.

    Многоточие строго ASCII ("..."), а не символ U+2026: маска попадает в
    print, а в кодировке консоли Windows (cp866) U+2026 отсутствует — вывод
    сервера не должен падать на печати служебного сообщения.
    """
    k = str(key or "")
    if not k:
        return ""
    if len(k) <= 8:
        return "****"
    head = k[:6] if len(k) > 14 else k[:3]
    return "%s...%s" % (head, k[-4:])


def redact(text):
    """Убирает из произвольного текста все известные секреты.

    Через эту функцию проходит ВЕСЬ вывод сервера (dashboard._Tee), а не только
    сообщения об ошибках. Причина: журнал stdout дублируется на HTTP-страницу
    /dashboard, и одного случайного print с заголовками запроса достаточно,
    чтобы ключ стал доступен по сети. Полагаться на аккуратность каждого
    будущего print нельзя — надёжнее один барьер на выходе.

    Список секретов кэшируется: функция вызывается на каждой строке вывода, а
    чтение файла настроек на каждую строку сделало бы сервер заметно медленнее.
    Кэш сбрасывается при любом изменении ключа или пароля прокси.
    """
    s = str(text or "")
    if not s:
        return s
    for secret in _secrets():
        if secret in s:
            s = s.replace(secret, mask(secret))
    return s


# Кэш секретов для redact(). None означает «надо перечитать».
_secrets_cache = {"list": None}


def _invalidate_secrets():
    _secrets_cache["list"] = None


def _secrets():
    """Все известные секреты, от длинных к коротким.

    Порядок важен: короткий секрет может оказаться подстрокой длинного, и
    замена в обратном порядке испортила бы маску длинного.
    """
    cached = _secrets_cache["list"]
    if cached is not None:
        return cached
    found = []
    try:
        cfg = _cfg()
        for rec in (cfg.get("providers") or {}).values():
            # ВСЕ ключи провайдера, а не только рабочий: redact() обязан
            # затирать и исчерпанный ключ — он попадает в тексты ошибок от
            # провайдера ровно так же, как действующий, а весь stdout сервера
            # виден на HTTP-странице /dashboard.
            for item in (rec.get("keys") or []):
                if isinstance(item, dict) and item.get("key"):
                    found.append(item["key"])
        pwd = (cfg.get("proxy") or {}).get("password")
        if pwd:
            found.append(pwd)
    except Exception:
        pass
    for name, value in os.environ.items():
        # Ключи из окружения: наши собственные и общепринятые имена вида
        # OPENROUTER_API_KEY / GROQ_API_KEY / GEMINI_API_KEY.
        if not value or len(value) <= 12:
            continue
        up = name.upper()
        if (up.startswith("GODOT_AGENT_") and up.endswith("_KEY")) \
                or up.endswith("_API_KEY"):
            found.append(value)
    result = sorted({s for s in found if len(s) > 8}, key=len, reverse=True)
    _secrets_cache["list"] = result
    return result


# ---------------------------------------------------------------------------
# Ключи
# ---------------------------------------------------------------------------

def _env_name(provider_id):
    safe = "".join(ch if ch.isalnum() else "_" for ch in str(provider_id or ""))
    return "GODOT_AGENT_%s_KEY" % safe.upper()


def _env_key(provider_id, env_names=()):
    """Ключ из переменных окружения или "" — если его там нет."""
    for name in (_env_name(provider_id),) + tuple(env_names or ()):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return ""


# ИНДЕКС КЛЮЧА ИЗ ОКРУЖЕНИЯ. Отрицательный намеренно: индексы файла — это
# позиции в списке, и смешивать их нельзя. Ключ из окружения в файле не лежит,
# исчерпание для него не запоминается (перезаписать чужую переменную окружения
# мы не вправе) и ротации для него нет — см. usable_keys.
ENV_KEY_INDEX = -1

# Исчерпание, о сроке которого провайдер НЕ сказал: provider_id -> {индекс:
# причина}. Причина хранится вместе с индексом, а не отдельно: объяснение
# «ключи кончились» обязано называть, ЧТО случилось с каждым ключом — иначе
# непонятно, ждать ли сброса квоты, пополнять баланс или менять отозванный ключ.
#
# Живёт только в памяти процесса и умирает с ним — это осознанный выбор, а не
# упрощение. Суточные квоты сбрасываются по расписанию провайдера, которого мы
# не знаем: у одних это полночь UTC, у других скользящее окно. Записать в файл
# выдуманный срок значило бы выдать догадку за факт и заблокировать рабочий
# ключ до утра на пустом месте. Срок из Retry-After — другое дело, он назван
# провайдером и потому попадает на диск (см. note_key_exhausted).
_session_spent = {}


def _forget_session_spent(provider_id):
    """Забыть память об исчерпании ключей провайдера.

    Вызывается при ЛЮБОМ изменении списка ключей: память привязана к позициям в
    списке, и после вставки или удаления она указывала бы на другие ключи.
    """
    _session_spent.pop(str(provider_id or ""), None)


def _key_records(provider_id):
    rec = (_cfg().get("providers") or {}).get(str(provider_id)) or {}
    return list(rec.get("keys") or [])


def _is_on_cooldown(item, now=None):
    """Назван ли провайдером срок, который ещё не истёк."""
    try:
        until = float(item.get("cooldown_until") or 0.0)
    except (TypeError, ValueError):
        return False
    return until > (now if now is not None else time.time())


def usable_keys(provider_id, env_names=()):
    """Ключи, которые СТОИТ пробовать: [(индекс, сырой ключ)], по порядку.

    Единственный источник кандидатов для ротации. Отдаёт СЫРЫЕ ключи, поэтому
    результат имеет право видеть только транспорт — как и у resolve_key.

    ОКРУЖЕНИЕ ОТМЕНЯЕТ РОТАЦИЮ. Если ключ задан переменной окружения, он
    единственный кандидат. Так было и раньше (окружение выигрывало у файла), и
    менять это нельзя: переменную ставят тесты, CI и переносимые сборки, и
    «иногда берём ключ из файла вместо заданного» сделало бы их поведение
    невоспроизводимым.

    Исчерпанные пропускаются: и те, чей срок назвал провайдер (cooldown_until в
    файле), и те, что исчерпались в этой сессии без названного срока.
    """
    env = _env_key(provider_id, env_names)
    if env:
        return [(ENV_KEY_INDEX, env)]
    spent = _session_spent.get(str(provider_id or "")) or {}
    now = time.time()
    out = []
    for idx, item in enumerate(_key_records(provider_id)):
        if idx in spent or _is_on_cooldown(item, now):
            continue
        if item.get("key"):
            out.append((idx, item["key"]))
    return out


def spent_keys(provider_id, env_names=()):
    """Исчерпанные ключи: [(индекс, маска, причина, до_когда_или_0)].

    Нужно объяснению «ключи кончились»: сказать «все %d ключа исчерпаны» без
    перечисления — это просьба к пользователю поверить на слово.
    """
    if _env_key(provider_id, env_names):
        return []
    spent = _session_spent.get(str(provider_id or "")) or {}
    now = time.time()
    out = []
    for idx, item in enumerate(_key_records(provider_id)):
        if not item.get("key"):
            continue
        on_cd = _is_on_cooldown(item, now)
        if idx in spent or on_cd:
            # Причина из файла (срок назвал провайдер) или из памяти сессии.
            reason = str(item.get("cooldown_reason") or "") or spent.get(idx, "")
            out.append((idx, mask(item["key"]), reason,
                        float(item.get("cooldown_until") or 0.0) if on_cd else 0.0))
    return out


def note_key_exhausted(provider_id, index, reason="", retry_after=None):
    """Запомнить, что ключ исчерпан, и больше его не пробовать.

    retry_after — срок в секундах, НАЗВАННЫЙ провайдером (заголовок
    Retry-After). Только он попадает на диск: это факт, а не наша оценка, и он
    переживает перезапуск редактора с сохранением смысла. Без него ключ
    считается исчерпанным до конца работы сервера (см. _session_spent).

    Ключ из окружения не помечается никак: он не наш, менять его состояние мы
    не вправе, а ротации для него всё равно нет.
    """
    pid = str(provider_id or "")
    if not pid or index == ENV_KEY_INDEX:
        return False
    if retry_after is not None:
        try:
            secs = int(float(retry_after))
        except (TypeError, ValueError):
            secs = None
        if secs is not None and secs > 0:
            cfg = _load()
            keys = (cfg["providers"].get(pid) or {}).get("keys") or []
            if 0 <= index < len(keys):
                keys[index]["cooldown_until"] = time.time() + secs
                keys[index]["cooldown_reason"] = str(reason or "")
                _save(cfg)
                print("--> Ключ %s (%s) исчерпан на %d с по слову провайдера: %s"
                      % (index + 1, mask(keys[index].get("key")), secs, reason))
                return True
    _session_spent.setdefault(pid, {})[int(index)] = str(reason or "")
    recs = _key_records(pid)
    shown = mask(recs[index].get("key")) if 0 <= index < len(recs) else "?"
    print("--> Ключ %d (%s) исчерпан до перезапуска сервера: %s"
          % (index + 1, shown, reason))
    return True


def clear_key_cooldowns(provider_id):
    """Забыть, что ключи исчерпаны — и в файле, и в памяти.

    Нужно панели: пользователь знает про свои квоты то, чего не знает агент
    (пополнил баланс, наступило утро), и обязан иметь возможность сказать
    «пробуй заново», не удаляя ключи.
    """
    pid = str(provider_id or "")
    _forget_session_spent(pid)
    cfg = _load()
    keys = (cfg["providers"].get(pid) or {}).get("keys") or []
    changed = False
    for item in keys:
        if item.get("cooldown_until") or item.get("cooldown_reason"):
            item["cooldown_until"] = 0.0
            item["cooldown_reason"] = ""
            changed = True
    return _save(cfg) if changed else True


def resolve_key(provider_id, env_names=()):
    """СЫРОЙ ключ провайдера — тот, которым СТОИТ пробовать сейчас.

    Порядок: переменные окружения, затем первый неисчерпанный ключ из файла.
    Окружение выигрывает намеренно — так тесты и CI подставляют свой ключ, не
    трогая файл разработчика, и так можно запустить агента вообще без записи
    ключа на диск.

    Функция осталась для кода, которому нужен ОДИН ключ и не нужна ротация:
    проверка подключения, обновление списка моделей. Сам чат ходит через
    usable_keys, потому что ему нужны все кандидаты сразу.

    Если исчерпаны все — отдаём первый ключ, а не пустую строку: пустая строка
    означает «ключ не задан», и вызывающий сказал бы пользователю неправду,
    предложив вписать ключ, который у него есть.

    Результат нельзя печатать, логировать и возвращать в HTTP-ответе.
    """
    env = _env_key(provider_id, env_names)
    if env:
        return env
    ready = usable_keys(provider_id, env_names)
    if ready:
        return ready[0][1]
    recs = _key_records(provider_id)
    return str(recs[0].get("key") or "").strip() if recs else ""


def key_source(provider_id, env_names=()):
    """Откуда взялся ключ: "env", "file" или "" (не задан). Нужно панели,
    чтобы не предлагать удалить ключ, заданный переменной окружения."""
    if _env_key(provider_id, env_names):
        return "env"
    return "file" if _key_records(provider_id) else ""


def has_key(provider_id, env_names=()):
    return bool(key_source(provider_id, env_names))


def key_count(provider_id, env_names=()):
    """Сколько ключей задано. Ключ из окружения считается одним."""
    if _env_key(provider_id, env_names):
        return 1
    return len(_key_records(provider_id))


def keys_state(provider_id, env_names=()):
    """Состояние каждого ключа для панели. СЫРЫХ КЛЮЧЕЙ ЗДЕСЬ НЕ БЫВАЕТ.

    [{"index", "masked", "source", "spent", "until", "reason"}] — по порядку
    попыток. until > 0 только когда срок назвал сам провайдер.
    """
    env = _env_key(provider_id, env_names)
    if env:
        return [{"index": ENV_KEY_INDEX, "masked": mask(env), "source": "env",
                 "spent": False, "until": 0.0, "reason": ""}]
    spent = _session_spent.get(str(provider_id or "")) or {}
    now = time.time()
    out = []
    for idx, item in enumerate(_key_records(provider_id)):
        on_cd = _is_on_cooldown(item, now)
        out.append({
            "index": idx,
            "masked": mask(item.get("key")),
            "source": "file",
            "spent": bool(idx in spent or on_cd),
            "until": float(item.get("cooldown_until") or 0.0) if on_cd else 0.0,
            "reason": (str(item.get("cooldown_reason") or "")
                       or spent.get(idx, "")),
        })
    return out


def add_key(provider_id, key):
    """Добавляет ещё один ключ в конец списка. Дубликат не добавляется."""
    pid = str(provider_id or "").strip()
    k = str(key or "").strip()
    if not pid or not k:
        return False
    cfg = _load()
    rec = cfg["providers"].get(pid) or {"keys": [], "model": "", "base_url": ""}
    rec.setdefault("keys", [])
    if any(item.get("key") == k for item in rec["keys"]):
        return True
    rec["keys"].append({"key": k, "cooldown_until": 0.0, "cooldown_reason": ""})
    cfg["providers"][pid] = rec
    ok = _save(cfg)
    _invalidate_secrets()
    _forget_session_spent(pid)
    if ok:
        print("--> Провайдеру %s добавлен ключ №%d (%s)"
              % (pid, len(rec["keys"]), mask(k)))
    return ok


def delete_key_at(provider_id, index):
    """Удаляет ключ по позиции в списке."""
    pid = str(provider_id or "").strip()
    cfg = _load()
    rec = cfg["providers"].get(pid) or {}
    keys = rec.get("keys") or []
    try:
        index = int(index)
    except (TypeError, ValueError):
        return False
    if not (0 <= index < len(keys)):
        return False
    gone = keys.pop(index)
    cfg["providers"][pid] = rec
    ok = _save(cfg)
    _invalidate_secrets()
    _forget_session_spent(pid)
    if ok:
        print("--> У провайдера %s удалён ключ №%d (%s), осталось %d"
              % (pid, index + 1, mask(gone.get("key")), len(keys)))
    return ok


def set_key(provider_id, key):
    """Задаёт ЕДИНСТВЕННЫЙ ключ, заменяя все прежние. Пустое значение
    равносильно удалению всех.

    Осталась ровно с этим смыслом, потому что так её и вызывали: панель
    сохраняет форму с одним полем ключа, и «сохранить» там всегда означало
    «пусть будет вот этот». Добавление второго ключа — отдельное действие
    (add_key), и путать их нельзя: иначе правка первого ключа молча стирала бы
    остальные.
    """
    pid = str(provider_id or "").strip()
    if not pid:
        return False
    k = str(key or "").strip()
    cfg = _load()
    rec = cfg["providers"].get(pid) or {"keys": [], "model": "", "base_url": ""}
    rec["keys"] = ([{"key": k, "cooldown_until": 0.0, "cooldown_reason": ""}]
                   if k else [])
    cfg["providers"][pid] = rec
    ok = _save(cfg)
    _invalidate_secrets()
    _forget_session_spent(pid)
    if ok:
        print("--> Ключ провайдера %s %s (%s)"
              % (pid, "сохранён" if k else "удалён", mask(k) if k else "пусто"))
    return ok


def delete_key(provider_id):
    return set_key(provider_id, "")


# ---------------------------------------------------------------------------
# Модель, свой адрес, значения по умолчанию
# ---------------------------------------------------------------------------

def get_model(provider_id):
    rec = (_cfg().get("providers") or {}).get(str(provider_id)) or {}
    return str(rec.get("model") or "")


def set_model(provider_id, model):
    pid = str(provider_id or "").strip()
    if not pid:
        return False
    cfg = _load()
    rec = (cfg["providers"].get(pid) or {"keys": [], "model": "", "base_url": ""})
    rec["model"] = str(model or "").strip()
    cfg["providers"][pid] = rec
    return _save(cfg)


def get_base_url(provider_id):
    """Свой адрес endpoint'а — для провайдера "custom", для зеркала известного
    провайдера и для локального llama-server. Пусто = адрес из реестра."""
    rec = (_cfg().get("providers") or {}).get(str(provider_id)) or {}
    return str(rec.get("base_url") or "").strip()


def validate_base_url(raw):
    """Разбирает введённый адрес endpoint'а. Возвращает (адрес, ошибка).

    ЗАЧЕМ ПРОВЕРКА. Поле адреса открыто у ВСЕХ провайдеров, а не только у
    «своего адреса»: сервис может переехать, и тогда пользователь исправляет
    адрес сам, не дожидаясь новой версии плагина (base_url_for отдаёт
    приоритет заданному здесь адресу). Обратная сторона — одной опечаткой
    можно сломать заведомо рабочего провайдера, причём молча: запросы начнут
    падать сетевой ошибкой, а причина будет спрятана в поле, которого человек
    не открывал. Ровно так уже вышло с полем прокси, куда вставили адрес
    DNS-over-HTTPS (см. parse_proxy_host).

    Пустая строка — это НЕ ошибка, а «вернуть адрес из реестра»: так работает
    сброс к стандартному значению, и отдельная кнопка для него не нужна.
    """
    s = str(raw or "").strip()
    if not s:
        return "", ""
    if "://" not in s:
        return "", (u"адрес должен начинаться с http:// или https:// "
                    u"(получено «%s»)" % s)
    scheme, rest = s.split("://", 1)
    if scheme.lower() not in ("http", "https"):
        return "", (u"схема «%s://» не поддерживается: нужен http:// или "
                    u"https://" % scheme)
    if not rest.strip(" /"):
        return "", u"в адресе нет хоста, только схема «%s://»" % scheme
    if " " in s:
        return "", u"в адресе не может быть пробелов"
    # Завершающий слэш убираем здесь, а не при сборке запроса: base_url_for
    # тоже его срезает, и два места, делающих одно и то же, однажды разойдутся.
    return s.rstrip("/"), ""


def set_base_url(provider_id, base_url):
    """Сохраняет свой адрес endpoint'а. Возвращает (ok, ошибка).

    Ошибка непустая — адрес НЕ сохранён: принять заведомо нерабочий адрес
    значит оставить пользователя с падающими запросами и невнятной сетевой
    ошибкой вместо понятного отказа сразу.
    """
    pid = str(provider_id or "").strip()
    if not pid:
        return False, u"не указан провайдер"
    clean, err = validate_base_url(base_url)
    if err:
        return False, err
    cfg = _load()
    rec = (cfg["providers"].get(pid) or {"keys": [], "model": "", "base_url": ""})
    rec["base_url"] = clean
    cfg["providers"][pid] = rec
    ok = _save(cfg)
    return ok, ("" if ok else u"не удалось сохранить адрес endpoint'а")


def get_defaults():
    d = _cfg().get("defaults") or {}
    return {"provider": str(d.get("provider") or ""),
            "model": str(d.get("model") or "")}


def set_defaults(provider_id, model=""):
    cfg = _load()
    cfg["defaults"] = {"provider": str(provider_id or "").strip(),
                       "model": str(model or "").strip()}
    return _save(cfg)


# Сколько пар «провайдер + модель» помнить. Список нужен, чтобы поднять наверх
# то, чем человек реально пользуется, а не чтобы вести журнал: десяти хватает на
# любое разумное число моделей в работе, а длинный список сам стал бы свалкой,
# в которой опять надо искать.
RECENT_LIMIT = 10


def get_recent():
    u"""Недавно выбранные пары {provider, model} — свежие первыми."""
    return [dict(item) for item in (_cfg().get("recent") or [])]


def note_model_used(provider_id, model):
    u"""Запомнить, что этой моделью начали работать.

    Вызывается там, где модель ЗАКРЕПЛЯЕТСЯ за чатом (создание чата по ключу и
    смена модели у открытого чата), а не там, где её просто посмотрели в списке:
    иначе «недавние» заполнились бы всем, на что человек нажал из любопытства.

    Хранится ПАРА, а не отдельная модель: одинаковые имена моделей встречаются у
    разных провайдеров (deepseek-chat есть и у deepseek, и у openrouter), и без
    провайдера список поднимал бы наверх модель у того, у кого её нет.
    """
    pid = str(provider_id or "").strip()
    mid = str(model or "").strip()
    if not pid or not mid:
        return False
    cfg = _load()
    rest = [item for item in (cfg.get("recent") or [])
            if not (item.get("provider") == pid and item.get("model") == mid)]
    cfg["recent"] = ([{"provider": pid, "model": mid}] + rest)[:RECENT_LIMIT]
    return _save(cfg)


# ---------------------------------------------------------------------------
# Наблюдения о провайдерах (для списка провайдеров в панели)
# ---------------------------------------------------------------------------

def get_stats(provider_id=None):
    """Наблюдения: по одному провайдеру или все сразу (provider_id=None).

    Провайдер, о котором ничего не известно, отсутствует в словаре — панель
    покажет «не проверялось». Это не то же самое, что запись с нулями.
    """
    all_stats = _cfg().get("provider_stats") or {}
    if provider_id is None:
        return {str(k): _clean_stats(v) for k, v in all_stats.items()}
    rec = all_stats.get(str(provider_id))
    return _clean_stats(rec) if isinstance(rec, dict) else {}


def _update_stats(changes):
    """Меняет наблюдения СРАЗУ У НЕСКОЛЬКИХ провайдеров одной записью файла.

    changes: {provider_id: {поле: значение}}. Ключи внутри записи
    накладываются на уже сохранённые, а не заменяют их целиком: проверка
    подключения не должна стирать числа моделей, и наоборот.

    ПОЧЕМУ ОДНОЙ ЗАПИСЬЮ, А НЕ ПО ПРОВАЙДЕРУ. Автообновление списков проходит
    по нескольким провайдерам за один запрос панели, а _load()/_save() — это
    «прочитать файл целиком, изменить, записать целиком». Пять таких пар подряд
    — пять шансов потерять чужое изменение, пришедшее в это же время другим
    HTTP-запросом (сервер поднят с threaded=True). Один проход оставляет
    единственное окно вместо пяти.
    """
    if not isinstance(changes, dict) or not changes:
        return False
    cfg = _load()
    stats = cfg.get("provider_stats")
    if not isinstance(stats, dict):
        stats = {}
    touched = False
    for provider_id, fields in changes.items():
        pid = str(provider_id or "").strip()
        if not pid or not isinstance(fields, dict):
            continue
        rec = dict(stats.get(pid) or {})
        rec.update(fields)
        stats[pid] = _clean_stats(rec)
        touched = True
    if not touched:
        return False
    cfg["provider_stats"] = stats
    return _save(cfg)


def models_stats_fields(total, free, free_catalog=-1):
    """Поля наблюдения об удачно полученном списке моделей.

    Отдельной функцией, потому что их пишут два места: обновление одного
    провайдера по кнопке и автообновление сразу нескольких. Собранные по месту
    наборы полей однажды разошлись бы, и «обновил кнопкой» начало бы значить не
    то же самое, что «обновилось само».

    ВАЖНО: считать надо по ПОЛНОМУ списку моделей, а не по отфильтрованному
    флажком «только бесплатные». Иначе total совпадёт с free, и у любого
    платного сервиса в списке провайдеров будет написано, что все его модели
    бесплатные, — ровно то враньё, ради предотвращения которого эти числа и
    заводились.

    free_catalog — сколько из ТЕХ ЖЕ моделей считает бесплатными справочник
    models.dev. -1 по умолчанию: пока каталог не загружен, второго мнения нет,
    и подставлять вместо него free значило бы выдать одно измерение за два.
    """
    return {"models_total": _int_or(total, -1),
            "models_free": _int_or(free, -1),
            "models_free_catalog": _int_or(free_catalog, -1),
            "models_at": time.time(),
            # Прошлая неудача снимается: держать её рядом со свежими числами
            # значит показывать пользователю ошибку, которой больше нет.
            "models_error": "",
            "models_try_at": 0.0}


def models_error_fields(message):
    """Поля наблюдения о НЕУДАЧНОЙ попытке получить список моделей.

    Прежние числа моделей при этом не стираются: список, полученный вчера,
    остаётся полезнее пустоты, а свежая ошибка показывается рядом с ним.
    """
    return {"models_error": str(message or u"не удалось получить список моделей"),
            "models_try_at": time.time()}


def record_models_stats(provider_id, total, free, free_catalog=-1):
    """Запоминает, сколько у провайдера моделей и сколько из них бесплатных."""
    return _update_stats({provider_id: models_stats_fields(total, free,
                                                           free_catalog)})


def record_models_error(provider_id, message):
    """Запоминает, что список моделей получить не удалось, и почему."""
    return _update_stats({provider_id: models_error_fields(message)})


def record_test_result(provider_id, ok, elapsed_ms=0):
    """Запоминает исход проверки подключения.

    Проверка — единственное место, где точно известно, что провайдер реально
    отвечает ИМЕННО У ЭТОГО пользователя: с его ключом, его прокси и его
    провайдером интернета. Никакая пометка в реестре этого знать не может.
    """
    return _update_stats({provider_id: {"test_ok": bool(ok),
                                        "test_at": time.time(),
                                        "test_ms": _int_or(elapsed_ms, 0)}})


def record_stats_bulk(changes):
    """Наблюдения сразу по нескольким провайдерам — одной записью файла.

    Ждёт готовые наборы полей: models_stats_fields() для удачи,
    models_error_fields() для неудачи.
    """
    return _update_stats(changes)


def reset_models_stats(provider_id):
    """Забывает всё, что известно о списке моделей провайдера.

    Нужно при СМЕНЕ АДРЕСА endpoint'а: числа «моделей 415, из них бесплатных
    20» относятся к тому адресу, у которого их спросили. Оставить их рядом с
    новым адресом значит выдать за факты о зеркале то, что известно про
    исходный сервис. Обнулённая запись отличается от отсутствующей только тем,
    что providers.models_stale() сразу считает её устаревшей — то есть при
    следующем открытии настроек список спросят заново.
    """
    return _update_stats({provider_id: {"models_total": -1, "models_free": -1,
                                        "models_free_catalog": -1,
                                        "models_at": 0.0, "models_error": "",
                                        "models_try_at": 0.0}})


# ---------------------------------------------------------------------------
# Прокси
# ---------------------------------------------------------------------------

def get_proxy():
    """Настройки прокси БЕЗ пароля — этот вид уходит в панель."""
    pr = _cfg().get("proxy") or {}
    return {"enabled": bool(pr.get("enabled")),
            "host": str(pr.get("host") or ""),
            "port": int(pr.get("port") or 0),
            "user": str(pr.get("user") or ""),
            "has_password": bool(pr.get("password"))}


def parse_proxy_host(raw):
    """Разбирает введённый адрес прокси. Возвращает (host, port, ошибка).

    Зачем разбор, а не «как ввели». Пользователь легко путает прокси с другими
    сетевыми адресами. Реальный случай: в поле хоста ввели адрес
    DNS-over-HTTPS «https://xbox-dns.ru/dns-query», из него собиралось
    «http://https://xbox-dns.ru/dns-query», и ВСЕ запросы к провайдеру падали
    с непонятной ошибкой разрешения имени. Такой ввод надо отклонять сразу и
    объяснять, что не так.

    Принимаем: «host», «host:port», «http://host:port». Путь в адресе для
    прокси невозможен — это признак, что человек вставил адрес сервиса.
    """
    s = str(raw or "").strip()
    if not s:
        return "", 0, ""
    if "://" in s:
        scheme, s = s.split("://", 1)
        if scheme.lower() not in ("http", "https"):
            return "", 0, (u"схема «%s://» не поддерживается: нужен обычный "
                           u"HTTP-прокси (SOCKS пока не поддержан)" % scheme)
    tail = ""
    for sep in ("/", "?", "#"):
        if sep in s:
            s, rest = s.split(sep, 1)
            tail = sep + rest
            break
    if tail and tail.strip("/"):
        return "", 0, (u"адрес прокси не может содержать путь («%s»). Похоже, "
                       u"это адрес сетевого сервиса, а не прокси: нужны только "
                       u"хост и порт, например 127.0.0.1:8080" % tail)
    port = 0
    if s.startswith("["):
        # IPv6 в скобках: [::1]:8080
        end = s.find("]")
        if end > 0:
            hostpart, rest = s[:end + 1], s[end + 1:]
            if rest.startswith(":") and rest[1:].isdigit():
                port = int(rest[1:])
            s = hostpart
    elif ":" in s:
        head, maybe_port = s.rsplit(":", 1)
        if maybe_port.isdigit():
            s, port = head, int(maybe_port)
        else:
            return "", 0, (u"после двоеточия ожидается номер порта, а не «%s»"
                           % maybe_port)
    if not s:
        return "", 0, u"пустой адрес прокси"
    if " " in s:
        return "", 0, u"в адресе прокси не может быть пробелов"
    if port and not (0 < port < 65536):
        return "", 0, u"номер порта вне диапазона 1–65535"
    return s, port, ""


def set_proxy(enabled=None, host=None, port=None, user=None, password=None):
    """Обновляет только переданные поля. password=None оставляет прежний
    пароль (панель не должна пересылать его при каждом изменении хоста).

    Возвращает (ok, ошибка). Ошибка непустая — настройки НЕ сохранены: лучше
    отказать с объяснением, чем принять заведомо нерабочий адрес и оставить
    пользователя с падающими запросами и невнятной сетевой ошибкой.
    """
    cfg = _load()
    pr = cfg.get("proxy") or {}
    if host is not None:
        parsed_host, parsed_port, err = parse_proxy_host(host)
        if err:
            return False, err
        pr["host"] = parsed_host
        # Порт из адреса («host:8080») имеет приоритет над отдельным полем:
        # человек написал его явно.
        if parsed_port:
            pr["port"] = parsed_port
            port = None
    if port is not None:
        try:
            pr["port"] = int(port or 0)
        except Exception:
            pr["port"] = 0
    if user is not None:
        pr["user"] = str(user or "")
    if password is not None:
        pr["password"] = str(password or "")
    if enabled is not None:
        want = bool(enabled)
        if want and not str(pr.get("host") or "").strip():
            return False, (u"нельзя включить прокси без адреса: укажите хост "
                           u"и порт, например 127.0.0.1:8080")
        pr["enabled"] = want
    cfg["proxy"] = pr
    ok = _save(cfg)
    _invalidate_secrets()
    if ok:
        print("--> Прокси: %s %s:%s"
              % ("включён" if pr.get("enabled") else "выключен",
                 pr.get("host") or "-", pr.get("port") or "-"))
    return ok, ("" if ok else u"не удалось сохранить настройки прокси")


def proxy_url():
    """Адрес прокси для транспорта или None.

    Только HTTP(S) CONNECT-прокси: он поддерживается стандартным urllib без
    новых зависимостей, а HTTPS через него остаётся сквозным — прокси видит
    лишь имя хоста и не может прочитать ключ. SOCKS5 потребовал бы PySocks
    в сборке, поэтому отложен до появления реальной потребности.

    ВАЖНО: применять этот адрес только к трафику провайдера. Обращения к
    127.0.0.1 (свой сервер, будущий llama-server, порт отладки браузера)
    через прокси гнать нельзя — за это отвечает транспорт.
    """
    pr = _cfg().get("proxy") or {}
    if not pr.get("enabled"):
        return None
    host = str(pr.get("host") or "").strip()
    if not host:
        return None
    port = int(pr.get("port") or 0)
    auth = ""
    user = str(pr.get("user") or "")
    if user:
        from urllib.parse import quote
        pwd = str(pr.get("password") or "")
        auth = "%s:%s@" % (quote(user, safe=""), quote(pwd, safe=""))
    hostport = "%s:%d" % (host, port) if port else host
    return "http://%s%s" % (auth, hostport)


# ---------------------------------------------------------------------------
# DNS over HTTPS
# ---------------------------------------------------------------------------

def get_dns():
    d = _cfg().get("dns") or {}
    return {"enabled": bool(d.get("enabled")), "url": str(d.get("url") or "")}


def set_dns(enabled=None, url=None):
    """Адрес доверенного DoH-резолвера. Возвращает (ok, ошибка).

    Проверка адреса — здесь, а не в панели: неверный адрес молча превратил бы
    все запросы к провайдеру в непонятные сетевые ошибки, как это уже вышло с
    прокси.
    """
    import doh
    cfg = _load()
    d = cfg.get("dns") or {}
    if url is not None:
        clean, err = doh.validate_url(url)
        if err:
            return False, err
        d["url"] = clean
    if enabled is not None:
        want = bool(enabled)
        if want and not str(d.get("url") or "").strip():
            return False, (u"нельзя включить DoH без адреса сервера: укажите "
                           u"его, например https://dns.example.com/dns-query")
        d["enabled"] = want
    cfg["dns"] = d
    ok = _save(cfg)
    if ok:
        print("--> DoH: %s %s" % ("включён" if d.get("enabled") else "выключен",
                                  d.get("url") or "-"))
        doh.configure(d.get("enabled"), d.get("url"))
    return ok, ("" if ok else u"не удалось сохранить настройки DNS")


def apply_dns_settings():
    """Применяет сохранённые настройки DoH к текущему процессу. Вызывается при
    старте сервера: настройки могли быть заданы в прошлой сессии."""
    import doh
    d = get_dns()
    doh.configure(d["enabled"], d["url"])
    return d


# ---------------------------------------------------------------------------
# Полный список провайдеров из каталога models.dev
# ---------------------------------------------------------------------------

def catalog_enabled():
    """Показывать ли в выборе провайдеров ВСЕХ пригодных из каталога.

    По умолчанию False: см. пояснение к разделу "catalog" в _DEFAULT_CONFIG.
    """
    return bool((_cfg().get("catalog") or {}).get("enabled"))


def set_catalog_enabled(enabled):
    cfg = _load()
    cfg["catalog"] = {"enabled": bool(enabled)}
    ok = _save(cfg)
    if ok:
        print("--> Провайдеры из каталога models.dev: %s"
              % (u"показываются" if cfg["catalog"]["enabled"] else u"скрыты"))
    return ok


def configured_provider_ids():
    u"""Провайдеры, о которых в настройках вообще есть запись.

    Нужно ровно для одного: провайдер, выбранный из полного списка каталога,
    обязан остаться видимым, даже если полный список потом выключили. Иначе
    человек не смог бы ни найти его, ни убрать свой же ключ.

    Пустая запись (все поля пустые) не считается: такие остаются после сброса
    адреса и ключа, и держать из-за них провайдера в списке незачем.
    """
    out = []
    for pid, rec in (_cfg().get("providers") or {}).items():
        if not isinstance(rec, dict):
            continue
        if rec.get("keys") or rec.get("model") or rec.get("base_url"):
            out.append(str(pid))
    return out


# ---------------------------------------------------------------------------
# Безопасный отчёт для панели
# ---------------------------------------------------------------------------

def status(provider_ids=(), env_map=None):
    """Состояние ключей для панели. Сырых ключей здесь не бывает.

    provider_ids — какие провайдеры показать (реестр знает только
    вызывающая сторона, чтобы этот модуль не зависел от providers.py).
    env_map — provider_id -> кортеж дополнительных имён переменных окружения
    (общепринятые вроде OPENROUTER_API_KEY).
    """
    env_map = env_map or {}
    cfg = _cfg()
    out = {}
    ids = list(provider_ids) or list((cfg.get("providers") or {}).keys())
    for pid in ids:
        extra = tuple(env_map.get(pid) or ())
        src = key_source(pid, extra)
        raw = resolve_key(pid, extra) if src else ""
        rec = (cfg.get("providers") or {}).get(pid) or {}
        keys = keys_state(pid, extra)
        out[pid] = {
            "configured": bool(src),
            "source": src,
            # Маска ДЕЙСТВУЮЩЕГО ключа — того, которым уйдёт следующий запрос.
            # Поле оставлено с прежним именем и смыслом: панель показывает им
            # «ключ задан вот такой», и ломать это ради списка незачем.
            "masked": mask(raw),
            # Список появился вместе с ротацией. Панель, которая про него ещё
            # не знает, продолжит работать на полях выше — поэтому он добавлен
            # рядом, а не вместо них.
            "keys": keys,
            "keys_total": len(keys),
            "keys_spent": sum(1 for k in keys if k.get("spent")),
            "model": str(rec.get("model") or ""),
            "base_url": str(rec.get("base_url") or ""),
        }
    return {"providers": out,
            "defaults": get_defaults(),
            "proxy": get_proxy(),
            "dns": get_dns(),
            "config_path": config_path()}
