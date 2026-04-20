# Telegram Bot для мониторинга 3x-ui

Мощный бот для мониторинга инфраструктуры 3x-ui с автоматическим созданием инцидентов и админ-панелью.

## 🚀 Возможности

### Автоматический мониторинг
- **Проверка нод** — пинг через Xray proxy inbound'ы
- **Проверка сайтов маскировки** — доступность и контент
- **Проверка GeoIP/GeoSite ресурсов** — доступность файлов правил
- **Периодичность** — проверка каждые 1 час

### Инциденты
- **Автоматическое создание** при проблемах:
  - Нода недоступна → `importance: high`
  - Сайт маскировки не работает → `importance: medium`
  - GeoIP/GeoSite недоступны → `importance: high`
  
- **Статусы инцидентов**:
  - `registered` (Зарегистрирован)
  - `in_progress` (В работе)
  - `resolved` (Решено)

- **Защита от дубликатов** — если инцидент по target уже существует, новый не создаётся
- **Редактирование постов** — при изменении инцидента пост в Telegram канале обновляется автоматически

### Админ-панель (`/admin`)
- **Управление инцидентами**:
  - Просмотр активных инцидентов
  - Создание вручную
  - Изменение статуса и описания
  - Редактирование поста в канале

- **Управление пользователями**:
  - Добавление/удаление подписок
  - Просмотр всех пользователей

- **Управление нодами**:
  - Добавление/удаление нод
  - Проверка доступности через proxy
  - Все ноды общие для всех пользователей

- **Управление сайтами маскировки**:
  - Добавление/удаление
  - Проверка доступности
  - Проверка контента

- **Управление Xray Inbounds** (proxy для пинга):
  - Добавление/удаление proxy
  - Поддержка vmess, vless, trojan и др.

- **Управление администраторами**:
  - Добавление/удаление админов

## 📁 Структура проекта

```
/workspace/
├── main.py           # Главный модуль бота
├── admin.py          # Админ-панель
├── db.py             # Работа с SQLite БД
├── checks.py         # Проверки (ноды, сайты, geo)
├── config.json       # Конфигурация
└── bot.db            # База данных (создаётся автоматически)
```

## ⚙️ Настройка config.json

```json
{
  "global_settings": {
    "telegram_token": "YOUR_BOT_TOKEN",
    "telegram_proxy": "",  // опционально
    "panel_host": "https://your-panel.com",
    "panel_username": "admin",
    "panel_password": "password",
    "subscription_base_url": "https://sub.example.com/",
    "incident_channel": "@your_channel",
    "report_interval_hours": 1,
    "ping_timeout": 5,
    "admin_ids": [123456789]
  },
  "nodes": [
    {"name": "node1", "ip": "192.168.1.1", "port": 443}
  ],
  "masking_sites": [
    {"url": "https://example.com", "expected_content": "Example Domain"}
  ],
  "geoip_url": "https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/geoip.dat",
  "geosite_url": "https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/geosite.dat",
  "xray_inbounds": [
    {
      "name": "proxy1",
      "protocol": "vmess",
      "settings": {
        "address": "proxy1.example.com",
        "port": 443
      }
    }
  ]
}
```

## 🛠 Установка

1. **Установите зависимости**:
```bash
pip install schedule py3xui ping3 requests pytelegrambotapi
```

2. **Настройте config.json**:
   - Вставьте ваш Telegram bot token
   - Укажите данные панели 3x-ui
   - Добавьте admin_ids (ваш Telegram ID)
   - Настройте ноды, сайты маскировки и xray inbounds

3. **Запустите бота**:
```bash
python3 main.py
```

## 📊 Формат инцидента в Telegram

```
🚨 Инцидент: {ID}
Важность: {importance}
Статус: {status}

Описание:
{description}
```

## 🔧 API функции

### DB (db.py)
- `add_incident(importance, description, target)` — создать инцидент
- `get_active_incidents()` — получить активные инциденты
- `update_incident_status(id, status)` — изменить статус
- `update_incident_description(id, desc)` — изменить описание
- `get_all_inbounds()` — получить все proxy
- `sync_inbounds_from_config(list)` — синхронизировать proxy из конфига

### Checks (checks.py)
- `check_node(ip, port, timeout, inbounds)` — проверить ноду через proxy
- `check_website(url, expected_content, timeout)` — проверить сайт
- `check_geo_resource(url, timeout)` — проверить GeoIP/GeoSite

## 📝 Примечания

- **База данных**: SQLite (`bot.db`) — удобно редактировать вручную
- **Логирование**: Все действия логируются в консоль
- **Обработка ошибок**: Присутствует во всех модулях
- **Масштабируемость**: Код готов к расширению функционала

## 🆘 Команды бота

- `/start` — главное меню
- `/admin` — админ-панель (только для админов)

## 📞 Поддержка

При возникновении проблем проверьте:
1. Логи бота
2. Наличие токена в config.json
3. Доступность Telegram API
4. Права бота в канале инцидентов
