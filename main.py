import logging
import random
import time
from telegram_bot_automation import TelegramBotAutomation
from utils import read_accounts_from_file, write_accounts_to_file, reset_balances, update_balance_table
from colorama import Fore, Style
from prettytable import PrettyTable, SINGLE_BORDER
from termcolor import colored
from datetime import datetime, timedelta
from queue import Queue
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

# Глобальный список для хранения данных об аккаунтах
account_balances = []
balance_queue = Queue()

def process_account_once(account, balance_queue):
    """
    Обрабатывает заданный аккаунт в рамках запланированного таймера
    и выводит обновлённую таблицу после выполнения.
    """
    logger.info(f"Scheduled processing for account {account}. Starting...")

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

        # Преобразование баланса в число
        try:
            balance = float(balance) if isinstance(balance, str) and balance.replace('.', '', 1).isdigit() else float(balance)
        except (ValueError, TypeError):
            logger.warning(f"Account {account}: Invalid balance format: {balance}. Setting to 0.0.")
            balance = 0.0

        logger.info(f"Account {account}: Current balance after farming: {balance}")

        # Получаем время до следующего действия
        scheduled_time_str = bot.get_time()
        if ":" in scheduled_time_str:
            hours, minutes, seconds = map(int, scheduled_time_str.split(":"))
            time_delta = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            scheduled_time = datetime.now() + time_delta
        else:
            scheduled_time = datetime.now() + timedelta(hours=8)  # Если время недоступно, добавить 8 часов.

        next_schedule = scheduled_time.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Account {account}: Next scheduled time: {next_schedule}")

        # Обновляем глобальную таблицу с балансами
        update_balance_table(account, username, balance, next_schedule)

        # Добавляем результат обработки в потокобезопасную очередь
        balance_queue.put((account, username, balance, next_schedule, "Success"))

    except Exception as e:
        logger.warning(f"Account {account}: Error occurred during scheduled processing: {e}")
        balance_queue.put((account, "N/A", 0.0, "N/A", "ERROR"))

    finally:
        if bot and hasattr(bot.browser_manager, "close_browser"):
            try:
                bot.browser_manager.close_browser()
                logger.info(f"Account {account}: Browser closed after processing.")
            except Exception as e:
                logger.warning(f"Account {account}: Failed to close browser: {e}")

    # Вывод обновлённой таблицы после обработки аккаунта
    display_balance_table(balance_queue)


def display_balance_table(balance_queue):
    """
    Отображает таблицу балансов, извлекая данные из очереди.
    """
    logger.info("\nUpdated Balance Table:")
    current_table = PrettyTable()
    current_table.field_names = ["ID", "Username", "Balance", "Next Scheduled Time", "Status"]
    total_balance = 0.0

    # Извлечение данных из очереди для обновления таблицы
    all_balances = list(balance_queue.queue)  # Снимок текущего состояния очереди
    for serial_number, username, balance, next_schedule, status in all_balances:
        row = [serial_number, username if username else "N/A", balance, next_schedule if next_schedule else "N/A", status]
        if status == "ERROR":
            current_table.add_row([f"{Fore.RED}{cell}{Style.RESET_ALL}" for cell in row])
        else:
            current_table.add_row([f"{Fore.CYAN}{cell}{Style.RESET_ALL}" for cell in row])
            if isinstance(balance, (int, float)):
                total_balance += balance

    logger.info("\n" + str(current_table))
    logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:,.2f}{Style.RESET_ALL}")




def process_accounts():
    """
    Обрабатывает список аккаунтов с поддержкой ретраев и таймеров, показывая общую таблицу баланса после обработки каждого аккаунта.
    При прерывании (Ctrl+C) все таймеры и браузеры закрываются.
    """
    try:
        reset_balances()
        accounts = read_accounts_from_file()
        random.shuffle(accounts)
        write_accounts_to_file(accounts)

        # Очередь для хранения результатов обработки аккаунтов
        balance_queue = Queue()
        active_timers = []  # Список активных таймеров
        active_bots = []    # Список активных ботов для закрытия браузеров

        logger.info("Starting main cycle for account processing.")

        # Основной цикл обработки аккаунтов
        for account in accounts:
            retry_count = 0
            success = False
            adjusted_time_str = "N/A"

            while retry_count < 3 and not success:
                bot = None  # Объявление bot вне блока try
                try:
                    bot = TelegramBotAutomation(account, settings)
                    active_bots.append(bot)  # Добавляем бот в список для отслеживания

                    # Навигация и выполнение задач
                    if not bot.navigate_to_bot():
                        raise Exception("Failed to navigate to bot")
                    if not bot.send_message(settings['TELEGRAM_GROUP_URL']):
                        raise Exception("Failed to send message")
                    if not bot.click_link():
                       raise Exception("Failed to click link")
                    bot.preparing_account()

                    # Получение баланса
                    balance = bot.get_balance()
                    username = bot.get_username() if hasattr(bot, 'get_username') else "N/A"
                    try:
                        balance = float(balance) if isinstance(balance, str) and balance.replace('.', '', 1).isdigit() else float(balance)
                    except (ValueError, TypeError):
                        logger.warning(f"Account {account}: Invalid balance format: {balance}. Setting to 0.0.")
                        balance = 0.0

                    logger.info(f"Account {account}: Final balance after processing: {balance}.")

                    # Фермерство (после получения баланса)
                    bot.farming()

                    # Расчет времени до следующего действия
                    scheduled_time = bot.get_time()
                    if ":" in scheduled_time:
                        hours, minutes, seconds = map(int, scheduled_time.split(':'))
                        time_delta = timedelta(hours=hours, minutes=minutes, seconds=seconds)
                        trigger_time = datetime.now() + time_delta + timedelta(minutes=random.randint(5, 30))
                        adjusted_time_str = trigger_time.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        adjusted_time_str = "N/A"

                    logger.info(f"Account {account}: Adjusted scheduled time for next claim: {adjusted_time_str}")

                    success = True

                    # Обновление таблицы балансов
                    balance_queue.put((account, username, balance, adjusted_time_str, "Success"))
                except Exception as e:
                    logger.warning(f"Account {account}: Error occurred on attempt {retry_count + 1}: {e}")
                    retry_count += 1
                finally:
                    if bot:
                        bot.browser_manager.close_browser()
                        active_bots.remove(bot)  # Удаляем бот из списка после закрытия браузера
                    sleep_time = random.randint(5, 15)
                    logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                    time.sleep(sleep_time)

            if not success:
                logger.warning(f"Account {account}: Failed after 3 attempts.")
                balance_queue.put((account, "N/A", 0.0, "N/A", "ERROR"))

            # Генерация итоговой таблицы баланса после обработки текущего аккаунта
            current_balances, balance_table, total_balance = generate_final_balance_table(balance_queue, show_remaining=True)
            #print(balance_table)

            # Установка таймера для следующего действия
            if adjusted_time_str != "N/A":
                trigger_time = datetime.strptime(adjusted_time_str, "%Y-%m-%d %H:%M:%S")
                timer = threading.Timer(
                    (trigger_time - datetime.now()).total_seconds(),
                    process_account_once,
                    args=(account, balance_queue)
                )
                active_timers.append(timer)
                timer.start()
                logger.info(f"Account {account}: Timer set for {adjusted_time_str}.")

        logger.info("All accounts processed.")

        # Ожидание завершения всех таймеров
        logger.info("Waiting for all timers to complete...")
        for timer in active_timers:
            timer.join()

    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Cancelling all timers and closing browsers...")
        # Закрытие всех активных браузеров
        for bot in active_bots:
            try:
                bot.browser_manager.close_browser()
            except Exception as e:
                logger.warning(f"Failed to close browser during interrupt: {e}")
        # Прерывание всех таймеров
        for timer in active_timers:
            if timer.is_alive():
                timer.cancel()
                #logger.info("Timer cancelled.")
        logger.info("All timers and browsers cancelled. Exiting gracefully.")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")





def generate_final_balance_table(balance_queue, show_remaining=False):
    """
    Извлекает данные из очереди и генерирует итоговую таблицу.
    Возвращает список всех балансов, саму таблицу и общий баланс.
    """
    logger.info("Generating balance table...")
    table = PrettyTable()
    table.field_names = ["ID", "Username", "Balance", "Scheduled Time", "Status"]
    total_balance = 0.0
    current_balances = []  # Список для хранения всех балансов

    # Снимок текущей очереди для сохранения данных
    all_balances = list(balance_queue.queue)

    for account, username, balance, scheduled_time, status in all_balances:
        row = [account, username, balance, scheduled_time, status]

        if status == "ERROR":
            row = [Fore.RED + str(cell) + Style.RESET_ALL for cell in row]
        else:
            row = [Fore.CYAN + str(cell) + Style.RESET_ALL for cell in row]
            if isinstance(balance, (int, float)):
                total_balance += balance

        current_balances.append((account, username, balance, scheduled_time, status))
        table.add_row(row)

    logger.info("\nCurrent Balance Table:\n" + str(table))
    logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:.2f}{Style.RESET_ALL}")

    if show_remaining:
        #logger.info(f"Remaining accounts to process: {balance_queue.qsize()}")        
        #logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:.2f}{Style.RESET_ALL}")
        pass

    return current_balances, table, total_balance




if __name__ == "__main__":
    try:
        process_accounts()
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Exiting...")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
