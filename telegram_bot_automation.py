import random
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, WebDriverException, TimeoutException, StaleElementReferenceException 
from browser_manager import BrowserManager
from utils import setup_logger, suppress_stacktrace
from colorama import Fore, Style
import traceback


# Set up logging with colors
# Настройка логирования
logger = setup_logger()


class TelegramBotAutomation:
    MAX_RETRIES = 3

    def __init__(self, serial_number, settings):
        self.serial_number = serial_number
        self.username = None  # Initialize username as None
        self.balance = 0.0  # Initialize balance as 0.0
        self.browser_manager = BrowserManager(serial_number)
        self.settings = settings
        self.driver = None

        logger.debug(f"Initializing automation for account {serial_number}")

        # Ожидание завершения предыдущей сессии браузера
        if not self.browser_manager.wait_browser_close():
            logger.error(
                f"#{serial_number}: Failed to close previous browser session.")
            raise RuntimeError("Failed to close previous browser session")

        # Запуск браузера
        if not self.browser_manager.start_browser():
            logger.error(f"#{serial_number}: Failed to start browser.")
            raise RuntimeError("Failed to start browser")

        # Сохранение экземпляра драйвера
        self.driver = self.browser_manager.driver
    @suppress_stacktrace
    def perform_quests(self):
        """
        Выполняет доступные квесты в интерфейсе через Selenium.
        """
        logger.info(f"#{self.serial_number}: Looking for available tasks.")
        processed_quests = set()  # Хранение обработанных кнопок

        try:
            # Переключаемся в iframe с квестами
            if not self.switch_to_iframe():
                logger.error(
                    f"#{self.serial_number}: Failed to switch to iframe for quests.")
                return

            while True:
                try:
                    # Находим кнопки квестов с наградами
                    quest_buttons = self.driver.find_elements(
                        By.CSS_SELECTOR, "button.relative.flex.h-\\[74px\\].w-\\[74px\\]")
                    quest_buttons = [
                        btn for btn in quest_buttons
                        if btn not in processed_quests and self.has_reward(btn)
                    ]

                    if not quest_buttons:
                        # logger.info(f"#{self.serial_number}: No more quests available.")
                        break

                    # Берём первый квест из списка
                    current_quest = quest_buttons[0]
                    reward_text = self.get_reward_text(current_quest)
                    logger.info(
                        f"#{self.serial_number}: Found quest with reward: {reward_text}")

                    # Нажимаем на кнопку квеста
                    self.safe_click(current_quest)
                    processed_quests.add(current_quest)

                    # Выполняем взаимодействие с окном квеста
                    if self.interact_with_quest_window():
                        logger.info(
                            f"#{self.serial_number}: Quest with reward {reward_text} completed.")
                    else:
                        logger.warning(
                            f"#{self.serial_number}: Failed to complete quest with reward {reward_text}. Retrying.")
                        break  # Если квест не завершён, прерываем выполнение
                except Exception as e:
                    logger.error(
                        f"#{self.serial_number}: Error while performing quest: {str(e)}")
                    break
        finally:
            # Возвращаемся к главному контенту
            self.driver.switch_to.default_content()
            self.switch_to_iframe()
            logger.info(f"#{self.serial_number}: All quests are completed.")
   
    @suppress_stacktrace
    def has_reward(self, button):
        """
        Проверяет, содержит ли кнопка квеста награду.
        """
        try:
            reward_div = button.find_element(
                By.CSS_SELECTOR, "div.absolute.-bottom-2.-left-2.z-50")
            reward_text = reward_div.text.strip()
            return bool(reward_text and reward_text.startswith("+"))
        except Exception:
            return False

    @suppress_stacktrace
    def get_reward_text(self, button):
        """
        Получает текст награды из кнопки квеста.
        """
        try:
            reward_div = button.find_element(
                By.CSS_SELECTOR, "div.absolute.-bottom-2.-left-2.z-50")
            return reward_div.text.strip()
        except Exception:
            return "Unknown"

    @suppress_stacktrace
    def interact_with_quest_window(self):
        """
        Взаимодействует с окном квеста до его закрытия.
        """
        try:
            # Ожидаем появления окна квеста
            quest_window = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@style, 'position: absolute; height: inherit; width: inherit;')]"))
            )
            # logger.info(f"#{self.serial_number}: Quest window detected. Starting interaction.")

            retries = 0  # Счётчик попыток
            while retries < 10:  # Ограничение на 10 попыток взаимодействия
                # Проверяем, закрыто ли окно квеста
                quest_window = self.driver.find_elements(
                    By.XPATH, "//div[contains(@style, 'position: absolute; height: inherit; width: inherit;')]")
                if not quest_window:
                    logger.info(
                        f"#{self.serial_number}: Quest window closed. Interaction complete.")
                    return True  # Окно квеста успешно закрыто

                # Пытаемся найти элемент для клика в правой половине
                quest_element = self.wait_for_element(
                    By.XPATH, "/html/body/div[5]/div/div[3]/div[2]", timeout=5)
                if quest_element:
                    self.safe_click(quest_element)
                    # logger.info(f"#{self.serial_number}: Clicked on the right side of the quest window.")
                else:
                    logger.warning(
                        f"#{self.serial_number}: Right-side element not found. Retrying.")
                    retries += 1
                    time.sleep(1)
                    continue

                # Проверяем снова, закрыто ли окно после клика
                time.sleep(1)  # Небольшая пауза для обновления состояния
                updated_quest_window = self.driver.find_elements(
                    By.XPATH, "//div[contains(@style, 'position: absolute; height: inherit; width: inherit;')]")
                if not updated_quest_window:
                    # logger.info(f"#{self.serial_number}: Quest window successfully closed after click.")
                    return True

                retries += 1
                time.sleep(1)  # Пауза перед следующей попыткой

            # Если после 10 попыток окно не закрылось
            logger.warning(
                f"#{self.serial_number}: Quest window did not close after maximum retries.")
            return False
        except TimeoutException:
            logger.warning(
                f"#{self.serial_number}: Quest window did not appear in time.")
            return False
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Error interacting with quest window: {str(e)}")
            return False

    @suppress_stacktrace
    def safe_click(self, element):
        """
        Безопасный клик по элементу.
        """
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element)
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(element))
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
                logger.debug(
                    f"#{self.serial_number}: Navigated to Telegram web.")
                self.close_extra_windows()
                sleep_time = random.randint(5, 7)
                logger.debug(
                    f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                time.sleep(sleep_time)
                return True
            except (WebDriverException, TimeoutException) as e:
                logger.warning(
                    f"#{self.serial_number}: Exception in navigating to Telegram bot (attempt {retries + 1}): {str(e)}")
                retries += 1
                time.sleep(5)
        return False
    
    @suppress_stacktrace
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
            logger.warning(
                f"#{self.serial_number}: Exception while closing extra windows: {str(e)}")

    @suppress_stacktrace
    def send_message(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                chat_input_area = self.wait_for_element(
                    By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/input[1]')
                if chat_input_area:
                    chat_input_area.click()
                    group_url = self.settings.get(
                        'TELEGRAM_GROUP_URL', 'https://t.me/CryptoProjects_sbt')
                    chat_input_area.send_keys(group_url)

                search_area = self.wait_for_element(
                    By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/ul[1]/a[1]/div[1]')
                if search_area:
                    search_area.click()
                    logger.debug(
                        f"#{self.serial_number}: Group searched.")
                sleep_time = random.randint(5, 7)
                logger.debug(
                    f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                time.sleep(sleep_time)
                return True
            except (NoSuchElementException, WebDriverException) as e:
                logger.warning(
                    f"#{self.serial_number}: Failed to perform action (attempt {retries + 1}): {str(e)}")
                retries += 1
                time.sleep(5)
        return False
    
    @suppress_stacktrace
    def check_iframe_src(self):
        """
        Проверяет, загружен ли правильный iframe по URL в атрибуте src с ожиданием.
        """
        try:
            # Ждем появления iframe в течение 15 секунд
            iframe = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            iframe_src = iframe.get_attribute("src")
            
            # Проверяем, соответствует ли src ожидаемому значению
            if "nutsfarm.crypton.xyz" in iframe_src and "tgWebAppData" in iframe_src:
                logger.debug(f"#{self.serial_number}: Iframe src indicates the app is loaded: {iframe_src}")
                return True
            else:
                logger.warning(f"#{self.serial_number}: Unexpected iframe src: {iframe_src}")
                return False
        except TimeoutException:
            logger.error(f"#{self.serial_number}: App not loaded within the timeout.")
            return False
        except Exception as e:
            logger.debug(f"#{self.serial_number}: Unexpected error while checking iframe src: {str(e)}")
            return False

    @suppress_stacktrace
    def click_link(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                # Получаем ссылку из настроек
                bot_link = self.settings.get(
                    'BOT_LINK', 'https://t.me/nutsfarm_bot/nutscoin?startapp=ref_YCNYYSFWGOQTBFS')

                # Поиск элемента ссылки
                link = self.wait_for_element(
                    By.CSS_SELECTOR, f"a[href*='{bot_link}']")
                if link:
                    # Скроллинг к ссылке
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", link)
                    # Небольшая задержка для завершения скроллинга
                    time.sleep(1)

                    # Клик по ссылке
                    link.click()
                    logger.debug(f"#{self.serial_number}: Link clicked.")
                    time.sleep(2)

                # Поиск и клик по кнопке запуска
                launch_button = self.wait_for_element(
                    By.CSS_SELECTOR, "button.popup-button.btn.primary.rp", timeout=5)
                if launch_button:
                    launch_button.click()
                    logger.debug(f"#{self.serial_number}: Launch button clicked.")

                # Проверка iframe
                if self.check_iframe_src():
                    # Лог успешного запуска
                    logger.info(f"#{self.serial_number}: App loaded successfully.")

                    # Случайная задержка перед переключением на iframe
                    sleep_time = random.randint(3, 5)
                    logger.debug(
                        f"#{self.serial_number}: Sleeping for {sleep_time} seconds before switching to iframe.")
                    time.sleep(sleep_time)

                    # Переключение на iframe
                    self.switch_to_iframe()
                    logger.debug(f"#{self.serial_number}: Switched to iframe.")
                    return True
                else:
                    raise Exception(f"#{self.serial_number}: Iframe not loaded with expected content.")

            except (NoSuchElementException, WebDriverException, TimeoutException) as e:
                logger.warning(
                    f"#{self.serial_number}: Failed to click link or interact with elements (attempt {retries + 1}): {str(e).splitlines()[0]}")
                retries += 1
                time.sleep(5)

        # Возвращаем False, если все попытки завершились неудачно
        return False


    @suppress_stacktrace
    def wait_for_element(self, by, value, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
        except TimeoutException:
            # logger.warning(f"#{self.serial_number}: Failed to find the element located by {by} with value {value} within {timeout} seconds.")
            return None
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error while waiting for element: {str(e)}")
            return None

    @suppress_stacktrace
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

    @suppress_stacktrace
    def preparing_account(self):
        actions = [
            ("/html/body/div[1]/div/button", "First start button claimed"),
            ("//button[contains(text(), 'Click now')]", "'Click now' button clicked"),
            ("/html/body/div[2]/div[2]/button", "Claimed welcome bonus: 1337 NUTS"),
            ("/html/body/div[2]/div[2]/div[2]/button", "Daily reward claimed")
        ]

        for xpath, success_msg in actions:
            retries = 0
            while retries < self.MAX_RETRIES:
                try:
                    # Поиск элемента по XPath
                    element = self.driver.find_element(By.XPATH, xpath)

                    # Клик по элементу
                    element.click()

                    # Лог успешного нажатия
                    logger.info(f"#{self.serial_number}: {success_msg}")

                    # Сон перед следующей попыткой
                    sleep_time = random.randint(5, 7)
                    logger.debug(
                        f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                    time.sleep(sleep_time)
                    break  # Завершаем попытки, если успешно нажали
                except NoSuchElementException:
                    # Элемент не найден, переход к следующему действию
                    logger.debug(f"#{self.serial_number}: Element not found for action: {success_msg}")
                    break
                except WebDriverException as e:
                    # Обработка исключения WebDriverException
                    retries += 1
                    logger.warning(
                        f"#{self.serial_number}: Failed action (attempt {retries}): {str(e)}")
                    time.sleep(5)
                    # Если количество попыток превышено, просто переходим к следующему
                    if retries >= self.MAX_RETRIES:
                        logger.error(f"#{self.serial_number}: Exceeded maximum retries for action: {success_msg}")
                        break

    @suppress_stacktrace
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
                # logger.info(f"#{self.serial_number}: Switched to iframe.")
                return True
            else:
                logger.warning(
                    f"#{self.serial_number}: No iframe found to switch.")
                return False
        except NoSuchElementException:
            logger.warning(f"#{self.serial_number}: No iframe found.")
            return False
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error while switching to iframe: {str(e)}")
            return False

    @suppress_stacktrace
    def get_username(self):
        # Получение имени пользователя
        username_block = WebDriverWait(self.driver, 10).until(
            # Укажите точный XPATH для username
            EC.presence_of_element_located((By.XPATH, "//header/button/p"))
        )
        username = username_block.get_attribute("textContent").strip()
        # logger.info(f"#{self.serial_number}: Current username: {username}")
        return username

    @suppress_stacktrace
    def get_balance(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                # Ожидание контейнера с балансом
                parent_block = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@class, 'flex items-center font-tt-hoves')]"))
                )
                logger.debug("Parent block for balance found.")

                # Поиск всех чисел в балансе
                visible_balance_elements = parent_block.find_elements(
                    By.XPATH, ".//span[contains(@class, 'index-module_num__j6XH3') and not(@aria-hidden='true')]")
                logger.debug(
                    f"Extracted raw balance elements: {[el.get_attribute('textContent').strip() for el in visible_balance_elements]}")

                # Сбор текста чисел и объединение в строку
                balance_text = ''.join([element.get_attribute(
                    "textContent").strip() for element in visible_balance_elements])
                logger.debug(f"Raw balance text: {balance_text}")

                # Удаление запятых
                balance_text = balance_text.replace(',', '')
                logger.debug(f"Cleaned balance text: {balance_text}")

                # Преобразование в float
                if balance_text.replace('.', '', 1).isdigit():
                    self.balance = float(balance_text)
                else:
                    logger.warning(
                        f"Balance text is invalid: '{balance_text}'")
                    self.balance = 0.0

                # Преобразование float к строке, удаление .0
                if self.balance.is_integer():
                    balance_text = str(int(self.balance))  # Удаляет .0
                self.get_username()

                # Логирование

                logger.info(
                    f"#{self.serial_number}: Current balance: {balance_text}")

                # # Обновление таблицы
                # update_balance_table(self.serial_number,
                #                      self.username, balance_text)
                return balance_text

            except (NoSuchElementException, TimeoutException) as e:
                logger.warning(
                    f"#{self.serial_number}: Failed to get balance or username (attempt {retries + 1}): {str(e).splitlines()[0]}")
                retries += 1
                time.sleep(5)

        # Возврат 0 в случае неудачи
        return "0"    

    @suppress_stacktrace
    def get_time(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                # Ищем элемент, содержащий текст "Осталось" или "Get after"
                all_elements = self.driver.find_elements(By.TAG_NAME, "span")

                parent_element = None
                for element in all_elements:
                    try:
                        text = element.text.strip().lower()
                        if "осталось" in text or "get after" in text:
                            parent_element = element
                            break
                    except StaleElementReferenceException:
                        # Если элемент устарел, пропускаем его
                        logger.debug(f"#{self.serial_number}: Stale element encountered while searching for parent element. Retrying...")
                        continue

                if not parent_element:
                    raise NoSuchElementException(
                        "No element with text 'Осталось' or 'Get after' found.")

                # Логируем найденный контейнер
                logger.debug(
                    f"Found parent element: {parent_element.get_attribute('outerHTML')}")

                # Извлекаем все вложенные элементы и ищем цифры
                child_elements = parent_element.find_elements(By.XPATH, ".//span")

                visible_digits = []
                for child in child_elements:
                    try:
                        text = child.get_attribute("textContent").strip()
                        aria_hidden = child.get_attribute("aria-hidden")
                        if (not aria_hidden or aria_hidden.lower() == "false") and text.isdigit() and len(text) == 1:
                            visible_digits.append(text)
                    except StaleElementReferenceException:
                        # Если элемент устарел, пропускаем его
                        logger.debug(f"#{self.serial_number}: Stale element encountered while processing child elements. Retrying...")
                        continue

                logger.debug(f"Visible digits collected: {visible_digits}")

                # Проверяем, достаточно ли цифр для формирования времени
                if len(visible_digits) >= 6:
                    time_text = ''.join(visible_digits[:6])
                    formatted_time = f"{time_text[:2]}:{time_text[2:4]}:{time_text[4:6]}"
                    logger.info(f"#{self.serial_number}: Start farm will be available after: {formatted_time}")
                    return formatted_time
                else:
                    raise NoSuchElementException(
                        "Not enough visible digits to form time.")

            except (NoSuchElementException, TimeoutException) as e:
                retries += 1
                logger.warning(f"#{self.serial_number}: Failed to get time (attempt {retries}): {str(e)}")
                logger.debug(traceback.format_exc())
                logger.info(f"#{self.serial_number}: Initiating farming due to get_time error.")
                self.farming()  # Вызываем farming при ошибке
                time.sleep(5)
            except StaleElementReferenceException:
                retries += 1
                logger.warning(f"#{self.serial_number}: Encountered stale element reference (attempt {retries}). Retrying...")
                time.sleep(2)  # Пауза перед повторным поиском элементов
            except Exception as e:
                logger.error(f"#{self.serial_number}: Unexpected error during time extraction: {str(e)}")
                logger.debug(traceback.format_exc())
                return "N/A"

        # Если превышено количество попыток, просто возвращаем "N/A"
        logger.error(f"#{self.serial_number}: Could not retrieve time after {self.MAX_RETRIES} attempts.")
        return "N/A"

    @suppress_stacktrace
    def farming(self):
        actions = [
            ("/html[1]/body[1]/div[1]/div[1]/main[1]/div[5]/button[1] | /html[1]/body[1]/div[1]/div[1]/main[1]/div[4]/button[1]/div[1] | /html/body/div[1]/div[1]/main/div[4]/button",
             "'Start farming' button clicked"),
            ("/html[1]/body[1]/div[1]/div[1]/main[1]/div[5]/button[1] | /html[1]/body[1]/div[1]/div[1]/main[1]/div[4]/button[1]/div[1] | /html/body/div[1]/div[1]/main/div[4]/button",
             "'Collect' button clicked")
        ]

        for xpath, success_msg in actions:
            retries = 0
            while retries < self.MAX_RETRIES:
                try:
                    button = self.driver.find_element(By.XPATH, xpath)
                    button.click()
                    logger.info(f"#{self.serial_number}: {success_msg}")
                    sleep_time = random.randint(3, 4)
                    logger.debug(
                        f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                    time.sleep(sleep_time)
                    break
                except NoSuchElementException:
                    # Если элемент не найден, просто переходим к следующему действию
                    break
                except WebDriverException as e:
                    logger.warning(
                        f"#{self.serial_number}: Failed action (attempt {retries + 1}): {str(e).splitlines()[0]}")
                    # Логгируем полный стектрейс для отладки
                    logger.debug(traceback.format_exc())
                    retries += 1
                    time.sleep(5)

