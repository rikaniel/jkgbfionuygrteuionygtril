# 🔧 Исправления и улучшения в коде бота

## 📋 Основная проблема
Ошибка `❌ Клиент Yura Phone 1 не найден в inbound 1` возникала из-за неправильной работы с 3x-ui API:
- Использовался числовой `inbound_id` вместо имени inbound
- Прямое обращение к API по ID без проверки существования inbound
- Отсутствие логирования доступных клиентов для отладки

## ✅ Выполненные изменения

### 1. **Изменение структуры БД** (`db.py`)
```python
# Было:
inbound_id INTEGER NOT NULL

# Стало:
inbound_name TEXT NOT NULL
```

**Функции обновлены:**
- `get_user()` — возвращает `inbound_name` вместо `inbound_id`
- `add_user()` — принимает `inbound_name` (строку) вместо `inbound_id` (числа)
- `get_all_users()` — возвращает `inbound_name`
- **Новая функция:** `get_inbound_by_name(name)` — поиск inbound по имени

### 2. **Улучшение работы с 3x-ui API** (`main.py`)

**Функция `get_client_by_email()` полностью переписана:**
```python
def get_client_by_email(inbound_name: str, email: str) -> Optional[Client]:
    # 1. Получаем ВСЕ inbound'ы из API
    all_inbounds = api.inbound.get_list()
    
    # 2. Ищем по имени (или по ID если передан как строка)
    for ib in all_inbounds:
        if ib.name == inbound_name or str(ib.id) == str(inbound_name):
            inbound_id = ib.id
            break
    
    # 3. Получаем данные inbound и ищем клиента
    inbound_data = api.inbound.get_by_id(inbound_id)
    for client in inbound_data.settings.clients:
        if client.email == email:
            return client
    
    # 4. Подробное логирование при ошибке
    logger.warning(f"Доступные клиенты в inbound: {[c.email for c in inbound_data.settings.clients]}")
```

**Преимущества нового подхода:**
- ✅ Работает с именами inbound'ов (человекочитаемо)
- ✅ Автоматически получает актуальный список inbound'ов из 3x-ui
- ✅ При ошибке показывает список всех доступных клиентов для отладки
- ✅ Двойная проверка с переподключением к API
- ✅ Логирование с `exc_info=True` для полного трейсбека

### 3. **Обновление обработчика сообщений** (`main.py`)
```python
# Было:
inbound_id = user["inbound_id"]
client = get_client_by_email(inbound_id, client_email)

# Стало:
inbound_name = user.get("inbound_name") or user.get("inbound_id")
if not inbound_name:
    bot.send_message(..., "❌ Ошибка конфигурации: не указан inbound")
    return

client = get_client_by_email(inbound_name, client_email)
```

### 4. **Обновление админ-панели** (`admin.py`)
```python
# При добавлении пользователя теперь запрашивается:
msg = bot.send_message(message.chat.id, "Введите inbound_name (имя inbound из 3x-ui):")

# Вместо старого:
msg = bot.send_message(message.chat.id, "Введите inbound_id:")
```

### 5. **Скрипт миграции** (`migrate_db.py`)
Автоматически конвертирует старую БД:
- Загружает маппинг `ID -> name` из `config.json`
- Создаёт новую таблицу с `inbound_name`
- Переносит данные с преобразованием
- Сохраняет все остальные поля

## 📝 Как использовать

### Для новых пользователей:
1. В config.json укажите inbound'ы с именами:
```json
"xray_inbounds": [
  {"name": "proxy1", "protocol": "vmess", "settings": {...}},
  {"name": "proxy2", "protocol": "vless", "settings": {...}}
]
```

2. При добавлении пользователя через админку вводите **имя** inbound:
```
Введите inbound_name (имя inbound из 3x-ui): proxy1
```

### Для существующих пользователей:
Запустите скрипт миграции:
```bash
python3 migrate_db.py
```

Или удалите старую БД и создайте заново:
```bash
rm bot.db
# Бот создаст новую БД при запуске
```

## 🔍 Отладка

При ошибке поиска клиента в логах будет:
```
WARNING - Клиент user@example.com не найден в inbound 'proxy1' (ID: 5)
WARNING - Доступные клиенты в inbound: ['alice@example.com', 'bob@example.com']
```

Это поможет быстро понять:
- Существует ли inbound
- Какие клиенты в нём есть
- Правильно ли указан email

## ✅ Проверки пройдены
- Синтаксическая проверка Python ✅
- Тест создания БД и добавления пользователей ✅
- Тест функции `get_inbound_by_name()` ✅
