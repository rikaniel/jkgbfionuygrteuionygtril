"""
Модуль проверки доступности узлов и веб-сайтов (синхронный).
"""
import logging
import requests
from ping3 import ping

logger = logging.getLogger(__name__)

def check_node(ip: str, port: int = None, timeout: int = 2) -> bool:
    """Проверяет доступность узла (ICMP ping или TCP соединение)."""
    # 1. ICMP ping
    try:
        rtt = ping(ip, timeout=timeout)
        if rtt is not None:
            logger.debug(f"ICMP ping to {ip} successful, rtt={rtt:.2f}ms")
            return True
    except Exception as e:
        logger.debug(f"ICMP ping to {ip} error: {e}")

    # 2. TCP соединение, если указан порт
    if port:
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            if result == 0:
                logger.debug(f"TCP connection to {ip}:{port} successful")
                return True
        except Exception as e:
            logger.debug(f"TCP connection to {ip}:{port} error: {e}")

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
