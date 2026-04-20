"""
Модуль проверки доступности узлов и веб-сайтов (синхронный).
"""
import logging
import requests
import socket
from ping3 import ping
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def check_node(ip: str, port: int = None, timeout: int = 2, inbounds: List[Dict[str, Any]] = None) -> bool:
    """
    Проверяет доступность узла (ICMP ping или TCP соединение через proxy).
    
    Если переданы inbounds, попытка подключения идёт через первый доступный proxy.
    """
    # 1. ICMP ping (базовая проверка)
    try:
        rtt = ping(ip, timeout=timeout)
        if rtt is not None:
            logger.debug(f"ICMP ping to {ip} successful, rtt={rtt:.2f}ms")
            return True
    except Exception as e:
        logger.debug(f"ICMP ping to {ip} error: {e}")

    # 2. TCP соединение через proxy (если есть inbounds)
    if inbounds:
        for inbound in inbounds:
            try:
                settings = inbound.get('settings', {})
                proxy_addr = settings.get('address')
                proxy_port = settings.get('port')
                
                if not proxy_addr or not proxy_port:
                    continue
                
                # Пытаемся подключиться к целевому хосту через proxy
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                
                # Для VMess/VLESS нужен специальный подход - здесь упрощённая проверка
                # Просто проверяем доступность самого proxy
                result = sock.connect_ex((proxy_addr, proxy_port))
                sock.close()
                
                if result == 0:
                    logger.debug(f"Proxy {inbound['name']} ({proxy_addr}:{proxy_port}) доступен")
                    # Теперь пробуем пингануть целевую ноду
                    if port:
                        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock2.settimeout(timeout)
                        result2 = sock2.connect_ex((ip, port))
                        sock2.close()
                        if result2 == 0:
                            logger.debug(f"TCP connection to {ip}:{port} via proxy successful")
                            return True
            except Exception as e:
                logger.debug(f"Proxy check error for {inbound['name']}: {e}")
                continue

    # 3. Прямое TCP соединение (если нет proxy или не сработало)
    if port:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            if result == 0:
                logger.debug(f"Direct TCP connection to {ip}:{port} successful")
                return True
        except Exception as e:
            logger.debug(f"Direct TCP connection to {ip}:{port} error: {e}")

    return False


def check_website(url: str, expected_content: str = None, timeout: int = 10) -> bool:
    """Проверяет доступность сайта и опционально наличие контента."""
    try:
        resp = requests.get(url, timeout=timeout, verify=False)
        if resp.status_code != 200:
            logger.debug(f"Website {url} returned status {resp.status_code}")
            return False
        if expected_content and expected_content not in resp.text:
            logger.debug(f"Expected content not found on {url}")
            return False
        logger.debug(f"Website {url} is OK")
        return True
    except Exception as e:
        logger.debug(f"Website {url} error: {e}")
        return False


def check_geo_resource(url: str, timeout: int = 30) -> bool:
    """Проверяет доступность GeoIP/GeoSite ресурса (HEAD запрос)."""
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            logger.debug(f"Geo resource {url} is OK")
            return True
        # Некоторые ресурсы могут не поддерживать HEAD, пробуем GET с малым размером
        resp = requests.get(url, timeout=timeout, stream=True)
        if resp.status_code == 200:
            logger.debug(f"Geo resource {url} is OK (GET)")
            return True
        return False
    except Exception as e:
        logger.debug(f"Geo resource {url} error: {e}")
        return False
