#!/usr/bin/env python3
"""
Модуль для работы с 3x-ui API через requests с поддержкой прокси.
Заменяет библиотеку py3xui для более надёжной работы.
"""

import json
import logging
import re
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

logger = logging.getLogger(__name__)

class XUIAPI:
    """Клиент для работы с 3x-ui API (Alireza0/x-ui fork)"""
    
    def __init__(self, base_url: str, username: str, password: str, proxy_url: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.proxy_url = proxy_url
        self.session = requests.Session()
        self.is_logged_in = False
        
        # Настройка прокси
        self._setup_proxy()
        
        # Отключаем предупреждения о SSL (для localhost это нормально)
        self.session.verify = False
        try:
            requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    def _setup_proxy(self):
        """Настройка прокси для сессии"""
        if not self.proxy_url:
            return
            
        # Преобразуем socks5:// в socks5h:// для DNS resolution через прокси
        proxy = self.proxy_url
        if proxy.startswith('socks5://'):
            proxy = proxy.replace('socks5://', 'socks5h://')
        
        # Настраиваем прокси через параметры сессии
        self.session.proxies = {
            'http': proxy,
            'https': proxy
        }
        logger.info(f"Прокси настроен: {proxy}")

    def login(self) -> bool:
        """Выполнение входа в панель"""
        # Пытаемся разные эндпоинты для разных версий панелей
        login_endpoints = [
            '/login',
            '/api/login',
            '/panel/api/login'
        ]
        
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        for endpoint in login_endpoints:
            login_url = f"{self.base_url}{endpoint}"
            try:
                logger.debug(f"Попытка входа через {login_url}")
                response = self.session.post(login_url, json=payload, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success', False) or data.get('status') == 'success':
                        self.is_logged_in = True
                        logger.info(f"✅ Успешный вход в 3x-ui панель через {endpoint}")
                        return True
                    else:
                        error_msg = data.get('msg', data.get('message', 'Неизвестная ошибка'))
                        logger.error(f"❌ Ошибка входа через {endpoint}: {error_msg}")
                elif response.status_code == 302:
                    # Редирект может означать успех в некоторых версиях
                    self.is_logged_in = True
                    logger.info(f"✅ Вход выполнен (редирект) через {endpoint}")
                    return True
                else:
                    logger.debug(f"Статус {response.status_code} при входе через {endpoint}")
                    
            except Exception as e:
                logger.debug(f"Исключение при входе через {endpoint}: {e}")
                continue
        
        logger.error("❌ Не удалось войти ни через один из доступных эндпоинтов")
        return False

    def get_inbounds(self) -> List[Dict]:
        """Получение списка всех inbound'ов"""
        if not self.is_logged_in:
            if not self.login():
                return []
        
        # Разные эндпоинты для разных версий
        endpoints = [
            '/panel/api/inbounds/list',
            '/api/inbounds/list',
            '/panel/api/inbounds/'
        ]
        
        for endpoint in endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                response = self.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    # Обработка разных форматов ответа
                    if isinstance(data, dict):
                        if data.get('success', False):
                            result = data.get('obj', [])
                            if result:
                                logger.info(f"Получено {len(result)} inbound'ов")
                                return result
                        elif data.get('status') == 'success':
                            result = data.get('data', data.get('result', []))
                            if result:
                                return result
                    elif isinstance(data, list):
                        # Прямой список в некоторых версиях
                        if data:
                            return data
                            
            except Exception as e:
                logger.debug(f"Ошибка получения inbound'ов через {endpoint}: {e}")
                continue
        
        # Если сессия истекла, пробуем перелогиниться
        self.is_logged_in = False
        return []

    def get_inbound_by_id(self, inbound_id: int) -> Optional[Dict]:
        """Получение конкретного inbound по ID"""
        if not self.is_logged_in and not self.login():
            return None
        
        endpoints = [
            f'/panel/api/inbounds/get/{inbound_id}',
            f'/api/inbounds/get/{inbound_id}',
            f'/panel/api/inbounds/{inbound_id}'
        ]
        
        for endpoint in endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                response = self.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict):
                        if data.get('success', False) or data.get('status') == 'success':
                            return data.get('obj', data.get('data', {}))
            except Exception as e:
                logger.debug(f"Ошибка получения inbound {inbound_id} через {endpoint}: {e}")
                continue
        
        return None

    def get_client_by_email(self, email: str) -> Optional[Dict]:
        """Поиск клиента по email во всех inbound'ах"""
        inbounds = self.get_inbounds()
        
        if not inbounds:
            logger.warning("Список inbound'ов пуст или не получен")
            return None
        
        for inbound in inbounds:
            # Получаем настройки inbound
            settings_raw = inbound.get('settings', '{}')
            
            # Если settings - строка (JSON), парсим её
            if isinstance(settings_raw, str):
                try:
                    settings = json.loads(settings_raw)
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка парсинга JSON settings для inbound {inbound.get('id')}: {e}")
                    continue
            else:
                settings = settings_raw
            
            clients = settings.get('clients', [])
            
            for client in clients:
                if client.get('email') == email:
                    logger.info(f"✅ Клиент {email} найден в inbound '{inbound.get('remark', inbound.get('name', 'unknown'))}'")
                    # Добавляем информацию об inbound для удобства
                    client['inbound_id'] = inbound.get('id')
                    client['inbound_remark'] = inbound.get('remark', inbound.get('name', 'unknown'))
                    return client
        
        # Логируем все найденные emails для отладки
        all_emails = []
        for inbound in inbounds:
            settings_raw = inbound.get('settings', '{}')
            if isinstance(settings_raw, str):
                try:
                    settings = json.loads(settings_raw)
                except json.JSONDecodeError:
                    continue
            else:
                settings = settings_raw
            for client in settings.get('clients', []):
                all_emails.append(client.get('email'))
        
        logger.warning(f"❌ Клиент {email} не найден. Доступные клиенты: {all_emails}")
        return None

    def get_client_stats(self, inbound_id: int, email: str) -> Optional[Dict]:
        """Получение статистики клиента из данных inbound"""
        if not self.is_logged_in and not self.login():
            return None
        
        # Получаем список всех inbound'ов и ищем нужный
        inbounds = self.get_inbounds()
        if not inbounds:
            logger.error("Не удалось получить список inbound'ов")
            return None
        
        for inbound in inbounds:
            if inbound.get('id') == inbound_id:
                # Получаем настройки inbound
                settings_raw = inbound.get('settings', '{}')
                
                # Если settings - строка (JSON), парсим её
                if isinstance(settings_raw, str):
                    try:
                        settings = json.loads(settings_raw)
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка парсинга JSON settings для inbound {inbound_id}: {e}")
                        return None
                else:
                    settings = settings_raw
                
                # Ищем клиента в списке
                clients = settings.get('clients', [])
                for client in clients:
                    if client.get('email') == email:
                        # Возвращаем статистику из данных клиента
                        return {
                            'up': client.get('up', 0),
                            'down': client.get('down', 0),
                            'total': client.get('total', 0)
                        }
                
                logger.warning(f"Клиент {email} не найден в inbound {inbound_id}")
                return None
        
        logger.warning(f"Inbound {inbound_id} не найден")
        return None

    def reset_client_traffic(self, inbound_id: int, email: str) -> bool:
        """Сброс трафика клиента"""
        if not self.is_logged_in and not self.login():
            return False
        
        endpoints = [
            f'/panel/api/inbounds/resetClientTraffic/{inbound_id}/{email}',
            f'/api/inbounds/resetClientTraffic/{inbound_id}/{email}'
        ]
        
        for endpoint in endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                response = self.session.post(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success', False) or data.get('status') == 'success':
                        logger.info(f"Трафик сброшен для {email}")
                        return True
            except Exception as e:
                logger.debug(f"Ошибка сброса трафика через {endpoint}: {e}")
                continue
        
        logger.error(f"Не удалось сбросить трафик для {email}")
        return False


# Глобальный экземпляр для кэширования
_api_instance: Optional[XUIAPI] = None
_last_login_time: float = 0
_SESSION_TTL = 300  # 5 минут

def get_xui_api(base_url: str, username: str, password: str, proxy_url: Optional[str] = None) -> XUIAPI:
    """Получение экземпляра API с кэшированием сессии"""
    global _api_instance, _last_login_time
    import time
    
    current_time = time.time()
    
    # Проверяем, нужно ли пересоздавать сессию
    if _api_instance is not None and (current_time - _last_login_time) < _SESSION_TTL:
        if _api_instance.is_logged_in:
            logger.debug("Используется кэшированная сессия XUI API")
            return _api_instance
    
    # Создаём новый экземпляр
    logger.info(f"Создание нового XUI API клиента для {base_url}")
    _api_instance = XUIAPI(base_url, username, password, proxy_url)
    
    if not _api_instance.is_logged_in:
        _api_instance.login()
    
    _last_login_time = current_time
    return _api_instance
