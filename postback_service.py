"""
Сервис для извлечения clickid, получения secure из Affise и отправки постбеков.
"""
from urllib.parse import urlparse, parse_qs, urljoin, urlencode

import httpx

from config import AFFISE_API_URL, AFFISE_API_KEY, POSTBACK_BASE_URL, REQUEST_TIMEOUT, PROXY_URL, TRACKER_DOMAINS, TRACKING_CLICK_BASE


def _is_tracker_url(url: str) -> bool:
    """Проверяет, принадлежит ли URL домену трекера."""
    return any(domain in url for domain in TRACKER_DOMAINS)


def _looks_like_click_id(value: str) -> bool:
    """Проверяет, похоже ли значение на click_id (sub1/sub2 могут быть и другими)."""
    if not value or len(value) < 8:
        return False
    return value.replace("-", "").replace("_", "").isalnum()


def _normalize_clickid_value(val: str) -> str | None:
    """
    Нормализует значение: если формат {clickid}_{your_sub}, берёт часть до '_'.
    """
    if not val:
        return None
    if "_" in val:
        before_underscore = val.split("_", 1)[0]
        if _looks_like_click_id(before_underscore):
            return before_underscore
    if _looks_like_click_id(val):
        return val
    return None


def _extract_clickid_from_url(url: str) -> str | None:
    """
    Извлекает click_id из URL. Поддерживает явные имена и sub1-sub5.
    Учитывает формат {clickid}_{your_sub} — берёт часть до '_'.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    explicit_names = [
        "clickid", "click_id", "cbid", "aff_click_id", "external_id",
        "stag", "utm_content", "partner_click_id", "subid", "afp1",
        "sub_id1", "anid","s2s.req_id","payload"
    ]
    for name in explicit_names:
        if name in params and params[name]:
            normalized = _normalize_clickid_value(params[name][0])
            if normalized:
                return normalized
    for name in ["sub1", "sub2", "sub3", "sub4", "sub5"]:
        if name in params and params[name]:
            normalized = _normalize_clickid_value(params[name][0])
            if normalized:
                return normalized
    return None


def extract_clickid_from_redirect(affiliate_url: str) -> tuple[str | None, str | None, str | None, str]:
    """
    Следует редиректам только до первого редиректа после трекера и берёт click_id оттуда.
    Не открывает ссылку до финала — достаточно редиректа после TRACKER_DOMAINS.

    Returns:
        tuple: (clickid, offer_id, pid, error_message)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        client_kwargs: dict = {
            "follow_redirects": False,
            "timeout": REQUEST_TIMEOUT,
        }
        if PROXY_URL:
            client_kwargs["proxy"] = PROXY_URL
        with httpx.Client(**client_kwargs) as client:
            url = affiliate_url
            all_urls = [affiliate_url]
            clickid = None
            max_hops = 15

            for _ in range(max_hops):
                response = client.get(url, headers=headers)
                if response.status_code >= 400:
                    response.raise_for_status()  # 3xx не поднимаем — обрабатываем редиректы вручную

                if 300 <= response.status_code < 400 and "location" in response.headers:
                    loc = response.headers["location"].strip()
                    if loc:
                        next_url = urljoin(str(response.url), loc)
                        all_urls.append(next_url)
                        # Редирект с трекера — берём click_id из Location, дальше НЕ идём (избегаем 403)
                        if _is_tracker_url(str(response.url)):
                            clickid = _extract_clickid_from_url(next_url)
                            break  # не запрашиваем next_url — лендинг может отдавать 403
                        url = next_url
                        continue
                break

            if not clickid:
                return None, None, None, (
                    "ClickID не найден в редиректе X-partners. "
                )
            
            # Извлекаем offer_id и pid только из URL трекера (TRACKER_DOMAINS)
            offer_id = None
            pid = None
            for url in all_urls:
                if _is_tracker_url(url):
                    if not offer_id:
                        offer_id = extract_offer_id_from_url(url)
                    if not pid:
                        pid = extract_pid_from_url(url)
                    if offer_id and pid:
                        break
            
            if not offer_id:
                return clickid, None, pid, "ClickID найден, но offer_id не удалось извлечь из URL. Укажите offer_id вручную."
            
            return clickid, offer_id, pid, ""
            
    except httpx.TimeoutException:
        return None, None, None, "Таймаут при переходе по ссылке. Попробуйте снова."
    except httpx.HTTPError as e:
        return None, None, None, f"Ошибка HTTP при переходе по ссылке: {str(e)}"
    except Exception as e:
        return None, None, None, f"Ошибка: {str(e)}"


def extract_offer_id_from_url(url: str) -> str | None:
    """
    Извлекает offer_id из URL trk.xplink.
    Поддерживает: путь /123/, query ?offer_id=123, ?offer=123, поддомен 123.trk.xplink
    """
    try:
        parsed = urlparse(url)
        
        # Проверяем query параметры
        params = parse_qs(parsed.query)
        for key in ["offer_id", "offer", "o", "offerid"]:
            if key in params and params[key]:
                val = params[key][0]
                if val.isdigit():
                    return val
        
        # Проверяем путь - ищем числовой сегмент
        path_parts = [p for p in parsed.path.split("/") if p]
        for part in path_parts:
            if part.isdigit():
                return part
        
        # Проверяем поддомен (123.trk.xplink)
        hostname = parsed.hostname or ""
        if any(d in hostname for d in TRACKER_DOMAINS):
            subdomain = hostname.split(".")[0]
            if subdomain.isdigit():
                return subdomain
        
        return None
    except Exception:
        return None


def extract_pid_from_url(url: str) -> str | None:
    """
    Извлекает pid (partner/affiliate ID) из URL трекера (TRACKER_DOMAINS).
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not any(d in hostname for d in TRACKER_DOMAINS):
            return None

        params = parse_qs(parsed.query)
        for key in ["pid", "partner_id", "partner", "affiliate_id"]:
            if key in params and params[key]:
                val = params[key][0]
                if val and (val.isdigit() or val):
                    return val

        path_parts = [p for p in parsed.path.split("/") if p]
        for i, part in enumerate(path_parts):
            if part.lower() == "pid" and i + 1 < len(path_parts) and path_parts[i + 1].isdigit():
                return path_parts[i + 1]
        for part in path_parts:
            if part.isdigit():
                return part

        return None
    except Exception:
        return None


def get_offer_secure(offer_id: str) -> tuple[str | None, str]:
    """
    Получает secure (hash_password) для оффера из Affise API.
    
    Returns:
        tuple: (secure, error_message)
    """
    url = f"{AFFISE_API_URL}/3.0/offer/{offer_id}"
    headers = {"API-Key": AFFISE_API_KEY}
    
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") != 1:
                return None, "API вернул неожиданный статус"
            
            offer = data.get("offer", {})
            secure = offer.get("hash_password") or offer.get("secure")
            
            if not secure:
                return None, "У оффера не настроен secure (hash_password). Обратитесь к менеджеру."
            
            return str(secure), ""
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None, f"Оффер {offer_id} не найден"
        return None, f"Ошибка API: {e.response.status_code}"
    except httpx.RequestError as e:
        return None, f"Ошибка подключения к API: {str(e)}"
    except Exception as e:
        return None, f"Ошибка: {str(e)}"


def infer_postback_status(goal_value: str, goal_title: str | None = None) -> int:
    """
    Определяет status постбека по goal из Affise.

    X-Partners использует status=1 для регистрации и status=2 для остальных
    целей. В payments регистрация может приходить numeric goal "1".
    """
    value = str(goal_value or "").strip().lower()
    title = str(goal_title or "").strip().lower()
    registration_values = {
        "registration", "register", "reg", "signup", "sign_up", "sign up", "1",
    }

    if value in registration_values:
        return 1

    normalized_title = " ".join(title.replace("-", " ").replace("_", " ").split())
    if normalized_title in registration_values or normalized_title.startswith(
        ("registration ", "register ", "signup ", "sign up ")
    ):
        return 1

    return 2


def _parse_offer_goals(offer: dict) -> list[dict]:
    """
    Извлекает список целей оффера из ответа Affise API.
    Возвращает список dict с ключами: id, title, value.

    value — то, что подставляется в параметр goal постбека.
    Affise может называть это поле по-разному, поэтому пробуем
    несколько вариантов в порядке приоритета.
    """
    result: list[dict] = []
    seen_values: set[str] = set()

    # Источник целей только payments.
    raw_payments = offer.get("payments") or []
    for idx, payment in enumerate(raw_payments):
        if not isinstance(payment, dict):
            continue
        payment_goal = payment.get("goal")
        if payment_goal is None:
            continue
        value_str = str(payment_goal).strip()
        if not value_str or value_str in seen_values:
            continue

        payment_title = payment.get("title") or payment.get("name") or f"Payment goal {value_str}"
        payment_goal_id = payment.get("goal_id")
        if payment_goal_id is not None:
            gid = f"payment-{payment_goal_id}-{idx}"
        else:
            gid = f"payment-{idx}"

        result.append({
            "id": str(gid),
            "title": str(payment_title),
            "value": value_str,
            "status": infer_postback_status(value_str, payment_title),
        })
        seen_values.add(value_str)
    return result


def _build_postback_url(params: dict) -> str:
    """Собирает URL постбека с безопасным encoding всех query values."""
    return f"{POSTBACK_BASE_URL}?{urlencode(params, safe='{}')}"


def get_offer_details(offer_id: str) -> tuple[str | None, list[dict], str]:
    """
    Получает данные оффера из Affise API за один вызов:
    secure (hash_password) + список целей (goals).

    Returns:
        tuple: (secure, goals, error_message)
            goals — list[{"id": str, "title": str, "value": str}]
    """
    url = f"{AFFISE_API_URL}/3.0/offer/{offer_id}"
    headers = {"API-Key": AFFISE_API_KEY}

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != 1:
            return None, [], "API вернул неожиданный статус"

        offer = data.get("offer", {})
        secure = offer.get("hash_password") or offer.get("secure")

        if not secure:
            return None, [], "У оффера не настроен secure (hash_password). Обратитесь к менеджеру."

        goals = _parse_offer_goals(offer)
        if not goals:
            return str(secure), [], "У оффера не настроены цели в Affise"

        return str(secure), goals, ""

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None, [], f"Оффер {offer_id} не найден"
        return None, [], f"Ошибка API: {e.response.status_code}"
    except httpx.RequestError as e:
        return None, [], f"Ошибка подключения к API: {str(e)}"
    except Exception as e:
        return None, [], f"Ошибка: {str(e)}"


def send_postback(clickid: str, secure: str, goal: str, status: int, pid: str = "") -> tuple[bool, str]:
    """
    Отправляет постбек.

    Args:
        goal: 'registration' или 'deposit'
        status: 1 для reg, 2 для deposit
        pid: ID партнёра из ссылки, для action_id=TEST_{pid}

    Returns:
        tuple: (success, message)
    """
    action_id = f"TEST_{pid}" if pid else "TEST_0"
    url = _build_postback_url({
        "clickid": clickid,
        "secure": secure,
        "goal": goal,
        "status": status,
        "action_id": action_id,
    })
    
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(url)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("status") == 1:
                        return True, "Постбек успешно отправлен!"
                    return False, f"Ответ: {data}"
                except Exception:
                    return True, f"Постбек отправлен (код {response.status_code})"
            return False, f"Ошибка постбека: HTTP {response.status_code}"
            
    except Exception as e:
        return False, f"Ошибка отправки: {str(e)}"


def get_offer_links(offer_id: str, pid: str) -> tuple[str | None, list[dict], str]:
    """
    Получает трекинг-ссылку и лендинги оффера для вебмастера из Affise API.
    
    Args:
        offer_id: ID оффера (число или строка)
        pid: ID вебмастера (partner/affiliate id)
    
    Returns:
        (tracking_url, landings_list, error_message)
        landings_list — список dict с ключами: id, title, url, url_preview, type
    """
    url = f"{AFFISE_API_URL}/3.0/offer/{offer_id}"
    headers = {"API-Key": AFFISE_API_KEY}
    client_kwargs: dict = {"timeout": REQUEST_TIMEOUT}
    if PROXY_URL:
        client_kwargs["proxy"] = PROXY_URL

    try:
        with httpx.Client(**client_kwargs) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != 1:
            return None, [], "API вернул неожиданный статус"
        
        offer = data.get("offer", {})
        internal_id = offer.get("id") or offer_id
        landings_raw = offer.get("landings") or []

        # Домен трекинг-ссылки берём из API: tracking_domain или domain_url
        domain = (offer.get("tracking_domain") or offer.get("domain_url") or "").strip()
        use_https = bool(offer.get("use_https", True))
        if domain:
            domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
            scheme = "https" if use_https else "http"
            base = f"{scheme}://{domain}"
        else:
            base = TRACKING_CLICK_BASE.rstrip("/")
        tracking_url = f"{base}/click?pid={pid}&offer_id={internal_id}"
        
        landings = []
        for L in landings_raw:
            if isinstance(L, dict):
                lnd_id = L.get("id")
                if lnd_id is None:
                    continue  # без id — лендинга нет, не включаем
                landings.append({
                    "id": lnd_id,
                    "title": L.get("title") or L.get("name") or "—",
                    "url": f"{base}/click?pid={pid}&offer_id={internal_id}&l={lnd_id}",
                    "url_preview": L.get("url_preview") or L.get("url") or "",
                    "type": L.get("type") or "landing",
                })
        
        return tracking_url, landings, ""
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None, [], f"Оффер {offer_id} не найден"
        return None, [], f"Ошибка API: {e.response.status_code}"
    except httpx.RequestError as e:
        return None, [], f"Ошибка подключения к API: {str(e)}"
    except Exception as e:
        return None, [], f"Ошибка: {str(e)}"


def build_postback_urls_for_advertiser(offer_id: str, pid: str = "108") -> tuple[str | None, str | None, str]:
    """
    Собирает URL постбеков для передачи рекламодателю.
    clickid={adv_click_id} — рекламодатель подставляет свой click_id.
    Returns:
        (url_registration, url_deposit, error_message)
    """
    secure, goals, error = get_offer_details(offer_id)
    if not secure:
        return None, None, error or "Не удалось получить данные оффера"

    reg_goal = None
    dep_goal = None
    for goal in goals:
        status = int(
            goal.get("status")
            or infer_postback_status(goal.get("value", ""), goal.get("title", ""))
        )
        if status == 1 and reg_goal is None:
            reg_goal = goal
        elif status == 2 and dep_goal is None:
            dep_goal = goal

    if not reg_goal or not dep_goal:
        return None, None, "У оффера не найдены цели регистрации и депозита в Affise"

    url_reg = _build_postback_url({
        "clickid": "{adv_click_id}",
        "secure": secure,
        "goal": reg_goal.get("value", ""),
        "status": 1,
    })
    url_dep = _build_postback_url({
        "clickid": "{adv_click_id}",
        "secure": secure,
        "goal": dep_goal.get("value", ""),
        "status": 2,
    })
    return url_reg, url_dep, ""
