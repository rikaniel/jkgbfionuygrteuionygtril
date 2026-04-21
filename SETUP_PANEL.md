# 🔧 Настройка подключения к 3x-ui панели

## Проблема
Ошибка `No session cookie found, something wrong with the login...` возникает из-за проблем с подключением к панели 3x-ui.

## Решение

### 1. Проверьте, запущена ли панель 3x-ui
```bash
# Проверка порта (по умолчанию 2053)
netstat -tlnp | grep 2053
# или
ss -tlnp | grep 2053
```

Если порт не слушается, запустите панель:
```bash
# Для x-ui от Alireza0
systemctl status x-ui
# или
service x-ui status
```

### 2. Обновите config.json

Откройте файл `config.json` и укажите **правильные данные** вашей панели:

```json
{
  "global_settings": {
    "telegram_token": "YOUR_BOT_TOKEN_HERE",
    "telegram_proxy": "socks5://127.0.0.1:10808",
    "panel_host": "http://ВАШ_IP:2053",
    "panel_username": "admin",
    "panel_password": "ваш_пароль",
    "panel_proxy": null,
    ...
  }
}
```

**Важные параметры:**
- `panel_host` - URL вашей панели (например, `http://192.168.1.100:2053` или `https://panel.example.com`)
- `panel_username` - логин от панели
- `panel_password` - пароль от панели
- `panel_proxy` - прокси для доступа к панели (если нужен), или `null` если панель локально

### 3. Если панель за NAT/файрволом

Если панель находится на удалённом сервере и недоступна напрямую:

**Вариант A: SSH туннель**
```bash
ssh -L 2053:localhost:2053 user@your-server-ip
```
Затем в config.json укажите: `"panel_host": "http://localhost:2053"`

**Вариант B: Прокси**
Установите `panel_proxy` в config.json:
```json
"panel_proxy": "socks5://proxy-host:port"
```

### 4. Тестирование подключения

Запустите тестовый скрипт:
```bash
python test_api.py
```

Ожидаемый результат:
```
✅ Успешный вход в панель!
📋 Получение списка inbound'ов...
✅ Найдено X inbound'ов:
   • ID=1, Name='proxy1', Protocol=vmess, Clients=5
      - user1@example.com
      - user2@example.com
```

### 5. Запуск бота

После успешного теста:
```bash
# Удалите старую БД (если меняли структуру)
rm -f bot.db

# Запустите бота
python main.py
```

## Возможные ошибки и решения

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `Connection refused` | Панель не запущена или неверный порт | Проверьте `systemctl status x-ui`, убедитесь что порт правильный |
| `No session cookie found` | Неверный логин/пароль | Проверьте учётные данные в панели |
| `Timeout` | Сетевая проблема | Проверьте доступность сервера (`ping`, `telnet`) |
| `404 Not Found` | Неверный URL или версия панели | Попробуйте разные варианты: `/login`, `/api/login`, `/panel/api/login` |

## Примечания

- Бот теперь использует **кастомный API клиент** (`custom_xui_api.py`) вместо `py3xui` для лучшей поддержки разных версий панелей
- Поддерживаются SOCKS5 прокси для доступа к панели
- Автоматическая переподключение при обрыве сессии (TTL 5 минут)
- Логирование всех попыток подключения для отладки
