import logging
import random
import time
from telegram_bot_automation import TelegramBotAutomation
from utils import read_accounts_from_file, write_accounts_to_file, reset_balances, update_balance_table
from colorama import Fore, Style
from prettytable import PrettyTable, SINGLE_BORDER
from termcolor import colored
from datetime import datetime, timedelta
import threading

# Load settings from settings.txt
def load_settings():
    settings = {}
    try:
        with open('settings.txt', 'r') as f:
            for line in f:
                key, value = line.strip().split('=', 1)
                settings[key.strip()] = value.strip()
    except FileNotFoundError:
        logging.error(f"Settings file 'settings.txt' not found.")
    except Exception as e:
        logging.error(f"Error reading settings file: {e}")
    return settings

settings = load_settings()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
#logger.setLevel(logging.DEBUG)

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

# Словарь для хранения таймеров
scheduled_timers = {}


def process_account_once(account):
    """
    Обрабатывает заданный аккаунт в рамках запланированного таймера
    и выводит обновлённую таблицу после выполнения.
    """
    logger.info(f"Scheduled processing for account {account}. Starting...")

    global account_balances  # Используем глобальный список для обновления таблицы

    try:
        bot = TelegramBotAutomation(account, settings)

        if not bot.navigate_to_bot():
            raise Exception("Failed to navigate to bot")
        

        if not bot.send_message(settings['TELEGRAM_GROUP_URL']):
            raise Exception("Failed to send message")
        if not bot.click_link():
            raise Exception("Failed to click link")

        bot.preparing_account()
        
        # Выполняем фермерство
        bot.farming()
        username = bot.get_username() if hasattr(bot, 'get_username') else "N/A"
        # Получаем баланс
        balance = bot.get_balance()
        # Проверяем, если баланс строка, пытаемся преобразовать в число
        if isinstance(balance, str):
            if balance.replace('.', '', 1).isdigit():
               balance = float(balance) if '.' in balance else int(balance)
            else:
               logger.warning(f"Account {account}: Invalid balance format: {balance}. Setting to 0.0.")
               balance = 0.0

        # Если баланс не число после всех проверок, сбрасываем его в 0.0
        if not isinstance(balance, (int, float)):
           logger.warning(f"Account {account}: Balance is not a number. Setting to 0.0.")
           balance = 0.0

        logger.info(f"Account {account}: Current balance after farming: {balance}")

        # Получаем время до следующего действия
        scheduled_time = bot.get_time()
        logger.info(f"Account {account}: Next scheduled time: {scheduled_time}")

        # Обновляем глобальную таблицу с балансами
        update_balance_table(account, username, balance, scheduled_time)

        # Добавляем результат обработки в глобальный список
        account_balances.append((account, username, balance, scheduled_time, "Success"))

    except Exception as e:
        logger.warning(f"Account {account}: Error occurred during scheduled processing: {e}")
        account_balances.append((account, "N/A", 0.0, "N/A", "ERROR"))
    finally:
        if bot and hasattr(bot.browser_manager, "close_browser"):
            bot.browser_manager.close_browser()
        logger.info(f"Account {account}: Processing completed.")

    # Вывод обновлённой таблицы после обработки аккаунта
    logger.info("\nUpdated Balance Table:")
    current_table = PrettyTable()
    current_table.field_names = ["ID", "Username", "Balance", "Scheduled Time", "Status"]
    total_balance = 0.0

    for serial_number, username, balance, scheduled_time, status in account_balances:
        row = [serial_number, username if username else "N/A", balance, scheduled_time if scheduled_time else "N/A", status]
        if status == "ERROR":
            current_table.add_row([colored(cell, "red") for cell in row])
        else:
            current_table.add_row([colored(cell, "cyan") for cell in row])
            if isinstance(balance, (int, float)):
                total_balance += balance

    logger.info("\n" + str(current_table))
    logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:,.2f}{Style.RESET_ALL}")


def process_accounts():
    global scheduled_timers
    try:
        reset_balances()
        accounts = read_accounts_from_file()
        random.shuffle(accounts)
        write_accounts_to_file(accounts)

        account_balances = []
        accounts_with_zero_balance = []

        # Основной цикл обработки
        logger.info("Starting main cycle for account processing.")
        for account in accounts:
            retry_count = 0
            success = False
            bot = None
            balance = 0.0
            adjusted_time_str = "N/A"  # Инициализация переменной времени

            while retry_count < 3 and not success:
                try:
                    bot = TelegramBotAutomation(account, settings)
                    if not bot.navigate_to_bot():
                        raise Exception("Failed to navigate to bot")
                    
                    if not bot.send_message(settings['TELEGRAM_GROUP_URL']):
                        raise Exception("Failed to send message")
                    if not bot.click_link():
                        raise Exception("Failed to click link")
                    bot.preparing_account()

                    # Получение баланса
                    balance = bot.get_balance()
                    logger.debug(f"Account {account}: Retrieved balance: {balance} (type: {type(balance)})")
                    username = bot.get_username() if hasattr(bot, 'get_username') else "N/A"
                    # Проверяем, если баланс строка, пытаемся преобразовать в число
                    if isinstance(balance, str):
                        if balance.replace('.', '', 1).isdigit():
                            balance = float(balance) if '.' in balance else int(balance)
                        else:
                            logger.warning(f"Account {account}: Invalid balance format: {balance}. Setting to 0.0.")
                            balance = 0.0

                    # Если баланс не число после всех проверок, сбрасываем его в 0.0
                    if not isinstance(balance, (int, float)):
                        logger.warning(f"Account {account}: Balance is not a number. Setting to 0.0.")
                        balance = 0.0

                    # Логирование после всех проверок
                    logger.info(f"Account {account}: Final balance after processing: {balance}.")

                    # Фермерство (до получения времени)
                    bot.farming()

                    # Получение времени до следующего клейма
                    scheduled_time = bot.get_time()

                    # Парсинг времени HH:MM:SS
                    hours, minutes, seconds = map(int, scheduled_time.split(':'))
                    time_delta = timedelta(hours=hours, minutes=minutes, seconds=seconds)

                    # Рассчитываем точное время следующего запуска
                    trigger_time = datetime.now() + time_delta

                    # Добавляем случайное значение (от 5 до 30 минут)
                    random_minutes = random.randint(5, 30)
                    trigger_time += timedelta(minutes=random_minutes)

                    # Форматируем запланированное время в строку
                    adjusted_time_str = trigger_time.strftime("%Y-%m-%d %H:%M:%S")
                    logger.info(f"Account {account}: Adjusted scheduled time for next claim: {adjusted_time_str}")

                    success = True
                    update_balance_table(account, username, balance, adjusted_time_str)  # Используем точное время
                except Exception as e:
                    logger.warning(f"Account {account}: Error occurred on attempt {retry_count + 1}: {e}")
                    retry_count += 1
                finally:
                    if bot:
                        bot.browser_manager.close_browser()
                    sleep_time = random.randint(5, 15)
                    logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                    time.sleep(sleep_time)

                if retry_count >= 3:
                    logger.warning(f"Account {account}: Failed after 3 attempts.")

            # Обновляем список результатов
            account_balances.append((account, username if bot and username else "N/A", balance if success else 0.0, adjusted_time_str, "Success" if success else "ERROR"))

            # Вывод таблицы после обработки аккаунта
            logger.info("\nCurrent Balance Table:")
            current_table = PrettyTable()
            current_table.field_names = ["ID", "Username", "Balance", "Scheduled Time", "Status"]
            total_balance = 0.0

            for serial_number, username, bal, scheduled_time, status in account_balances:
                row = [serial_number, username if username else "N/A", bal, scheduled_time if scheduled_time else "N/A", status]
                if bal == 0.0:
                    current_table.add_row([colored(cell, "red") for cell in row])
                else:
                    current_table.add_row([colored(cell, "cyan") for cell in row])
                    if isinstance(bal, (int, float)):
                        total_balance += bal

            logger.info("\n" + str(current_table))
            logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:,.2f}{Style.RESET_ALL}")

            # Установка таймера после фермерства
            if adjusted_time_str != "N/A":
                trigger_time = datetime.strptime(adjusted_time_str, "%Y-%m-%d %H:%M:%S")
                scheduled_timers[account] = threading.Timer(
                    (trigger_time - datetime.now()).total_seconds(),
                    lambda acc=account: process_account_once(acc)
                )
                scheduled_timers[account].start()
                logger.info(f"Account {account}: Timer set for {adjusted_time_str}.")

        # Дополнительный цикл обработки (для аккаунтов с нулевым балансом)
        for account in accounts_with_zero_balance:
            retry_count = 0
            success = False
            bot = None
            balance = 0.0
            adjusted_time_str = "N/A"

            while retry_count < 3 and not success:
                try:
                    bot = TelegramBotAutomation(account, settings)
                    if not bot.navigate_to_bot():
                        raise Exception("Failed to navigate to bot")
                    
                    if not bot.send_message(settings['TELEGRAM_GROUP_URL']):
                        raise Exception("Failed to send message")
                    if not bot.click_link():
                        raise Exception("Failed to click link")
                    bot.preparing_account()
                    username = bot.get_username() if hasattr(bot, 'get_username') else "N/A"
                    # Получение баланса
                    balance = bot.get_balance()

                    # Фермерство (до получения времени)
                    bot.farming()

                    # Получение времени до следующего клейма
                    scheduled_time = bot.get_time()

                    success = True
                    update_balance_table(account, username, balance, scheduled_time)
                except Exception as e:
                    logger.warning(f"Account {account}: Error occurred on retry attempt {retry_count + 1}: {e}")
                    retry_count += 1
                finally:
                    if bot:
                        bot.browser_manager.close_browser()
                    sleep_time = random.randint(5, 15)
                    logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                    time.sleep(sleep_time)

                if retry_count >= 3:
                    logger.warning(f"Account {account}: Failed after 3 retry attempts.")

    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Cancelling all timers and closing browsers...")
        for account, timer in scheduled_timers.items():
            if timer.is_alive():
                timer.cancel()
                logger.info(f"Account {account}: Timer cancelled.")
        try:
            if bot and hasattr(bot.browser_manager, "api_stop_browser"):
                bot.browser_manager.api_stop_browser()
                logger.info(f"Browser for account {account} stopped successfully.")
            if bot and bot.browser_manager.driver:
                bot.browser_manager.driver.quit()  # Закрытие WebDriver
                logger.info(f"WebDriver for account {account} stopped successfully.")
        except Exception as e:
            logger.warning(f"Failed to stop browser or WebDriver for account {account}: {e}")
        
        logger.info("All browsers closed. Exiting...")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")

if __name__ == "__main__":
    try:
        process_accounts()
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Exiting...")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
