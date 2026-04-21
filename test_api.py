#!/usr/bin/env python3
"""
Тестовый скрипт для проверки подключения к 3x-ui API через custom_xui_api
"""

import logging
import json

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)

# Загружаем конфиг
with open("config.json", "r") as f:
    config = json.load(f)

GLOBAL = config["global_settings"]
PANEL_HOST = GLOBAL["panel_host"]
PANEL_USER = GLOBAL["panel_username"]
PANEL_PASS = GLOBAL["panel_password"]
PROXY = GLOBAL.get("telegram_proxy")

print(f"\n🔧 Тестирование подключения к 3x-ui панели:")
print(f"   URL: {PANEL_HOST}")
print(f"   User: {PANEL_USER}")
print(f"   Proxy: {PROXY}")
print()

from custom_xui_api import get_xui_api

try:
    print("📡 Попытка подключения...")
    api = get_xui_api(PANEL_HOST, PANEL_USER, PANEL_PASS, None)  # Без прокси для теста
    
    if api.is_logged_in:
        print("✅ Успешный вход в панель!")
        
        print("\n📋 Получение списка inbound'ов...")
        inbounds = api.get_inbounds()
        
        if inbounds:
            print(f"✅ Найдено {len(inbounds)} inbound'ов:")
            for ib in inbounds:
                name = ib.get('remark', ib.get('name', 'Unknown'))
                ib_id = ib.get('id')
                protocol = ib.get('protocol', 'unknown')
                settings = ib.get('settings', {})
                clients = settings.get('clients', [])
                print(f"   • ID={ib_id}, Name='{name}', Protocol={protocol}, Clients={len(clients)}")
                
                # Выводим email'ы клиентов
                for client in clients:
                    email = client.get('email')
                    if email:
                        print(f"      - {email}")
        else:
            print("❌ Не удалось получить список inbound'ов или список пуст")
            
        # Тест поиска клиента
        if inbounds:
            settings = inbounds[0].get('settings', {})
            clients = settings.get('clients', [])
            if clients:
                test_email = clients[0].get('email')
                if test_email:
                    print(f"\n🔍 Тест поиска клиента по email: {test_email}")
                    found_client = api.get_client_by_email(test_email)
                    if found_client:
                        print(f"✅ Клиент найден: {found_client.get('email')}")
                        print(f"   Inbound: {found_client.get('inbound_remark')}")
                        print(f"   Inbound ID: {found_client.get('inbound_id')}")
                    else:
                        print("❌ Клиент не найден")
        
    else:
        print("❌ Не удалось войти в панель")
        
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\n✅ Тестирование завершено")
