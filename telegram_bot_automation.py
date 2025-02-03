import random
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, WebDriverException, TimeoutException, StaleElementReferenceException
from browser_manager import BrowserManager
from rapidfuzz import fuzz
from utils import stop_event
from colorama import Fore, Style
import traceback
import logging

# Настроим логирование (если не было настроено ранее)
logger = logging.getLogger("application_logger")


class TelegramBotAutomation:
    MAX_RETRIES = 3

    def __init__(self, serial_number, settings):
        try:
            self.serial_number = serial_number
            self.username = None  # Initialize username as None
            self.balance = 0.0  # Initialize balance as 0.0
            self.browser_manager = BrowserManager(serial_number)
            self.settings = settings
            self.driver = None

            logger.debug(
                f"Initializing automation for account {serial_number}")

            # Ожидание завершения предыдущей сессии браузера
            logger.debug(
                f"#{serial_number}: Waiting for the previous browser session to close...")
            if not self.browser_manager.wait_browser_close():
                logger.error(
                    f"#{serial_number}: Failed to close previous browser session.")
                raise RuntimeError("Failed to close previous browser session")

            logger.debug(
                f"#{serial_number}: Previous browser session closed successfully.")

            # Запуск браузера
            logger.debug(f"#{serial_number}: Starting browser...")
            if not self.browser_manager.start_browser():
                logger.error(f"#{serial_number}: Failed to start browser.")
                raise RuntimeError("Failed to start browser")

            logger.debug(f"#{serial_number}: Browser started successfully.")

            # Сохранение экземпляра драйвера
            self.driver = self.browser_manager.driver
            logger.debug(
                f"#{serial_number}: Driver instance saved successfully.")

        except (WebDriverException, StaleElementReferenceException) as e:
            error_message = str(e).splitlines()[0]
            logger.warning(f"__init__: Exception occurred: {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in __init__: {e}")
            raise

    def perform_quests(self):
        """
        Выполняет доступные квесты в интерфейсе через Selenium с поддержкой остановки через stop_event.
        """
        logger.info(f"#{self.serial_number}: Looking for available quests.")
        processed_quests = set()  # Хранение обработанных кнопок

        try:
            # Переключаемся в iframe с квестами
            if not self.switch_to_iframe():
                logger.error(
                    f"#{self.serial_number}: Failed to switch to iframe for quests.")
                return

            while not stop_event.is_set():  # Проверка флага остановки
                try:
                    if stop_event.is_set():  # Дополнительная проверка перед итерацией
                        break

                    logger.debug(
                        f"#{self.serial_number}: Searching for quest buttons.")
                    # Находим кнопки квестов с наградами
                    quest_buttons = self.driver.find_elements(
                        By.CSS_SELECTOR, "button.relative"
                    )
                    if stop_event.is_set():  # Проверка после долгой операции
                        break

                    logger.debug(
                        f"#{self.serial_number}: Found {len(quest_buttons)} quest buttons.")

                    quest_buttons = [
                        btn for btn in quest_buttons
                        if btn not in processed_quests and self.has_reward(btn)
                    ]
                    logger.debug(
                        f"#{self.serial_number}: Filtered {len(quest_buttons)} quest buttons with rewards.")

                    if not quest_buttons:
                        logger.debug(
                            f"#{self.serial_number}: No more quests available.")
                        break

                    # Берём первый квест из списка
                    current_quest = quest_buttons[0]
                    reward_text = self.get_reward_text(current_quest)
                    logger.info(
                        f"#{self.serial_number}: Found quest with reward: {reward_text}")

                    # Проверка перед кликом
                    if stop_event.is_set():
                        break

                    logger.debug(
                        f"#{self.serial_number}: Clicking on quest button.")
                    self.safe_click(current_quest)
                    processed_quests.add(current_quest)

                    if stop_event.is_set():  # Проверка после клика
                        break

                    # Выполняем взаимодействие с окном квеста
                    if self.interact_with_quest_window():
                        logger.info(
                            f"#{self.serial_number}: Quest with reward {reward_text} completed.")
                    else:
                        logger.warning(
                            f"#{self.serial_number}: Failed to complete quest with reward {reward_text}. Retrying.")
                        break  # Если квест не завершён, прерываем выполнение

                except (WebDriverException, StaleElementReferenceException) as e:
                    error_message = str(e).splitlines()[0]
                    logger.warning(
                        f"#{self.serial_number}: Exception occurred: {error_message}")
                    break
                except Exception as e:
                    logger.error(
                        f"#{self.serial_number}: Unexpected error while performing quest: {str(e)}")
                    break

        finally:
            # Возвращаемся к главному контенту
            logger.debug(
                f"#{self.serial_number}: Switching back to default content.")
            self.driver.switch_to.default_content()
            self.switch_to_iframe()
            logger.info(f"#{self.serial_number}: All quests are completed.")

    def has_reward(self, button):
        """
        Проверяет, содержит ли кнопка квеста награду.
        """
        try:
            logger.debug(f"Checking if button {button} contains a reward.")
            reward_div = button.find_element(
                By.CSS_SELECTOR, "div.absolute.-bottom-2.-left-2.z-50"
            )
            reward_text = reward_div.text.strip()
            logger.debug(f"Reward text found: '{reward_text}'")
            return bool(reward_text and reward_text.startswith("+"))
        except (WebDriverException, StaleElementReferenceException) as e:
            error_message = str(e).splitlines()[0]
            logger.debug(
                f"Exception while checking reward for button {button}: {error_message}")
        except Exception as e:
            logger.error(
                f"Unexpected error while checking reward for button {button}: {e}")
        return False

    def get_reward_text(self, button):
        """
        Получает текст награды из кнопки квеста.
        """
        try:
            logger.debug(
                f"Attempting to retrieve reward text from button {button}.")
            reward_div = button.find_element(
                By.CSS_SELECTOR, "div.absolute.-bottom-2.-left-2.z-50"
            )
            reward_text = reward_div.text.strip()
            logger.debug(f"Reward text retrieved: '{reward_text}'")
            return reward_text
        except (WebDriverException, StaleElementReferenceException) as e:
            error_message = str(e).splitlines()[0]
            logger.debug(
                f"Exception while retrieving reward text from button {button}: {error_message}")
        except Exception as e:
            logger.error(
                f"Unexpected error while retrieving reward text from button {button}: {e}")
        return "Unknown"

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
                    logger.debug(
                        f"#{self.serial_number}: Right-side element not found. Retrying.")
                    retries += 1
                    stop_event.wait(1)
                    continue

                # Проверяем снова, закрыто ли окно после клика
                stop_event.wait(1)  # Небольшая пауза для обновления состояния
                updated_quest_window = self.driver.find_elements(
                    By.XPATH, "//div[contains(@style, 'position: absolute; height: inherit; width: inherit;')]")
                if not updated_quest_window:
                    # logger.info(f"#{self.serial_number}: Quest window successfully closed after click.")
                    return True

                retries += 1
                stop_event.wait(1)  # Пауза перед следующей попыткой

            # Если после 10 попыток окно не закрылось
            logger.warning(
                f"#{self.serial_number}: Quest window did not close after maximum retries.")
            return False
        except TimeoutException:
            logger.debug(
                f"#{self.serial_number}: Quest window did not appear in time.")
            return False
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Error interacting with quest window: {str(e)}")
            return False

    def safe_click(self, element):
        """
        Безопасный клик по элементу.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Attempting to scroll to element.")
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element)
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(element))
            element.click()
            logger.debug(
                f"#{self.serial_number}: Element clicked successfully.")
        except (WebDriverException, StaleElementReferenceException) as e:
            error_message = str(e).splitlines()[0]
            logger.debug(
                f"#{self.serial_number}: Error during safe click: {error_message}")
            try:
                logger.debug(
                    f"#{self.serial_number}: Attempting JavaScript click as fallback.")
                self.driver.execute_script("arguments[0].click();", element)
                logger.debug(
                    f"#{self.serial_number}: JavaScript click succeeded.")
            except (WebDriverException, StaleElementReferenceException) as e:
                error_message = str(e).splitlines()[0]
                logger.error(
                    f"#{self.serial_number}: JavaScript click failed: {error_message}")
            except Exception as e:
                logger.error(
                    f"#{self.serial_number}: Unexpected error during fallback click: {e}")
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error during safe click: {e}")

    def navigate_to_bot(self):
        """
        Очищает кэш браузера, загружает Telegram Web и закрывает лишние окна.
        """
        logger.debug(
            f"#{self.serial_number}: Starting navigation to Telegram web.")

        # Очистка кэша с проверкой stop_event
        self.clear_browser_cache_and_reload()
        if stop_event.is_set():
            return False

        retries = 0
        while retries < self.MAX_RETRIES:
            if stop_event.is_set():
                return False

            try:
                logger.debug(
                    f"#{self.serial_number}: Attempting to load Telegram web (attempt {retries + 1}).")
                self.driver.get('https://web.telegram.org/k/')
                if stop_event.is_set():
                    return False

                logger.debug(
                    f"#{self.serial_number}: Telegram web loaded successfully.")
                self.close_extra_windows()

                # Упрощённое ожидание с проверкой stop_event
                for _ in range(random.randint(5, 7)):
                    if stop_event.wait(1):  # Ждём с прерыванием
                        logger.debug(
                            f"#{self.serial_number}: Stopping wait due to stop_event.")
                        return False

                return True

            except (WebDriverException, TimeoutException) as e:
                logger.debug(
                    f"#{self.serial_number}: Exception in navigating to Telegram bot (attempt {retries + 1}): {e}")
                retries += 1

                # Ожидание перед повторной попыткой
                if stop_event.wait(5):  # Ждём 5 секунд с прерыванием
                    logger.debug(
                        f"#{self.serial_number}: Stopping retry due to stop_event.")
                    return False

        logger.debug(
            f"#{self.serial_number}: Failed to navigate to Telegram web after {self.MAX_RETRIES} attempts.")
        return False

    def close_extra_windows(self):
        """
        Закрывает все дополнительные окна, кроме текущего.
        """
        try:
            current_window = self.driver.current_window_handle
            all_windows = self.driver.window_handles

            logger.debug(
                f"#{self.serial_number}: Current window handle: {current_window}")
            logger.debug(
                f"#{self.serial_number}: Total open windows: {len(all_windows)}")

            for window in all_windows:
                if window != current_window:
                    logger.debug(
                        f"#{self.serial_number}: Closing window: {window}")
                    self.driver.switch_to.window(window)
                    self.driver.close()
                    logger.debug(
                        f"#{self.serial_number}: Window {window} closed successfully.")

            # Переключаемся обратно на исходное окно
            self.driver.switch_to.window(current_window)
            logger.debug(
                f"#{self.serial_number}: Switched back to the current window: {current_window}")
        except WebDriverException as e:
            error_message = str(e).splitlines()[0]
            logger.debug(
                f"#{self.serial_number}: Exception while closing extra windows: {error_message}")
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error during closing extra windows: {e}")

    def send_message(self):
        """
        Отправляет сообщение в указанный Telegram-групповой чат.
        """
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                logger.debug(
                    f"#{self.serial_number}: Attempt {retries + 1} to send message.")

                # Находим область ввода сообщения
                chat_input_area = self.wait_for_element(
                    By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/input[1]'
                )
                if chat_input_area:
                    logger.debug(
                        f"#{self.serial_number}: Chat input area found.")
                    chat_input_area.click()
                    group_url = self.settings.get(
                        'TELEGRAM_GROUP_URL', 'https://t.me/CryptoProjects_sbt'
                    )
                    logger.debug(
                        f"#{self.serial_number}: Typing group URL: {group_url}")
                    chat_input_area.send_keys(group_url)
                else:
                    logger.warning(
                        f"#{self.serial_number}: Chat input area not found.")
                    retries += 1
                    stop_event.wait(5)
                    continue

                # Находим область поиска
                search_area = self.wait_for_element(
                    By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/ul[1]/a[1]/div[1]'
                )
                if search_area:
                    logger.debug(f"#{self.serial_number}: Search area found.")
                    search_area.click()
                    logger.debug(
                        f"#{self.serial_number}: Group search clicked.")
                else:
                    logger.warning(
                        f"#{self.serial_number}: Search area not found.")
                    retries += 1
                    stop_event.wait(5)
                    continue

                # Добавляем задержку перед завершением
                sleep_time = random.randint(5, 7)
                logger.debug(
                    f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                stop_event.wait(sleep_time)
                logger.debug(
                    f"#{self.serial_number}: Message successfully sent to the group.")
                return True
            except (NoSuchElementException, WebDriverException) as e:
                error_message = str(e).splitlines()[0]
                logger.warning(
                    f"#{self.serial_number}: Failed to perform action (attempt {retries + 1}): {error_message}")
                retries += 1
                stop_event.wait(5)
            except Exception as e:
                logger.error(f"#{self.serial_number}: Unexpected error: {e}")
                break

        logger.error(
            f"#{self.serial_number}: Failed to send message after {self.MAX_RETRIES} attempts.")
        return False

    def check_iframe_src(self):
        """
        Проверяет, загружен ли правильный iframe по URL в атрибуте src с ожиданием.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Waiting for iframe to appear...")

            # Ждем появления iframe в течение 20 секунд
            iframe = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            logger.debug(
                f"#{self.serial_number}: Iframe detected. Checking src attribute.")

            iframe_src = iframe.get_attribute("src")

            # Проверяем, соответствует ли src ожидаемому значению
            if "nutsfarm.crypton.xyz" in iframe_src and "tgWebAppData" in iframe_src:
                logger.debug(
                    f"#{self.serial_number}: Iframe src is valid: {iframe_src}")
                return True
            else:
                logger.warning(
                    f"#{self.serial_number}: Unexpected iframe src: {iframe_src}")
                return False
        except TimeoutException:
            logger.error(
                f"#{self.serial_number}: Iframe not found within the timeout period.")
            return False
        except (WebDriverException, Exception) as e:
            logger.warning(
                f"#{self.serial_number}: Error while checking iframe src: {str(e).splitlines()[0]}")
            return False

    def click_link(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                logger.debug(
                    f"#{self.serial_number}: Attempt {retries + 1} to click link.")

                # Получаем ссылку из настроек
                bot_link = self.settings.get(
                    'BOT_LINK', 'https://t.me/nutsfarm_bot/nutscoin?startapp=ref_YCNYYSFWGOQTBFS')
                logger.debug(f"#{self.serial_number}: Bot link: {bot_link}")

                # Ожидание перед началом поиска
                # Увеличенное ожидание перед первой проверкой
                stop_event.wait(3)

                scroll_attempts = 0
                max_scrolls = 20  # Максимальное количество прокруток

                while scroll_attempts < max_scrolls:
                    # Ожидаем появления всех ссылок, начинающихся с https://t.me
                    try:
                        links = WebDriverWait(self.driver, 5).until(
                            lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='https://t.me']"))
                    except TimeoutException:
                        logger.warning(
                            f"#{self.serial_number}: Links did not load in time.")
                        break

                    logger.debug(
                        f"#{self.serial_number}: Found {len(links)} links starting with 'https://t.me/'.")

                    # Прокручиваемся к каждой ссылке поочередно
                    for link in links:
                        href = link.get_attribute("href")
                        if bot_link in href:
                            logger.debug(
                                f"#{self.serial_number}: Found matching link: {href}")

                            # Скроллинг к нужной ссылке
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", link)
                            # Небольшая задержка после прокрутки
                            stop_event.wait(0.5)

                            # Клик по ссылке
                            link.click()
                            logger.debug(
                                f"#{self.serial_number}: Link clicked successfully.")
                            stop_event.wait(2)

                            # Поиск и клик по кнопке запуска
                            launch_button = self.wait_for_element(
                                By.CSS_SELECTOR, "button.popup-button.btn.primary.rp", timeout=5)
                            if launch_button:
                                logger.debug(
                                    f"#{self.serial_number}: Launch button found. Clicking it.")
                                launch_button.click()
                                logger.debug(
                                    f"#{self.serial_number}: Launch button clicked.")

                            # Проверка iframe
                            if self.check_iframe_src():
                                logger.info(
                                    f"#{self.serial_number}: App loaded successfully.")

                                # Случайная задержка перед переключением на iframe
                                sleep_time = random.randint(3, 5)
                                logger.debug(
                                    f"#{self.serial_number}: Sleeping for {sleep_time} seconds before switching to iframe.")
                                stop_event.wait(sleep_time)

                                # Переключение на iframe
                                self.switch_to_iframe()
                                logger.debug(
                                    f"#{self.serial_number}: Switched to iframe successfully.")
                                return True
                            else:
                                logger.warning(
                                    f"#{self.serial_number}: Iframe did not load expected content.")
                                raise Exception(
                                    "Iframe content validation failed.")

                    # Если нужная ссылка не найдена, прокручиваемся к первому элементу
                    logger.debug(
                        f"#{self.serial_number}: Scrolling up (attempt {scroll_attempts + 1}).")
                    if links:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'start' });", links[0])
                    else:
                        logger.debug(
                            f"#{self.serial_number}: No links found to scroll to.")
                        break

                    # Небольшая задержка для загрузки контента
                    stop_event.wait(0.5)
                    scroll_attempts += 1

                    # Проверяем позицию страницы
                    current_position = self.driver.execute_script(
                        "return window.pageYOffset;")
                    logger.debug(
                        f"#{self.serial_number}: Current scroll position: {current_position}")
                    if current_position == 0:  # Если достигнут верх страницы
                        logger.debug(
                            f"#{self.serial_number}: Reached the top of the page.")
                        break

                # Если не удалось найти ссылку
                logger.debug(
                    f"#{self.serial_number}: No matching link found after scrolling through all links.")
                retries += 1
                stop_event.wait(5)

            except (NoSuchElementException, WebDriverException, TimeoutException) as e:
                logger.debug(
                    f"#{self.serial_number}: Failed to click link or interact with elements (attempt {retries + 1}): {str(e).splitlines()[0]}")
                retries += 1
                stop_event.wait(5)
            except Exception as e:
                logger.error(
                    f"#{self.serial_number}: Unexpected error during click_link: {str(e).splitlines()[0]}")
                break

        logger.error(
            f"#{self.serial_number}: All attempts to click link failed after {self.MAX_RETRIES} retries.")
        return False

    def wait_for_page_load(self, timeout=30):
        """
        Ожидание полной загрузки страницы с помощью проверки document.readyState.

        :param driver: WebDriver Selenium.
        :param timeout: Максимальное время ожидания.
        """
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script(
                "return document.readyState") == "complete"
        )

    def wait_for_element(self, by, value, timeout=10):
        """
        Ожидает, пока элемент станет кликабельным, в течение указанного времени.

        :param by: Метод локатора (например, By.XPATH, By.ID).
        :param value: Значение локатора.
        :param timeout: Время ожидания в секундах (по умолчанию 10).
        :return: Найденный элемент, если он кликабельный, иначе None.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Waiting for element by {by} with value '{value}' for up to {timeout} seconds."
            )

            # Ожидание с проверкой stop_event
            for _ in range(timeout):
                if stop_event.is_set():
                    logger.debug(
                        f"#{self.serial_number}: Stop event detected during wait for element.")
                    return None

                try:
                    element = WebDriverWait(self.driver, 1).until(
                        EC.element_to_be_clickable((by, value))
                    )
                    logger.debug(
                        f"#{self.serial_number}: Element found and clickable: {value}")
                    return element
                except TimeoutException:
                    continue  # Продолжаем цикл, если элемент пока не найден

            logger.debug(
                f"#{self.serial_number}: Element not found or not clickable within {timeout} seconds: {value}"
            )
            return None
        except (WebDriverException, StaleElementReferenceException) as e:
            logger.debug(
                f"#{self.serial_number}: Error while waiting for element {value}: {str(e).splitlines()[0]}"
            )
            return None
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error while waiting for element: {str(e)}"
            )
            return None

    def clear_browser_cache_and_reload(self):
        """
        Очищает кэш браузера, IndexedDB для https://web.telegram.org и перезагружает текущую страницу.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Attempting to clear browser cache and IndexedDB for https://web.telegram.org.")

            # Очистка кэша через CDP команду
            self.driver.execute_cdp_cmd("Network.clearBrowserCache", {})
            logger.debug(
                f"#{self.serial_number}: Browser cache successfully cleared.")

            # Очистка IndexedDB для https://web.telegram.org
            self.driver.execute_cdp_cmd("Storage.clearDataForOrigin", {
                "origin": "https://web.telegram.org",
                "storageTypes": "indexeddb"
            })
            logger.debug(
                f"#{self.serial_number}: IndexedDB successfully cleared for https://web.telegram.org.")

            # Перезагрузка текущей страницы
            logger.debug(f"#{self.serial_number}: Refreshing the page.")
            self.driver.refresh()
            logger.debug(
                f"#{self.serial_number}: Page successfully refreshed.")
        except WebDriverException as e:
            logger.warning(
                f"#{self.serial_number}: WebDriverException while clearing cache or reloading page: {str(e).splitlines()[0]}")
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error during cache clearing or page reload: {str(e)}")

    def preparing_account(self):
        stop_event.wait(15)
        """
        Выполняет подготовительные действия для аккаунта с поддержкой остановки через stop_event.
        """
        actions = [
            ("(//button[contains(@class, 'group relative flex h-14 w-full items-start outline-none')])[1]",
             "Freeze button clicked"),
            ("/html/body/div[2]/div[2]/div[2]/div[3]/div[4]/button[1]",
             "Freeze button clicked"),
            ("/html/body/div[1]/div/button", "First start button claimed"),
            ("//button[contains(text(), 'Click now')]",
             "'Click now' button clicked"),
            ("/html/body/div[2]/div[2]/button",
             "Claimed welcome bonus: 1337 NUTS"),
            ("/html/body/div[2]/div[2]/div[2]/button", "Daily reward claimed")

        ]

        for xpath, success_msg in actions:
            retries = 0
            logger.debug(
                f"#{self.serial_number}: Starting action for XPath: {xpath}")

            while retries < self.MAX_RETRIES:
                if stop_event.is_set():  # Проверка на остановку перед выполнением действия
                    logger.info(
                        f"#{self.serial_number}: Stop event detected. Exiting preparing_account.")
                    return

                try:
                    # Поиск элемента по XPath
                    logger.debug(
                        f"#{self.serial_number}: Attempting to locate element for action: {success_msg}")
                    element = self.driver.find_element(By.XPATH, xpath)
                    logger.debug(
                        f"#{self.serial_number}: Element located. Attempting to click.")

                    # Клик по элементу
                    element.click()
                    logger.info(f"#{self.serial_number}: {success_msg}")

                    # Сон перед следующим действием с проверкой stop_event
                    sleep_time = random.randint(5, 7)
                    logger.debug(
                        f"#{self.serial_number}: Sleeping for {sleep_time} seconds after action.")
                    for _ in range(sleep_time):
                        if stop_event.is_set():
                            logger.info(
                                f"#{self.serial_number}: Stop event detected during sleep. Exiting preparing_account.")
                            return
                        stop_event.wait(1)

                    break  # Успешное завершение действия

                except NoSuchElementException:
                    logger.debug(
                        f"#{self.serial_number}: Element not found for action: {success_msg}. Skipping.")
                    break  # Пропускаем текущую кнопку
                except WebDriverException as e:
                    retries += 1
                    logger.debug(
                        f"#{self.serial_number}: Failed action (attempt {retries}): {str(e).splitlines()[0]}")
                    for _ in range(5):  # Пауза с проверкой stop_event
                        if stop_event.is_set():
                            logger.info(
                                f"#{self.serial_number}: Stop event detected during retry wait. Exiting preparing_account.")
                            return
                        stop_event.wait(1)

                    if retries >= self.MAX_RETRIES:
                        logger.debug(
                            f"#{self.serial_number}: Exceeded maximum retries for action: {success_msg}")
                        break
                except Exception as e:
                    logger.debug(
                        f"#{self.serial_number}: Unexpected error during action '{success_msg}': {str(e)}")
                    break
            logger.debug(
                f"#{self.serial_number}: Finished processing action: {success_msg}")

    def click_home_tab(self):
        """
        Функция для клика на вкладку "Home" с обработкой исключений и остановкой по событию.

        :param driver: WebDriver Selenium.
        :param stop_event: Событие threading.Event для остановки выполнения.
        :param serial_number: Уникальный идентификатор для логирования.
        :param max_retries: Максимальное количество попыток клика.
        :return: None
        """
        retries = 0

        while retries < self.MAX_RETRIES:
            if stop_event.is_set():
                logger.debug(
                    f"#{self.serial_number}: Stop event detected. Exiting click_home_tab.")
                return False

            try:
                button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, 'a[href="/"]'))
                )
                button.click()
                logger.info(
                    f"#{self.serial_number}: Successfully clicked on the Home tab.")
                # Ждем полной загрузки страницы
                self.wait_for_page_load()
                return True  # Успешно выполнено, выходим из функции

            except TimeoutException:
                logger.debug(
                    f"#{self.serial_number}: Home tab not found within timeout.")
                break

            except WebDriverException as e:
                logger.debug(
                    f"#{self.serial_number}: Failed to click Home tab (attempt {retries + 1}): {str(e).splitlines()[0]}")
                retries += 1
                for _ in range(5):  # Проверяем stop_event во время паузы
                    if stop_event.is_set():
                        logger.info(
                            f"#{self.serial_number}: Stop event detected during retry. Exiting click_home_tab.")
                        return False
                    stop_event.wait(1)

        logger.error(
            f"#{self.serial_number}: Exceeded maximum retries to click Home tab.")
        return False

    def click_earn_tab(self):
        """
        Функция для клика на вкладку "Home" с обработкой исключений и остановкой по событию.

        :param driver: WebDriver Selenium.
        :param stop_event: Событие threading.Event для остановки выполнения.
        :param serial_number: Уникальный идентификатор для логирования.
        :param max_retries: Максимальное количество попыток клика.
        :return: None
        """
        retries = 0

        while retries < self.MAX_RETRIES:
            if stop_event.is_set():
                logger.debug(
                    f"#{self.serial_number}: Stop event detected. Exiting click_earn_tab.")
                return False

            try:
                button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, 'a[href="/earn"]'))
                )
                button.click()
                logger.info(
                    f"#{self.serial_number}: Successfully clicked on the earn tab.")
                # Ждем полной загрузки страницы
                self.wait_for_page_load()
                return True  # Успешно выполнено, выходим из функции

            except TimeoutException:
                logger.debug(
                    f"#{self.serial_number}: Earn tab not found within timeout.")
                break

            except WebDriverException as e:
                logger.debug(
                    f"#{self.serial_number}: Failed to click earn tab (attempt {retries + 1}): {str(e).splitlines()[0]}")
                retries += 1
                for _ in range(5):  # Проверяем stop_event во время паузы
                    if stop_event.is_set():
                        logger.info(
                            f"#{self.serial_number}: Stop event detected during retry. Exiting click_earn_tab.")
                        return False
                    stop_event.wait(1)

        logger.error(
            f"#{self.serial_number}: Exceeded maximum retries to click earn tab.")
        return False

    def switch_to_iframe(self):
        """
        Switches to the first iframe on the page, if available.
        """
        try:
            # Возвращаемся к основному контенту страницы
            logger.debug(
                f"#{self.serial_number}: Switching to the default content.")
            self.driver.switch_to.default_content()

            # Ищем все iframes на странице
            logger.debug(
                f"#{self.serial_number}: Looking for iframes on the page.")
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            logger.debug(
                f"#{self.serial_number}: Found {len(iframes)} iframes on the page.")

            if iframes:
                # Переключаемся на первый iframe
                self.driver.switch_to.frame(iframes[0])
                logger.debug(
                    f"#{self.serial_number}: Successfully switched to the first iframe.")
                return True
            else:
                logger.warning(
                    f"#{self.serial_number}: No iframes found to switch.")
                return False
        except NoSuchElementException:
            logger.warning(
                f"#{self.serial_number}: No iframe element found on the page.")
            return False
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error while switching to iframe: {str(e)}")
            return False

    def get_username(self):
        """
        Получает имя пользователя из элемента на странице с поддержкой остановки через stop_event.
        """
        if stop_event.is_set():  # Проверка на остановку перед выполнением
            logger.info(
                f"#{self.serial_number}: Stop event detected. Exiting get_username.")
            return "Unknown"

        try:
            logger.debug(
                f"#{self.serial_number}: Attempting to retrieve username.")

            # Ожидание появления элемента с именем пользователя
            username_block = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//header/button/p"))
            )

            if stop_event.is_set():  # Проверка после ожидания элемента
                logger.info(
                    f"#{self.serial_number}: Stop event detected after locating username element.")
                return "Unknown"

            logger.debug(f"#{self.serial_number}: Username element located.")

            # Извлечение имени пользователя
            username = username_block.get_attribute("textContent").strip()
            logger.debug(
                f"#{self.serial_number}: Username retrieved: {username}")
            return username

        except TimeoutException:
            logger.debug(
                f"#{self.serial_number}: Timeout while waiting for username element.")
            return "Unknown"
        except (WebDriverException, StaleElementReferenceException) as e:
            error_message = str(e).splitlines()[0]
            logger.warning(
                f"#{self.serial_number}: Exception occurred while retrieving username: {error_message}")
            return "Unknown"
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error while retrieving username: {str(e)}")
            return "Unknown"

    def get_balance(self):
        """
        Извлекает текущий баланс пользователя с поддержкой остановки через stop_event.
        """
        retries = 0
        while retries < self.MAX_RETRIES:
            if stop_event.is_set():  # Проверка на остановку перед началом цикла
                logger.info(
                    f"#{self.serial_number}: Stop event detected. Exiting get_balance.")
                return "0"

            try:
                logger.debug(
                    f"#{self.serial_number}: Attempting to retrieve balance (attempt {retries + 1}).")

                # Ожидание контейнера с балансом
                parent_block = WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@class, 'flex items-center font-tt-hoves')]"))
                )
                logger.debug(
                    f"#{self.serial_number}: Parent block for balance found.")

                if stop_event.is_set():
                    logger.info(
                        f"#{self.serial_number}: Stop event detected after finding parent block.")
                    return "0"

                # Поиск всех чисел в балансе
                visible_balance_elements = parent_block.find_elements(
                    By.XPATH, ".//span[contains(@class, 'index-module_num__j6XH3') and not(@aria-hidden='true')]"
                )
                raw_balance_elements = [el.get_attribute(
                    'textContent').strip() for el in visible_balance_elements]
                logger.debug(
                    f"#{self.serial_number}: Extracted raw balance elements: {raw_balance_elements}")

                if stop_event.is_set():
                    logger.info(
                        f"#{self.serial_number}: Stop event detected after extracting balance elements.")
                    return "0"

                # Сбор текста чисел и объединение в строку
                balance_text = ''.join(raw_balance_elements).replace(',', '')
                logger.debug(
                    f"#{self.serial_number}: Cleaned balance text: {balance_text}")

                # Преобразование в float
                if balance_text.replace('.', '', 1).isdigit():
                    self.balance = float(balance_text)
                else:
                    logger.warning(
                        f"#{self.serial_number}: Invalid balance text: '{balance_text}'. Setting balance to 0.")
                    self.balance = 0.0

                if stop_event.is_set():
                    logger.info(
                        f"#{self.serial_number}: Stop event detected before formatting balance.")
                    return "0"

                # Преобразование float к строке, удаление .0
                balance_text = str(
                    int(self.balance)) if self.balance.is_integer() else str(self.balance)
                logger.debug(
                    f"#{self.serial_number}: Final balance text: {balance_text}")

                # Логирование текущего баланса
                logger.info(
                    f"#{self.serial_number}: Current balance: {balance_text}")

                # Обновление имени пользователя
                self.get_username()

                return balance_text

            except (NoSuchElementException, TimeoutException) as e:
                logger.warning(
                    f"#{self.serial_number}: Failed to retrieve balance or username (attempt {retries + 1}): {str(e).splitlines()[0]}"
                )
                retries += 1
                stop_event.wait(5)

                if stop_event.is_set():  # Проверка во время ожидания перед новой попыткой
                    logger.info(
                        f"#{self.serial_number}: Stop event detected during retry sleep.")
                    return "0"

            except (WebDriverException, StaleElementReferenceException) as e:
                error_message = str(e).splitlines()[0]
                logger.warning(
                    f"#{self.serial_number}: Exception occurred while retrieving balance: {error_message}")
                retries += 1
                stop_event.wait(5)

                if stop_event.is_set():
                    logger.info(
                        f"#{self.serial_number}: Stop event detected during retry sleep.")
                    return "0"

            except Exception as e:
                logger.error(
                    f"#{self.serial_number}: Unexpected error while retrieving balance: {str(e)}")
                break

        logger.error(
            f"#{self.serial_number}: Exceeded maximum retries for balance retrieval.")
        return "0"

    def get_time(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            if stop_event.is_set():  # Проверка на остановку перед началом цикла
                logger.info(
                    f"#{self.serial_number}: Stop event detected. Exiting get_time.")
                return "N/A"

            try:
                # Ищем элемент, содержащий текст "Осталось" или "Get after"
                all_elements = self.driver.find_elements(By.TAG_NAME, "span")

                if stop_event.is_set():
                    logger.info(
                        f"#{self.serial_number}: Stop event detected while searching for elements.")
                    return "N/A"

                parent_element = None
                for element in all_elements:
                    if stop_event.is_set():
                        logger.info(
                            f"#{self.serial_number}: Stop event detected while iterating elements.")
                        return "N/A"

                    try:
                        text = element.text.strip().lower()
                        if "осталось" in text or "get after" in text:
                            parent_element = element
                            break
                    except StaleElementReferenceException:
                        logger.debug(
                            f"#{self.serial_number}: Stale element encountered while searching for parent element. Retrying...")
                        continue

                if not parent_element:
                    if retries == self.MAX_RETRIES - 1:  # Логируем только на последней попытке
                        logger.debug(
                            f"#{self.serial_number}: No element with text 'Осталось' or 'Get after' found after {self.MAX_RETRIES} attempts.")
                        logger.warning(
                            f"#{self.serial_number}: No 'Time' element found after {self.MAX_RETRIES} attempts.")
                    retries += 1
                    stop_event.wait(5)
                    continue

                # Логируем найденный контейнер
                logger.debug(
                    f"Found parent element: {parent_element.get_attribute('outerHTML')}")

                # Извлекаем все вложенные элементы и ищем цифры
                child_elements = parent_element.find_elements(
                    By.XPATH, ".//span")

                visible_digits = []
                for child in child_elements:
                    if stop_event.is_set():
                        logger.info(
                            f"#{self.serial_number}: Stop event detected while processing child elements.")
                        return "N/A"

                    try:
                        text = child.get_attribute("textContent").strip()
                        aria_hidden = child.get_attribute("aria-hidden")
                        if (not aria_hidden or aria_hidden.lower() == "false") and text.isdigit() and len(text) == 1:
                            visible_digits.append(text)
                    except StaleElementReferenceException:
                        logger.debug(
                            f"#{self.serial_number}: Stale element encountered while processing child elements. Retrying...")
                        continue

                logger.debug(f"Visible digits collected: {visible_digits}")

                # Проверяем, достаточно ли цифр для формирования времени
                if len(visible_digits) >= 6:
                    time_text = ''.join(visible_digits[:6])
                    formatted_time = f"{time_text[:2]}:{time_text[2:4]}:{time_text[4:6]}"
                    logger.info(
                        f"#{self.serial_number}: Start farm will be available after: {formatted_time}")
                    return formatted_time
                else:
                    raise NoSuchElementException(
                        "Not enough visible digits to form time.")

            except (NoSuchElementException, TimeoutException) as e:
                retries += 1
                logger.warning(
                    f"#{self.serial_number}: Failed to get time (attempt {retries}): {str(e)}")
                logger.debug(traceback.format_exc())

                if stop_event.is_set():
                    logger.info(
                        f"#{self.serial_number}: Stop event detected during retry sleep.")
                    return "N/A"

                self.farming()  # Вызываем farming при ошибке
                stop_event.wait(5)
            except StaleElementReferenceException:
                retries += 1
                logger.warning(
                    f"#{self.serial_number}: Encountered stale element reference (attempt {retries}). Retrying...")
                stop_event.wait(2)  # Пауза перед повторным поиском элементов
            except Exception as e:
                logger.error(
                    f"#{self.serial_number}: Unexpected error during time extraction: {str(e)}")
                logger.debug(traceback.format_exc())

                if stop_event.is_set():
                    logger.info(
                        f"#{self.serial_number}: Stop event detected after unexpected error.")
                    return "N/A"

                self.farming()  # Вызываем farming при ошибке
                return "N/A"

        # Если превышено количество попыток, просто возвращаем "N/A"
        logger.error(
            f"#{self.serial_number}: Could not retrieve time after {self.MAX_RETRIES} attempts.")
        return "N/A"

    def farming(self):
        # Ждем полной загрузки страницы
        self.wait_for_page_load()
        """
        Выполняет действия 'Start farming' и 'Collect'
        """
        actions = [
            ("/html[1]/body[1]/div[1]/div[1]/main[1]/div[5]/button[1] | /html[1]/body[1]/div[1]/div[1]/main[1]/div[4]/button[1]/div[1] | /html/body/div[1]/div[1]/main/div[4]/button | /html/body/div[1]/div/main/div[5]/button | //*[@id='root']/div/main/div[6]/button/div[1]",
             "'Start farming' button clicked"),
            ("/html[1]/body[1]/div[1]/div[1]/main[1]/div[5]/button[1] | /html[1]/body[1]/div[1]/div[1]/main[1]/div[4]/button[1]/div[1] | /html/body/div[1]/div[1]/main/div[4]/button | /html/body/div[1]/div/main/div[5]/button | //*[@id='root']/div/main/div[6]/button/div[1]",
             "'Collect' button clicked")
        ]
        for xpath, success_msg in actions:
            retries = 0
            while retries < self.MAX_RETRIES:
                if stop_event.is_set():  # Проверка на прерывание перед выполнением действий
                    logger.info(
                        f"#{self.serial_number}: Stopping farming due to stop event.")
                    return

                try:
                    logger.debug(
                        f"#{self.serial_number}: Attempting action: {success_msg}")

                    button = self.wait_for_element(By.XPATH, xpath, timeout=10)
                    if stop_event.is_set():  # Повторная проверка после потенциально долгого ожидания
                        logger.info(
                            f"#{self.serial_number}: Stop event detected after wait. Exiting...")
                        return

                    if button:
                        self.safe_click(button)
                        # button.click()
                        logger.info(f"#{self.serial_number}: {success_msg}")

                        sleep_time = random.randint(3, 4)
                        logger.debug(
                            f"#{self.serial_number}: Sleeping for {sleep_time} seconds before next action.")
                        # Разбиваем sleep на интервалы для проверки stop_event
                        for _ in range(sleep_time):
                            if stop_event.is_set():
                                logger.info(
                                    f"#{self.serial_number}: Stop event detected during sleep. Exiting...")
                                return
                            stop_event.wait(1)

                        break
                    else:
                        logger.debug(
                            f"#{self.serial_number}: Element not found for action: {success_msg}. Skipping...")
                        break
                except WebDriverException as e:
                    retries += 1
                    logger.warning(
                        f"#{self.serial_number}: Failed action (attempt {retries}): {str(e).splitlines()[0]}")
                    logger.debug(traceback.format_exc())

                    for _ in range(5):  # Проверка во время ожидания перед следующей попыткой
                        if stop_event.is_set():
                            logger.info(
                                f"#{self.serial_number}: Stop event detected during retry sleep. Exiting...")
                            return
                        stop_event.wait(1)

    def find_button_by_text(self, text, threshold=70):
        """
        Finds a button by its text with partial matching.
        """
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            logger.debug(
                f"#{self.serial_number}: Found {len(buttons)} buttons on the page.")
            best_match = None
            best_score = 0

            for button in buttons:
                button_text = button.text.strip()
                score = fuzz.partial_ratio(button_text.lower(), text.lower())
                if score > best_score:
                    best_score = score
                    best_match = button

                # Exact match (shortcut for performance)
                if score == 100:
                    logger.debug(
                        f"#{self.serial_number}: Exact match found for button text '{text}'.")
                    return button

            if best_score >= threshold:
                logger.debug(
                    f"#{self.serial_number}: Best match for text '{text}' is '{best_match.text}' with score {best_score}.")
                return best_match
            else:
                logger.debug(
                    f"#{self.serial_number}: No matching button found for text '{text}'. Highest score: {best_score}%.")
        except Exception as e:
            logger.debug(
                f"#{self.serial_number}: Error while searching for a button with text '{text}': {e}")
        return None

    def click_start(self, question_answer_map):
        """
        Finds and clicks the "Start" button.
        """
        stop_event.wait(2)
        try:
            start_button = self.find_button_by_text("Начать", threshold=70)
            if start_button:
                logger.debug(
                    f"#{self.serial_number}: The 'Start' button is found. Scrolling and clicking...")
                self.safe_click(start_button)
                self.click_second_button(question_answer_map)
            else:
                logger.info(
                    f"#{self.serial_number}: New courses is not found. All courses might be completed.")
        except Exception as e:
            logger.debug(
                f"#{self.serial_number}: Error during 'Start' button click: {e}")

    def click_second_button(self, question_answer_map):
        """
        Finds and clicks the second button in the popup.
        """
        stop_event.wait(3)
        try:
            self.reward = self.get_reward()
            task_name = self.get_task_name()
        except Exception as e:
            logger.debug(f"#{self.serial_number}: Error: {e}")
        if task_name:
            logger.info(
                f"#{self.serial_number}: Completing the courses: '{task_name}'")
        try:
            popup_button = self.driver.find_element(
                By.XPATH, "//div[contains(@class, 'z-40') and text()='Начать']")
            logger.debug(
                f"#{self.serial_number}: Second button found. Clicking...")
            self.safe_click(popup_button)
            stop_event.wait(5)
            self.execute_course(question_answer_map)
        except Exception as e:
            logger.debug(
                f"#{self.serial_number}: Second button not found: {e}")

    def find_best_match(self, question, question_answer_map, threshold=70):
        """
        Finds the best matching question using a similarity score.
        """
        best_match = None
        best_score = 0

        for key in question_answer_map.keys():
            score = fuzz.partial_ratio(question.lower(), key.lower())
            if score > best_score:
                best_score = score
                best_match = key

        if best_score >= threshold:
            logger.debug(
                f"#{self.serial_number}: Matching question found: '{best_match}' with similarity {best_score}%.")
            return question_answer_map[best_match]
        else:
            logger.debug(
                f"#{self.serial_number}: No matching question found. Highest similarity: {best_score}%.")
            return None

    def find_question_and_answer(self, question_answer_map, threshold=70):
        """
        Finds the question on the page and determines the corresponding answer.
        """
        try:
            # Новый XPath для поиска текста вопроса
            question_element = self.driver.find_element(
                By.XPATH, "//span[contains(@class, 'font-tt-hoves-expanded')]"
            )
            question_text = question_element.text.strip()
            logger.debug(
                f"#{self.serial_number}: Question text: '{question_text}'")

            # Ищем лучший ответ
            answer = self.find_best_match(
                question_text, question_answer_map, threshold)
            if answer:
                logger.debug(
                    f"#{self.serial_number}: Answer for the question: '{answer}'")
                answer_button = self.find_button_by_text(answer)
                if answer_button:
                    logger.debug(
                        f"#{self.serial_number}: Answer button found. Clicking...")
                    self.safe_click(answer_button)
                    return True
                else:
                    logger.debug(
                        f"#{self.serial_number}: Answer button not found.")
            else:
                logger.debug(
                    f"#{self.serial_number}: No matching answer found for the question.")

        except NoSuchElementException:
            logger.debug(f"#{self.serial_number}: Question element not found.")
        except Exception as e:
            logger.debug(
                f"#{self.serial_number}: Error processing the question: {e}")

        return False

    def execute_course(self, question_answer_map, max_time_per_course=600):
        """
        Выполняет курс с ограничением времени.
        :param question_answer_map: Словарь с вопросами и ответами.
        :param max_time_per_course: Максимальное время выполнения курса (в секундах).
        """
        start_time = time.time()  # Время начала курса

        try:
            while True:
                # Проверяем, не истекло ли время
                elapsed_time = time.time() - start_time
                if elapsed_time > max_time_per_course:
                    logger.warning(
                        f"#{self.serial_number}: Time limit of {max_time_per_course} seconds exceeded. Exiting course execution."
                    )
                    return  # Прекращаем выполнение курса
                stop_event.wait(1)
                next_button = self.find_button_by_text("Далее", threshold=70) or \
                    self.find_button_by_text("Продолжить", threshold=70)
                stop_event.wait(5)
                if next_button and next_button.get_attribute("disabled"):
                    logger.debug(
                        f"#{self.serial_number}: The 'Next' or 'Continue' button is disabled. Handling the question..."
                    )
                    if self.find_question_and_answer(question_answer_map):
                        stop_event.wait(2)
                        self.safe_click(next_button)
                    else:
                        logger.debug(
                            f"#{self.serial_number}: Answer not found. Refreshing the current page..."
                        )
                        script = """
                            window.location.assign(window.location.origin + window.location.pathname);
                        """
                        self.driver.execute_script(script)
                        stop_event.wait(5)
                        self.switch_to_iframe()
                        return

                if next_button:
                    logger.debug(
                        f"#{self.serial_number}: The 'Next' or 'Continue' button is active. Clicking..."
                    )
                    self.safe_click(next_button)
                    continue  # Продолжаем цикл для следующего шага курса

                else:
                    logger.debug(
                        f"#{self.serial_number}: The 'Next' or 'Continue' button is not found. Searching for the 'Claim' button..."
                    )
                    self.click_claim_button(question_answer_map)
                    break  # Завершаем выполнение, если кнопка не найдена

        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Error during quiz execution: {e}")

    def click_claim_button(self, question_answer_map):
        """
        Waits for and clicks the "Claim" button.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Waiting for the 'Claim' button to appear...")

            # Ожидаем появления кнопки с классом и текстом "Забрать"
            claim_button = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//button[contains(@class, 'claim-btn')]//div[text()='Забрать' or text()='Вернуться к модулю']"
                ))
            )


            # Получаем родительский элемент <button> для клика
            parent_button = claim_button.find_element(
                By.XPATH, "./ancestor::button")

            logger.debug(
                f"#{self.serial_number}: The 'Claim' button is found. Clicking...")
            self.safe_click(parent_button)
            if self.reward:
                logger.info(
                    f"#{self.serial_number}: Task completed. Reward received: {self.reward}")
            stop_event.wait(5)

            script = """
                    window.location.assign(window.location.origin + window.location.pathname);
                """
            self.driver.execute_script(script)
            stop_event.wait(5)
            self.click_start(question_answer_map)

        except TimeoutException:
            logger.debug(
                f"#{self.serial_number}: The 'Claim' button did not appear. Searching for 'Start'...")
            self.click_start(question_answer_map)
        except Exception as e:
            logger.debug(
                f"#{self.serial_number}: Error while waiting for the 'Claim' button: {e}")

    def get_task_name(self):
        """
        Retrieves the task name before clicking the second button.
        """
        try:
            task_name_element = self.driver.find_element(
                By.XPATH, "//div[@data-state='open']//span[contains(@class, 'text-base font-bold')]"
            )
            task_name = task_name_element.text.strip()
            logger.debug(
                f"#{self.serial_number}: Task name retrieved: '{task_name}'")
            return task_name
        except NoSuchElementException:
            logger.debug("Task name element not found.")
            return None
        except Exception as e:
            logger.debug(
                f"#{self.serial_number}: Error while retrieving task name: {e}")
            return None

    def get_reward(self):
        """
        Ищет и возвращает значение награды (например, '100 NUTS') на текущей странице.
        """
        try:
            # Ожидаем появления всех элементов с классом font-bold
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "span.font-bold"))
            )

            # Ищем элементы с текстом 'NUTS'
            elements = self.driver.find_elements(
                By.CSS_SELECTOR, "span.font-bold")
            for element in elements:
                if "NUTS" in element.text:
                    reward = element.text.strip()
                    logger.debug(
                        f"#{self.serial_number}: Reward found: {reward}")
                    return reward

            logger.debug(f"#{self.serial_number}: Reward not found.")
            return None
        except Exception as e:
            logger.debug(
                f"#{self.serial_number}: Error while trying to find reward: {e}")
            return None

    def run_courses_automation(self):
        """
        Запускает процесс автоматизации квиза.
        """
        logger.info(
            f"#{self.serial_number}: Сhecking the available courses...")
        question_answer_map = {
            "What is the key technology behind cryptocurrency?": "Blockchain",
            "Как называется ключевая технология на базе которой работает криптовалюта?": "Blockchain",
            "How many types of cryptocurrencies exist on the market today?": "13,000",
            "Сколько видов криптовалют сегодня существует на рынке?": "13,000",
            "Which currency has the largest market capitalization?": "ETH",
            "У какой валюты из перечисленных самая большая капитализация?": "ETH",
            "What is fiat?": "Traditional currency",
            "Что такое фиат?": "Традиционная валюта",
            "What can you do on a cryptocurrency exchange?": "Trade",
            "Что можно делать на криптобирже?": "Торговать",
            "What is P2P?": "Peer-to-peer cryptocurrency exchange",
            "Что такое P2P?": "Обмен криптовалютой без посредников",
            "How else can you exchange cryptocurrency?": "Through an exchanger",
            "Как еще можно обменивать криптовалюту?": "Через обменник",
            "When does the exchange confirm the transaction?": "When both parties confirm the exchange",
            "Когда биржа подтверждает сделку?": "Когда обе стороны подтвердили, что обмен состоялся",
            "What does the SQUID token example teach?": "It is important to analyze the project before investing.",
            "Чему учит пример с токеном SQUID?": "Что важно анализировать проект перед инвестированием.",
            "Select the type of cryptocurrency tied to the dollar:": "Stablecoin",
            "Выбери тип криптовалюты, которая привязана к доллару": "Стейблкоин",
            "BTC": "BTC",
            "Which cryptocurrency listed is a blockchain coin?": "BTC",
            "Какая криптовалюта из перечисленных является монетой блокчейна?": "BTC",
            "Which principle is important for successful investments?": "Diversification — distributing investments among different cryptocurrencies.",
            "Какой принцип является важным для успешных инвестиций?": "Диверсификация — распределение вложений между разными криптовалютами.",
            "Which portfolio is suitable for long-term investments (2+ years) with capital of $1,000?": "Safe portfolio (20% USDT, 50% BTC, 30% ETH).",
            "Какой портфель подходит для долгосрочных инвестиций (от двух лет) с капиталом от $1,000?": "Безопасный портфель (20% USDT, 50% BTC, 30% ETH).",
            "What percentage of the stablecoin market does USDT occupy?": "75%",
            "Сколько процентов рынка стейблкоинов занимает USDT?": "75%",
            "Что Тим сделал не так?": "Купил BTC на все свои сбережения под влиянием новостей.",
            "В чем преимущество стратегии Виктора?": "Виктор уменьшил риск и заработал, инвестируя постепенно.",
            "Что такое DCA?": "Стратегия регулярных покупок актива на одинаковую сумму.",
            "Почему стратегия DCA работает?": "Позволяет избежать импульсивных решений и приобретать активы по выгодным ценам.",
            "Что такое стратегия «лесенка»?": "Продажа криптовалюты частями на разных уровнях цены.",
            "Какую ошибку допустил Тим?": "Пытался угадать пик цены и в итоге упустил момент.",
            "Выберите главный плюс стратегии «лесенка»": "Помогает зафиксировать прибыль даже при падении цены в будущем.",
            "Что стоит сделать если цена актива выросла в 2 раза?": "Продать половину актива, чтобы забрать вложения.",
            "Что такое стейкинг?": "Процесс, при котором вы «замораживаете» свою криптовалюту, чтобы получать проценты.",
            "Откуда берется прибыль за стейкинг?": "За поддержку сети, кредитование или промо программы биржи.",
            "Как связана поддержка блокчейна и награды за стейкинг?": "Замораживая монеты, вы помогаете сети обрабатывать транзакции и обеспечивать безопасность, за что получаете награды.",
            "Как работают промо-программы с запуском новых проектов?": "Биржа начисляет токены нового проекта за стейкинг вашей криптовалюты."
            
        }
        self.click_start(question_answer_map)
