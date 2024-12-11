import requests
import time
from selenium import webdriver
from requests.exceptions import RequestException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
import traceback
from utils import setup_logger
from colorama import Fore, Style

# Настройка логирования
logger = setup_logger()

class BrowserManager:
    MAX_RETRIES = 3

    def __init__(self, serial_number):
        self.serial_number = serial_number
        self.driver = None
    
    
    def check_browser_status(self):
        """
        Проверяет статус активности браузера через API AdsPower.
        """
        try:
            logger.debug(f"#{self.serial_number}: Checking browser status via API.")
            response = requests.get(
                'http://local.adspower.net:50325/api/v1/browser/active',
                params={'serial_number': self.serial_number}
            )
            logger.debug(f"#{self.serial_number}: API request sent to check browser status.")
            
            response.raise_for_status()
            data = response.json()
            logger.debug(f"#{self.serial_number}: API response received: {data}")

            if data.get('code') == 0 and data.get('data', {}).get('status') == 'Active':
                logger.debug(f"#{self.serial_number}: Browser is active.")
                return True
            else:
                logger.debug(f"#{self.serial_number}: Browser is not active or unexpected status received.")
                return False
        except WebDriverException as e:
            logger.warning(f"#{self.serial_number}: WebDriverException occurred while checking browser status: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"#{self.serial_number}: Failed to check browser status due to network issue: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
        except Exception as e:
            logger.error(f"#{self.serial_number}: Unexpected exception while checking browser status: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
    
            
    def wait_browser_close(self):
        """
        Ожидает закрытия браузера, если он активен.
        """
        try:
            if self.check_browser_status():
                logger.info(f"#{self.serial_number}: Browser already open. Waiting for closure.")          
                start_time = time.time()
                timeout = 900  # Устанавливаем тайм-аут на 15 минут
                
                while time.time() - start_time < timeout:
                    try:
                        if not self.check_browser_status():
                            logger.info(f"#{self.serial_number}: Browser successfully closed.")
                            return True
                    except Exception as e:
                        logger.warning(f"#{self.serial_number}: Error while checking browser status during wait: {str(e)}")
                        logger.debug(traceback.format_exc())
                    
                    time.sleep(5)

                logger.warning(f"#{self.serial_number}: Waiting time for browser closure has expired.")
                return False
            else:
                logger.debug(f"#{self.serial_number}: Browser is not active, no need to wait.")
                return True
        except WebDriverException as e:
            logger.warning(f"#{self.serial_number}: WebDriverException while waiting for browser closure: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
        except Exception as e:
            logger.error(f"#{self.serial_number}: Unexpected error while waiting for browser closure: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
    
            
    def start_browser(self):
        """
        Запускает браузер через AdsPower API и настраивает Selenium WebDriver.
        """
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                logger.debug(f"#{self.serial_number}: Attempting to start the browser (attempt {retries + 1}).")

                if self.check_browser_status():
                    logger.info(f"#{self.serial_number}: Browser already open. Closing the existing browser.")
                    self.close_browser()
                    time.sleep(5)

                # Формирование URL для запуска браузера
                request_url = (
                    f'http://local.adspower.net:50325/api/v1/browser/start?'
                    f'serial_number={self.serial_number}&ip_tab=0&headless=1'
                )
                logger.debug(f"#{self.serial_number}: Request URL for starting browser: {request_url}")

                # Выполнение запроса к API
                response = requests.get(request_url)
                response.raise_for_status()
                data = response.json()
                logger.debug(f"#{self.serial_number}: API response: {data}")

                if data['code'] == 0:
                    selenium_address = data['data']['ws']['selenium']
                    webdriver_path = data['data']['webdriver']
                    logger.debug(f"#{self.serial_number}: Selenium address: {selenium_address}, WebDriver path: {webdriver_path}")

                    # Настройка ChromeOptions
                    chrome_options = Options()
                    chrome_options.add_argument("--disable-notifications=false")
                    chrome_options.add_argument("--disable-popup-blocking=false")
                    chrome_options.add_argument("--disable-geolocation=false")
                    chrome_options.add_argument("--disable-translate=false")
                    chrome_options.add_argument("--disable-infobars=false")
                    chrome_options.add_argument("--disable-blink-features=AutomationControlled=false")
                    chrome_options.add_argument("--no-sandbox=false")
                    chrome_options.add_experimental_option("debuggerAddress", selenium_address)

                    # Инициализация WebDriver
                    service = Service(executable_path=webdriver_path)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.driver.set_window_size(600, 720)
                    logger.info(f"#{self.serial_number}: Browser started successfully.")
                    return True
                else:
                    logger.warning(f"#{self.serial_number}: Failed to start the browser. Error: {data.get('msg', 'Unknown error')}")
                    retries += 1
                    time.sleep(5)  # Задержка перед повторной попыткой

            except requests.exceptions.RequestException as e:
                logger.error(f"#{self.serial_number}: Network issue when starting browser: {str(e)}")
                retries += 1
                time.sleep(5)
            except WebDriverException as e:
                logger.warning(f"#{self.serial_number}: WebDriverException occurred: {str(e)}")
                retries += 1
                time.sleep(5)
            except Exception as e:
                logger.exception(f"#{self.serial_number}: Unexpected exception in starting browser: {str(e)}")
                retries += 1
                time.sleep(5)

        logger.error(f"#{self.serial_number}: Failed to start browser after {self.MAX_RETRIES} retries.")
        return False


    
    def close_browser(self):
        """
        Закрывает браузер с использованием API и WebDriver, с приоритетом на API.
        """
        logger.debug(f"#{self.serial_number}: Initiating browser closure process.")

        # Флаг для предотвращения повторного закрытия
        if getattr(self, "browser_closed", False):
            logger.info(f"#{self.serial_number}: Browser already closed. Skipping closure.")
            return False

        self.browser_closed = True  # Устанавливаем флаг перед попыткой закрытия

        # Попытка остановить браузер через API
        try:
            logger.debug(f"#{self.serial_number}: Attempting to stop browser via API.")
            response = requests.get(
                'http://local.adspower.net:50325/api/v1/browser/stop',
                params={'serial_number': self.serial_number},
                timeout=25  # Тайм-аут для API-запроса
            )
            response.raise_for_status()
            data = response.json()
            logger.debug(f"#{self.serial_number}: API response for browser stop: {data}")

            if data.get('code') == 0:
                logger.info(f"#{self.serial_number}: Browser stopped via API successfully.")
                return True
            else:
                logger.warning(f"#{self.serial_number}: API stop returned unexpected code: {data.get('code')}")
        except requests.exceptions.RequestException as e:
            logger.error(f"#{self.serial_number}: Network issue while stopping browser via API: {str(e)}")
        except Exception as e:
            logger.exception(f"#{self.serial_number}: Unexpected error during API stop: {str(e)}")

        # Если API не сработал, пробуем стандартное закрытие через WebDriver
        try:
            if self.driver:
                logger.debug(f"#{self.serial_number}: Attempting to close browser via WebDriver.")
                self.driver.close()
                self.driver.quit()
                logger.info(f"#{self.serial_number}: Browser closed successfully via WebDriver.")
        except WebDriverException as e:
            logger.warning(f"#{self.serial_number}: WebDriverException while closing browser: {str(e)}")
        except Exception as e:
            logger.exception(f"#{self.serial_number}: General exception while closing browser via WebDriver: {str(e)}")
        finally:
            logger.debug(f"#{self.serial_number}: Resetting driver to None.")
            self.driver = None  # Обнуляем драйвер

        logger.error(f"#{self.serial_number}: Browser closure process completed with errors.")
        return False



