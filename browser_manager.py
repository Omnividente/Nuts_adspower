import requests
import time
import logging
import signal
from selenium import webdriver
from requests.exceptions import RequestException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from colorama import Fore, Style

# Set up logging with colors
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.hasHandlers():
    class CustomFormatter(logging.Formatter):
        COLORS = {
            logging.DEBUG: Fore.CYAN,
            logging.INFO: Fore.GREEN,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.MAGENTA,
        }

        def format(self, record):
            record.asctime = self.formatTime(record, self.datefmt).split('.')[0]
            log_message = super().format(record)
            # Set time to white
            log_message = log_message.replace(record.asctime, f"{Fore.LIGHTYELLOW_EX}{record.asctime}{Style.RESET_ALL}")
            # Set level name color
            levelname = f"{self.COLORS.get(record.levelno, Fore.WHITE)}{record.levelname}{Style.RESET_ALL}"
            log_message = log_message.replace(record.levelname, levelname)
            # Set message color based on level
            message_color = self.COLORS.get(record.levelno, Fore.WHITE)
            log_message = log_message.replace(record.msg, f"{message_color}{record.msg}{Style.RESET_ALL}")
            return log_message

    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

class BrowserManager:
    MAX_RETRIES = 3

    def __init__(self, serial_number):
        self.serial_number = serial_number
        self.driver = None
    
    def check_browser_status(self):
        try:
            response = requests.get(
                'http://local.adspower.net:50325/api/v1/browser/active',
                params={'serial_number': self.serial_number}
            )
            response.raise_for_status()
            data = response.json()
            if data['code'] == 0 and data['data']['status'] == 'Active':
                logger.info(f"Account {self.serial_number}: Browser is already active.")
                return True
            else:
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Account {self.serial_number}: Failed to check browser status due to network issue: {str(e)}")
            return False
        except Exception as e:
            logger.exception(f"Account {self.serial_number}: Unexpected exception while checking browser status: {str(e)}")
            return False
            
    def wait_browser_close(self):
        if self.check_browser_status():
            logger.info(f"Account {self.serial_number}: Browser already open. Waiting for closure.")          
            start_time = time.time()
            timeout = 900
            while time.time() - start_time < timeout:
                if not self.check_browser_status():
                    logger.info(f"Account {self.serial_number}: Browser already closed.")
                    return True
                time.sleep(5)
            logger.warning(f"Account {self.serial_number}: Waiting time for browser closure has expired.")
            return False
        return True
            
    def start_browser(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                if self.check_browser_status():
                    logger.info(f"Account {self.serial_number}: Browser already open. Closing the existing browser.")
                    self.close_browser()
                    time.sleep(5)

                request_url = (
                    f'http://local.adspower.net:50325/api/v1/browser/start?'
                    f'serial_number={self.serial_number}&ip_tab=0&headless=1'
                )

                response = requests.get(request_url)
                response.raise_for_status()
                data = response.json()
                if data['code'] == 0:
                    selenium_address = data['data']['ws']['selenium']
                    webdriver_path = data['data']['webdriver']
                    chrome_options = Options()
                    # Отключение всех запросов
                    chrome_options.add_argument("--disable-notifications=false")  # Уведомления
                    chrome_options.add_argument("--disable-popup-blocking=false")  # Всплывающие окна
                    chrome_options.add_argument("--disable-geolocation=false")  # Запросы местоположения
                    chrome_options.add_argument("--disable-translate=false")  # Запросы переводчика
                    chrome_options.add_argument("--disable-infobars=false")  # Информационные панели
                    chrome_options.add_argument("--disable-blink-features=AutomationControlled=false")  # Обнаружение автоматизации
                    chrome_options.add_argument("--no-sandbox=false")  # Отключение песочницы (для стабильности)
                    chrome_options.add_experimental_option("debuggerAddress", selenium_address)

                    service = Service(executable_path=webdriver_path)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.driver.set_window_size(600, 720)
                    logger.info(f"Account {self.serial_number}: Browser started successfully.")
                    return True
                else:
                    logger.warning(f"Account {self.serial_number}: Failed to start the browser. Error: {data['msg']}")
                    retries += 1
                    time.sleep(5)  # Wait before retrying
            except requests.exceptions.RequestException as e:
                logger.error(f"Account {self.serial_number}: Network issue when starting browser: {str(e)}")
                retries += 1
                time.sleep(5)
            except WebDriverException as e:
                logger.warning(f"Account {self.serial_number}: WebDriverException occurred: {str(e)}")
                retries += 1
                time.sleep(5)
            except Exception as e:
                logger.exception(f"Account {self.serial_number}: Unexpected exception in starting browser: {str(e)}")
                retries += 1
                time.sleep(5)
        
        logger.error(f"Account {self.serial_number}: Failed to start browser after {self.MAX_RETRIES} retries.")
        return False

    
    def close_browser(self):
        """
        Закрывает браузер с использованием API и WebDriver, с приоритетом на API.
        """
        # Флаг для предотвращения повторного закрытия
        if getattr(self, "browser_closed", False):
            logger.info(f"Account {self.serial_number}: Browser already closed. Skipping.")
            return False

        self.browser_closed = True  # Устанавливаем флаг перед попыткой закрытия

        # Попытка остановить браузер через API
        try:
            response = requests.get(
                'http://local.adspower.net:50325/api/v1/browser/stop',
                params={'serial_number': self.serial_number},
                timeout=25  # Тайм-аут для API-запроса
            )
            response.raise_for_status()
            data = response.json()

            if data.get('code') == 0:
                logger.info(f"Account {self.serial_number}: Browser stopped via API successfully.")
                return True
            else:
                logger.warning(f"Account {self.serial_number}: API stop returned unexpected code: {data.get('code')}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Account {self.serial_number}: Network issue while stopping browser via API: {str(e)}")
        except Exception as e:
            logger.exception(f"Account {self.serial_number}: Unexpected error during API stop: {str(e)}")

        # Если API не сработал, пробуем стандартное закрытие через WebDriver
        try:
            if self.driver:
                self.driver.close()
                self.driver.quit()
                logger.info(f"Account {self.serial_number}: Browser closed successfully via WebDriver.")
        except WebDriverException as e:
            logger.warning(f"Account {self.serial_number}: WebDriverException while closing browser: {str(e)}")
        except Exception as e:
            logger.exception(f"Account {self.serial_number}: General exception while closing browser via WebDriver: {str(e)}")
        finally:
            self.driver = None  # Обнуляем драйвер

        return False


