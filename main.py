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
balance_dict = {}
balance_lock = threading.Lock()  # Защита доступа к словарю
exit_flag = False  # Глобальный флаг для выхода из программы


def process_account_once(account, balance_dict, active_timers):
    global exit_flag  # Доступ к глобальному флагу завершения

    # Удаляем завершённые таймеры
    active_timers[:] = [t for t in active_timers if t.is_alive()]
    logger.debug(f"Active timers after cleanup: {[t.is_alive() for t in active_timers]}")

    # Удаляем таймеры для текущего аккаунта
    active_timers[:] = [t for t in active_timers if t.args[0] != account]
    logger.debug(f"Timers for account {account} removed before starting processing.")

    # Проверяем, установлен ли флаг завершения
    if exit_flag:
        logger.info(f"Account {account}: Exit flag detected. Skipping processing.")
        return

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
        balance = float(balance) if isinstance(balance, str) and balance.replace('.', '', 1).isdigit() else 0.0

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

        # Обновляем словарь с балансами
        with balance_lock:
            balance_dict[account] = {
                "username": username,
                "balance": balance,
                "next_schedule": next_schedule,
                "status": "Success"
            }

    except Exception as e:
        logger.warning(f"Account {account}: Error occurred during scheduled processing: {e}")
        retry_delay = random.randint(1800, 4200)  # 30–70 минут
        next_retry_time = datetime.now() + timedelta(seconds=retry_delay)

        with balance_lock:
            balance_dict[account] = {
                "username": "N/A",
                "balance": 0.0,
                "next_schedule": next_retry_time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "ERROR"
            }
        logger.info(f"Account {account}: Scheduling retry in {retry_delay // 60} minutes at {balance_dict[account]['next_schedule']}.")

        # Проверяем флаг завершения перед установкой таймера
        if not exit_flag:
            retry_timer = threading.Timer(
                retry_delay,
                process_account_once,
                args=(account, balance_dict, active_timers)
            )
            active_timers.append(retry_timer)
            retry_timer.start()
    finally:
        if bot and hasattr(bot.browser_manager, "close_browser"):
            try:
                bot.browser_manager.close_browser()
                logger.info(f"Account {account}: Browser closed after processing.")
            except Exception as e:
                logger.warning(f"Account {account}: Failed to close browser: {e}")

    # Вывод обновлённой таблицы после обработки аккаунта
    if not exit_flag:
        generate_and_display_balance_table(balance_dict, show_total=True, colored_output=True)


def process_accounts():
    """
    Обрабатывает список аккаунтов с поддержкой ретраев и таймеров, показывая общую таблицу баланса после обработки каждого аккаунта.
    При прерывании (Ctrl+C) все таймеры и браузеры закрываются.
    """
    global exit_flag  # Используем глобальный флаг для завершения

    try:
        reset_balances()
        accounts = read_accounts_from_file()
        random.shuffle(accounts)
        write_accounts_to_file(accounts)

        active_timers = []  # Список активных таймеров
        active_bots = []    # Список активных ботов для закрытия браузеров

        logger.info("Starting main cycle for account processing.")

        # Основной цикл обработки аккаунтов
        for account in accounts:
            if exit_flag:
                logger.info("Exit flag detected. Stopping account processing.")
                break  # Прерываем обработку аккаунтов

            try:
                retry_count = 0
                success = False
                adjusted_time_str = "N/A"

                while retry_count < 3 and not success:
                    if exit_flag:
                        logger.info("Exit flag detected. Stopping account processing.")
                        break  # Прерываем внутренний цикл
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
                        # Проверяем квесты
                        bot.perform_quests()
                        bot.switch_to_iframe()
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
                            raise Exception("Invalid scheduled time format")

                        logger.info(f"Account {account}: Adjusted scheduled time for next claim: {adjusted_time_str}")

                        success = True

                        # Обновление словаря балансов
                        with balance_lock:
                            balance_dict[account] = {
                                "username": username,
                                "balance": balance,
                                "next_schedule": adjusted_time_str,
                                "status": "Success"
                            }
                    except Exception as e:
                        logger.warning(f"Account {account}: Error occurred on attempt {retry_count + 1}: {e}")
                        retry_count += 1
                        if retry_count >= 3:
                            retry_delay = random.randint(1800, 4200)  # 30–70 минут
                            next_retry_time = datetime.now() + timedelta(seconds=retry_delay)
                            adjusted_time_str = next_retry_time.strftime("%Y-%m-%d %H:%M:%S")

                            with balance_lock:
                                balance_dict[account] = {
                                    "username": "N/A",
                                    "balance": 0.0,
                                    "next_schedule": adjusted_time_str,
                                    "status": "ERROR"
                                }

                            logger.warning(f"Account {account}: Scheduling retry in {retry_delay // 60} minutes at {adjusted_time_str}.")

                            # Устанавливаем таймер для повторной обработки аккаунта
                            retry_timer = threading.Timer(
                                retry_delay,
                                process_account_once,
                                args=(account, balance_dict, active_timers)
                            )
                            active_timers.append(retry_timer)
                            retry_timer.start()
                    finally:
                        if bot:
                            bot.browser_manager.close_browser()
                            active_bots.remove(bot)  # Удаляем бот из списка после закрытия браузера
                        sleep_time = random.randint(5, 15)
                        logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                        time.sleep(sleep_time)

                # Генерация итоговой таблицы баланса после обработки текущего аккаунта
                generate_and_display_balance_table(balance_dict, show_total=True, colored_output=True)

                # Установка таймера для следующего действия
                if success and adjusted_time_str != "N/A":
                    trigger_time = datetime.strptime(adjusted_time_str, "%Y-%m-%d %H:%M:%S")
                    timer = threading.Timer(
                        (trigger_time - datetime.now()).total_seconds(),
                        process_account_once,
                        args=(account, balance_dict, active_timers)
                    )
                    active_timers.append(timer)
                    timer.start()
                    logger.info(f"Account {account}: Timer set for {adjusted_time_str}.")
            except Exception as account_error:
                logger.exception(f"Critical error while processing account {account}: {account_error}")

        logger.info("All accounts processed.")

        # Ожидание завершения всех таймеров
        logger.info("Waiting for all timers to complete...")
        while not exit_flag and any(t.is_alive() for t in active_timers):
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Cancelling all timers and closing browsers...")
        exit_flag = True  # Устанавливаем флаг завершения
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
        logger.info("All timers and browsers cancelled. Exiting gracefully.")


def generate_and_display_balance_table(balance_dict, show_total=True, colored_output=True):
    """
    Генерирует таблицу балансов и выводит её в лог. Возвращает итоговый баланс, таблицу и список текущих балансов.
    
    :param balance_dict: Словарь с данными о балансе аккаунтов.
    :param show_total: Если True, выводит общий баланс.
    :param colored_output: Если True, добавляет цвета в таблицу.
    :return: tuple (список балансов, таблица в виде строки, общий баланс)
    """
    table = PrettyTable()
    table.field_names = ["ID", "Username", "Balance", "Next Scheduled Time", "Status"]
    total_balance = 0.0
    current_balances = []  # Список для хранения балансов

    with balance_lock:
        for account, data in balance_dict.items():
            row = [account, data["username"], data["balance"], data["next_schedule"], data["status"]]
            
            if colored_output:
                if data["status"] == "ERROR":
                    row = [f"{Fore.RED}{cell}{Style.RESET_ALL}" for cell in row]
                else:
                    row = [f"{Fore.CYAN}{cell}{Style.RESET_ALL}" for cell in row]
            
            table.add_row(row)
            if data["status"] != "ERROR" and isinstance(data["balance"], (int, float)):
                total_balance += data["balance"]

            # Добавляем данные в список балансов
            current_balances.append({
                "ID": account,
                "Username": data["username"],
                "Balance": data["balance"],
                "Next Scheduled Time": data["next_schedule"],
                "Status": data["status"]
            })

    # Логирование таблицы
    logger.info("\nCurrent Balance Table:\n" + str(table))
    if show_total:
        logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:,.2f}{Style.RESET_ALL}")

    return current_balances, str(table), total_balance





if __name__ == "__main__":
    while True:
        try:
            logger.info("Starting a new processing cycle...")
            process_accounts()
            # Добавляем паузу перед повторным запуском основного цикла
            pause_duration = 300  # 5 минут
            logger.info(f"Waiting {pause_duration // 60} minutes before restarting the cycle...")
            time.sleep(pause_duration)
        except KeyboardInterrupt:
            logger.info("Process interrupted by user. Exiting...")
            break
        except Exception as e:
            logger.exception(f"Unexpected error occurred: {e}. Restarting the cycle...")

