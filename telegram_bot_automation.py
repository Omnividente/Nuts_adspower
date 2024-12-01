import logging
import random
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, WebDriverException, TimeoutException
from browser_manager import BrowserManager
from utils import update_balance_table
from colorama import Fore, Style
import traceback




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

class TelegramBotAutomation:
    MAX_RETRIES = 3

    def __init__(self, serial_number, settings):
        self.serial_number = serial_number
        self.username = None  # Initialize username as None
        self.balance = 0.0  # Initialize balance as 0.0
        self.browser_manager = BrowserManager(serial_number)
        self.settings = settings        
        self.driver = None

        logger.info(f"Initializing automation for account {serial_number}")

        # Ожидание завершения предыдущей сессии браузера
        if not self.browser_manager.wait_browser_close():
            logger.error(f"Account {serial_number}: Failed to close previous browser session.")
            raise RuntimeError("Failed to close previous browser session")

        # Запуск браузера
        if not self.browser_manager.start_browser():
            logger.error(f"Account {serial_number}: Failed to start browser.")
            raise RuntimeError("Failed to start browser")

        # Сохранение экземпляра драйвера
        self.driver = self.browser_manager.driver

    def perform_quests(self):
        """
        Выполняет доступные квесты в интерфейсе через Selenium.
        """
        logger.info(f"Account {self.serial_number}: Starting quest execution.")
        processed_quests = set()  # Хранение обработанных кнопок

        try:
            # Переключаемся в iframe с квестами
            if not self.switch_to_iframe():
                logger.error(f"Account {self.serial_number}: Failed to switch to iframe for quests.")
                return

            while True:
                try:
                    # Находим кнопки квестов с наградами
                    quest_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.relative.flex.h-\\[74px\\].w-\\[74px\\]")
                    quest_buttons = [
                        btn for btn in quest_buttons
                        if btn not in processed_quests and self.has_reward(btn)
                    ]

                    if not quest_buttons:
                        #logger.info(f"Account {self.serial_number}: No more quests available.")
                        break

                    # Берём первый квест из списка
                    current_quest = quest_buttons[0]
                    reward_text = self.get_reward_text(current_quest)
                    logger.info(f"Account {self.serial_number}: Found quest with reward: {reward_text}")

                    # Нажимаем на кнопку квеста
                    self.safe_click(current_quest)
                    processed_quests.add(current_quest)

                    # Выполняем взаимодействие с окном квеста
                    if self.interact_with_quest_window():
                        logger.info(f"Account {self.serial_number}: Quest with reward {reward_text} completed.")
                    else:
                        logger.warning(f"Account {self.serial_number}: Failed to complete quest with reward {reward_text}. Retrying.")
                        break  # Если квест не завершён, прерываем выполнение
                except Exception as e:
                    logger.error(f"Account {self.serial_number}: Error while performing quest: {str(e)}")
                    break
        finally:
            # Возвращаемся к главному контенту
            self.driver.switch_to.default_content()
            self.switch_to_iframe()
            logger.info(f"Account {self.serial_number}: Completed all quests.")






    def has_reward(self, button):
        """
        Проверяет, содержит ли кнопка квеста награду.
        """
        try:
            reward_div = button.find_element(By.CSS_SELECTOR, "div.absolute.-bottom-2.-left-2.z-50")
            reward_text = reward_div.text.strip()
            return bool(reward_text and reward_text.startswith("+"))
        except Exception:
            return False


    def get_reward_text(self, button):
        """
        Получает текст награды из кнопки квеста.
        """
        try:
            reward_div = button.find_element(By.CSS_SELECTOR, "div.absolute.-bottom-2.-left-2.z-50")
            return reward_div.text.strip()
        except Exception:
            return "Unknown"


    def interact_with_quest_window(self):
        """
        Взаимодействует с окном квеста до его закрытия.
        """
        try:
            # Ожидаем появления окна квеста
            quest_window = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@style, 'position: absolute; height: inherit; width: inherit;')]"))
            )
            #logger.info(f"Account {self.serial_number}: Quest window detected. Starting interaction.")

            retries = 0  # Счётчик попыток
            while retries < 10:  # Ограничение на 10 попыток взаимодействия
                # Проверяем, закрыто ли окно квеста
                quest_window = self.driver.find_elements(By.XPATH, "//div[contains(@style, 'position: absolute; height: inherit; width: inherit;')]")
                if not quest_window:
                    logger.info(f"Account {self.serial_number}: Quest window closed. Interaction complete.")
                    return True  # Окно квеста успешно закрыто

                # Пытаемся найти элемент для клика в правой половине
                quest_element = self.wait_for_element(By.XPATH, "/html/body/div[5]/div/div[3]/div[2]", timeout=5)
                if quest_element:
                    self.safe_click(quest_element)
                    #logger.info(f"Account {self.serial_number}: Clicked on the right side of the quest window.")
                else:
                    logger.warning(f"Account {self.serial_number}: Right-side element not found. Retrying.")
                    retries += 1
                    time.sleep(1)
                    continue

                # Проверяем снова, закрыто ли окно после клика
                time.sleep(1)  # Небольшая пауза для обновления состояния
                updated_quest_window = self.driver.find_elements(By.XPATH, "//div[contains(@style, 'position: absolute; height: inherit; width: inherit;')]")
                if not updated_quest_window:
                    #logger.info(f"Account {self.serial_number}: Quest window successfully closed after click.")
                    return True

                retries += 1
                time.sleep(1)  # Пауза перед следующей попыткой

            # Если после 10 попыток окно не закрылось
            logger.warning(f"Account {self.serial_number}: Quest window did not close after maximum retries.")
            return False
        except TimeoutException:
            logger.warning(f"Account {self.serial_number}: Quest window did not appear in time.")
            return False
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Error interacting with quest window: {str(e)}")
            return False




    def safe_click(self, element):
        """
        Безопасный клик по элементу.
        """
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(element))
            element.click()
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except Exception:
                pass



    def navigate_to_bot(self):
        self.clear_browser_cache_and_reload()
        time.sleep(5)
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                self.driver.get('https://web.telegram.org/k/')
                logger.debug(f"Account {self.serial_number}: Navigated to Telegram web.")
                self.close_extra_windows()
                sleep_time = random.randint(5, 7)
                logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                time.sleep(sleep_time)
                return True
            except (WebDriverException, TimeoutException) as e:
                logger.warning(f"Account {self.serial_number}: Exception in navigating to Telegram bot (attempt {retries + 1}): {str(e)}")
                retries += 1
                time.sleep(5)
        return False
    
    def close_extra_windows(self):
        try:
            current_window = self.driver.current_window_handle
            all_windows = self.driver.window_handles
            for window in all_windows:
                if window != current_window:
                    self.driver.switch_to.window(window)
                    self.driver.close()
                    self.driver.switch_to.window(current_window)
        except WebDriverException as e:
            logger.warning(f"Account {self.serial_number}: Exception while closing extra windows: {str(e)}")
    
    def send_message(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                chat_input_area = self.wait_for_element(By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/input[1]')
                if chat_input_area:
                    chat_input_area.click()
                    group_url = self.settings.get('TELEGRAM_GROUP_URL', 'https://t.me/CryptoProjects_sbt')
                    chat_input_area.send_keys(group_url)
                
                search_area = self.wait_for_element(By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/ul[1]/a[1]/div[1]')
                if search_area:
                    search_area.click()
                    logger.debug(f"Account {self.serial_number}: Group searched.")
                sleep_time = random.randint(5, 7)
                logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                time.sleep(sleep_time)
                return True
            except (NoSuchElementException, WebDriverException) as e:
                logger.warning(f"Account {self.serial_number}: Failed to perform action (attempt {retries + 1}): {str(e)}")
                retries += 1
                time.sleep(5)
        return False

    def click_link(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                # Получаем ссылку из настроек
                bot_link = self.settings.get('BOT_LINK', 'https://t.me/nutsfarm_bot/nutscoin?startapp=ref_YCNYYSFWGOQTBFS')

                # Поиск элемента ссылки
                link = self.wait_for_element(By.CSS_SELECTOR, f"a[href*='{bot_link}']")
                if link:
                    # Скроллинг к ссылке
                    self.driver.execute_script("arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", link)
                    time.sleep(1)  # Небольшая задержка для завершения скроллинга
                    
                    # Клик по ссылке
                    link.click()
                    time.sleep(2)

                # Поиск и клик по кнопке запуска
                launch_button = self.wait_for_element(By.CSS_SELECTOR, "button.popup-button.btn.primary.rp", timeout=5)
                if launch_button:
                    launch_button.click()
                    logger.info(f"Account {self.serial_number}: Launch button clicked.")
                
                # Лог успешного запуска
                logger.info(f"Account {self.serial_number}: NUTSFARM STARTED")

                # Случайная задержка перед переключением на iframe
                sleep_time = random.randint(15, 20)
                logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                time.sleep(sleep_time)

                # Переключение на iframe
                self.switch_to_iframe()
                return True
            
            except (NoSuchElementException, WebDriverException, TimeoutException) as e:
                logger.warning(f"Account {self.serial_number}: Failed to click link or interact with elements (attempt {retries + 1}): {str(e)}")
                retries += 1
                time.sleep(5)

        # Возвращаем False, если все попытки завершились неудачно
        return False


    def wait_for_element(self, by, value, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
        except TimeoutException:
            #logger.warning(f"Account {self.serial_number}: Failed to find the element located by {by} with value {value} within {timeout} seconds.")
            return None
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Unexpected error while waiting for element: {str(e)}")
            return None
    def clear_browser_cache_and_reload(self):
        """
        Очищает кэш браузера и перезагружает текущую страницу.
        """
        try:
            # Очистка кэша
            self.driver.execute_cdp_cmd("Network.clearBrowserCache", {})
            logger.debug("Browser cache cleared.")
            
            # Перезагрузка текущей страницы
            self.driver.refresh()
            logger.debug("Page refreshed after clearing cache.")
        except Exception as e:
            logger.error(f"Failed to clear browser cache or reload page: {e}")


    def preparing_account(self):
        actions = [
            ("/html/body/div[1]/div/button", "First start button claimed", "First start button already claimed."),
            ("//button[contains(text(), 'Click now')]", "'Click now' button clicked", "'Click now' button is unnecessary."),
            ("/html/body/div[2]/div[2]/button", "Claimed welcome bonus: 1337 NUTS", "Welcome bonus already claimed."),
            ("/html/body/div[2]/div[2]/div[2]/button", "Daily reward claimed", "Daily reward already claimed.")
        ]
        for xpath, success_msg, fail_msg in actions:
            retries = 0
            while retries < self.MAX_RETRIES:
                try:
                    element = self.driver.find_element(By.XPATH, xpath)
                    element.click()
                    logger.debug(f"Account {self.serial_number}: {success_msg}")
                    sleep_time = random.randint(5, 7)
                    logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                    time.sleep(sleep_time)
                    break
                except NoSuchElementException:
                    logger.info(f"Account {self.serial_number}: {fail_msg}")
                    break
                except WebDriverException as e:
                    logger.warning(f"Account {self.serial_number}: Failed action (attempt {retries + 1}): {str(e)}")
                    retries += 1
                    time.sleep(5)

    def switch_to_iframe(self):
        """
        This method switches to the first iframe on the page, if available.
        """
        try:
            # Возвращаемся к основному контенту страницы
            self.driver.switch_to.default_content()
            
            # Ищем все iframes на странице
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                # Переключаемся на первый iframe
                self.driver.switch_to.frame(iframes[0])
                #logger.info(f"Account {self.serial_number}: Switched to iframe.")
                return True
            else:
                logger.warning(f"Account {self.serial_number}: No iframe found to switch.")
                return False
        except NoSuchElementException:
            logger.warning(f"Account {self.serial_number}: No iframe found.")
            return False
        except Exception as e:
            logger.error(f"Account {self.serial_number}: Unexpected error while switching to iframe: {str(e)}")
            return False




    def get_username(self):
        # Получение имени пользователя
        username_block = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//header/button/p"))  # Укажите точный XPATH для username
        )
        username = username_block.get_attribute("textContent").strip()
        #logger.info(f"Account {self.serial_number}: Current username: {username}")
        return username
    
    def get_balance(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                # Ожидание контейнера с балансом
                parent_block = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'flex items-center font-tt-hoves')]"))
                )
                logger.debug("Parent block for balance found.")

                # Поиск всех чисел в балансе
                visible_balance_elements = parent_block.find_elements(By.XPATH, ".//span[contains(@class, 'index-module_num__j6XH3') and not(@aria-hidden='true')]")
                logger.debug(f"Extracted raw balance elements: {[el.get_attribute('textContent').strip() for el in visible_balance_elements]}")

                # Сбор текста чисел и объединение в строку
                balance_text = ''.join([element.get_attribute("textContent").strip() for element in visible_balance_elements])
                logger.debug(f"Raw balance text: {balance_text}")

                # Удаление запятых
                balance_text = balance_text.replace(',', '')
                logger.debug(f"Cleaned balance text: {balance_text}")

                # Преобразование в float
                if balance_text.replace('.', '', 1).isdigit():
                    self.balance = float(balance_text)
                else:
                    logger.warning(f"Balance text is invalid: '{balance_text}'")
                    self.balance = 0.0

                # Преобразование float к строке, удаление .0
                if self.balance.is_integer():
                    balance_text = str(int(self.balance))  # Удаляет .0
                self.get_username()
                
                # Логирование
                
                logger.info(f"Account {self.serial_number}: Current balance: {balance_text}")

                # Обновление таблицы
                update_balance_table(self.serial_number, self.username, balance_text)
                return balance_text

            except (NoSuchElementException, TimeoutException) as e:
                logger.warning(f"Account {self.serial_number}: Failed to get balance or username (attempt {retries + 1}): {str(e)}")
                retries += 1
                time.sleep(5)

        # Возврат 0 в случае неудачи
        return "0"

    def get_time(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                parent_block = self.driver.find_element(By.XPATH, "//div[contains(@class, 'flex h-12 flex-1 items-center justify-center')]")
                visible_time_elements = parent_block.find_elements(By.XPATH, ".//span[contains(@class, 'index-module_num__j6XH3') and not(@aria-hidden='true')]")
                time_text = ''.join([element.get_attribute("textContent").strip() for element in visible_time_elements])
                formatted_time = f"{time_text[:2]}:{time_text[2:4]}:{time_text[4:6]}"
                
                logger.info(f"Account {self.serial_number}: Start farm will be available after: {formatted_time}")
                return formatted_time
            except (NoSuchElementException, TimeoutException) as e:
                logger.warning(f"Account {self.serial_number}: Failed to get time (attempt {retries + 1}): {str(e)}")
                logger.debug(traceback.format_exc())  # Логгируем полный стектрейс для отладки
                retries += 1
                time.sleep(5)
        logger.error(f"Account {self.serial_number}: Could not retrieve time after {self.MAX_RETRIES} attempts. Initiating farming.")
        self.farming()  # Повторный вызов farming при неудаче
        return "N/A"

    def farming(self):
        actions = [
            ("/html[1]/body[1]/div[1]/div[1]/main[1]/div[5]/button[1] | /html[1]/body[1]/div[1]/div[1]/main[1]/div[4]/button[1]/div[1] | /html/body/div[1]/div[1]/main/div[4]/button", "'Start farming' button clicked", "'Start farming' button is not active."),
            ("/html[1]/body[1]/div[1]/div[1]/main[1]/div[5]/button[1] | /html[1]/body[1]/div[1]/div[1]/main[1]/div[4]/button[1]/div[1] | /html/body/div[1]/div[1]/main/div[4]/button", "'Collect' button clicked", "'Collect' button is not active.")
        ]

        for xpath, success_msg, fail_msg in actions:
            retries = 0
            while retries < self.MAX_RETRIES:
                try:
                    button = self.driver.find_element(By.XPATH, xpath)
                    button.click()
                    logger.info(f"Account {self.serial_number}: {success_msg}")
                    sleep_time = random.randint(3, 4)
                    logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                    time.sleep(sleep_time)
                    break
                except NoSuchElementException:
                    logger.info(f"Account {self.serial_number}: {fail_msg}")
                    break
                except WebDriverException as e:
                    logger.warning(f"Account {self.serial_number}: Failed action (attempt {retries + 1}): {str(e)}")
                    logger.debug(traceback.format_exc())  # Логгируем полный стектрейс для отладки
                    retries += 1
                    time.sleep(5)
