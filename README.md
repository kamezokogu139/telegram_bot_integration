# X-Partners Postback Bot

Telegram бот для отправки тестовых постбеков (регистрация и депозит).

## Установка

```bash
cd xpartners-postback-bot
pip install -r requirements.txt
```

## Запуск

```bash
python bot.py
```

## Переменные окружения (опционально)

- `TELEGRAM_BOT_TOKEN` — токен бота (по умолчанию задан)
- `AFFISE_API_URL` — URL Affise API (по умолчанию: https://api.affise.com)
- `AFFISE_API_KEY` — ключ API Affise (по умолчанию задан)
- `PROXY_URL` — прокси для открытия ссылок (VPS, residential и т.д.)

Если ваш Affise развёрнут на другом домене, укажите:
```bash
export AFFISE_API_URL=https://api.your-domain.com
```

### Прокси через VPS (для гео-ограниченных ссылок)

Если ссылки не открываются из-за гео-ограничений, настройте прокси на VPS в нужной стране:

1. Установите Squid (HTTP) или Dante/microsocks (SOCKS5) на VPS
2. Запустите бота с переменной:

```bash
# HTTP прокси (Squid)
export PROXY_URL=http://user:password@your-vps-ip:3128

# или SOCKS5 (если используете Dante и т.п.)
export PROXY_URL=socks5://user:password@your-vps-ip:1080

python bot.py
```

Без `PROXY_URL` бот работает как раньше — ссылки открываются напрямую.

## Использование

1. Запустите бота: `/start`
2. Выберите действие: **Тестовая регистрация** или **Тестовый депозит**
3. Отправьте ссылку
4. Бот пройдёт по редиректам до trk.xplink, возьмёт offer_id и pid, click_id из следующего редиректа, получит secure из API и отправит постбек

## Формат постбеков

- **Регистрация**: `?clickid={clickid}&secure={secure}&goal=registration&status=1`
- **Депозит**: `?clickid={clickid}&secure={secure}&goal=deposit&status=2`
