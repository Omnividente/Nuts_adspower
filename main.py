import logging
import random
import time
from telegram_bot_automation import TelegramBotAutomation
from utils import read_accounts_from_file, write_accounts_to_file, reset_balances
from colorama import Fore, Style
from prettytable import PrettyTable
from datetime import datetime, timedelta
from threading import Timer, Lock
import json
import os
###################################################################################################################
###################################################################################################################
# Загрузка настроек
def load_settings():
    settings = {}
    try:
        with open('settings.txt', 'r') as f:
            for line in f:
                key, value = line.strip().split('=', 1)
                settings[key.strip()] = value.strip()
    except FileNotFoundError:
        logging.error("Settings file 'settings.txt' not found.")
    except Exception as e:
        logging.error(f"Error reading settings file: {e}")
    return settings

settings = load_settings()

# Настройка логирования
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
            log_message = log_message.replace(record.asctime, f"{Fore.LIGHTYELLOW_EX}{record.asctime}{Style.RESET_ALL}")
            levelname = f"{self.COLORS.get(record.levelno, Fore.WHITE)}{record.levelname}{Style.RESET_ALL}"
            log_message = log_message.replace(record.levelname, levelname)
            message_color = self.COLORS.get(record.levelno, Fore.WHITE)
            log_message = log_message.replace(record.msg, f"{message_color}{record.msg}{Style.RESET_ALL}")
            return log_message

    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# Глобальные переменные
balance_dict = {}
balance_lock = Lock()
exit_flag = False
TIMERS_FILE = "timers.json"
account_lock = Lock()

def load_timers():
    """Загрузка таймеров из JSON-файла."""
    if not os.path.exists(TIMERS_FILE):
        return {}
    try:
        with open(TIMERS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading timers from file: {e}")
        return {}

def save_timers(timers):
    """Сохранение таймеров в JSON-файл."""
    try:
        with open(TIMERS_FILE, "w") as f:
            json.dump(timers, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving timers to file: {e}")
# Основная обработка аккаунта
def process_account(account, balance_dict, active_timers):
    global exit_flag
    bot = None  # Убедимся, что объект доступен для finally
    logger.info(f"Processing account: {account}")
    retry_count = 0
    success = False
    with account_lock:  # Гарантируем, что одновременно обрабатывается только один аккаунт
        while retry_count < 3 and not success and not exit_flag:
            try:
                # Инициализация объекта TelegramBotAutomation для каждой попытки
                bot = TelegramBotAutomation(account, settings)

                # Навигация и выполнение задач
                navigate_and_perform_actions(bot)

                # Получение данных аккаунта
                username = bot.get_username() or "N/A"
                balance = parse_balance(bot.get_balance())
                next_schedule = calculate_next_schedule(bot.get_time())

                # Обновление баланса
                update_balance_info(account, username, balance, next_schedule, "Success", balance_dict)
                success = True

                logger.info(f"Account {account}: Next schedule: {next_schedule.strftime('%Y-%m-%d %H:%M:%S')}")

                # Установка таймера для следующего запуска
                if next_schedule:
                    schedule_next_run(account, next_schedule, balance_dict, active_timers)
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt detected in process_account. Exiting...")
                exit_flag = True  # Устанавливаем флаг выхода
                raise  # Прерывание поднимается выше для обработки в __main__
            except Exception as e:
                retry_count += 1
                logger.warning(f"Account {account}: Error on attempt {retry_count}: {e}")
                if retry_count >= 3:
                    # Обновляем баланс с данными об ошибке
                    retry_delay = random.randint(1800, 4200)  # 30–70 минут
                    next_retry_time = datetime.now() + timedelta(seconds=retry_delay)
                    update_balance_info(account, "N/A", 0.0, next_retry_time, "ERROR", balance_dict)
                    schedule_retry(account, next_retry_time, balance_dict, active_timers, retry_delay)
            finally:
                # Закрытие браузера
                if bot:
                    try:
                        bot.browser_manager.close_browser()
                    except Exception as e:
                        logger.warning(f"Failed to close browser for account {account}: {e}")
                #time.sleep(random.randint(5, 15))  # Пауза между попытками

    if not success:
        logger.error(f"Account {account}: Failed after 3 retries.")

    # Вызов таблицы после обработки аккаунта
    generate_and_display_table(balance_dict,  table_type="balance",show_total=True)






# Навигация и выполнение действий с ботом
def navigate_and_perform_actions(bot):
    """Навигация и выполнение всех задач с ботом."""
    if not bot.navigate_to_bot():
        raise Exception("Failed to navigate to bot")
    if not bot.send_message():
        raise Exception("Failed to send message")
    if not bot.click_link():
        raise Exception("Failed to click link")
    bot.preparing_account()
    bot.perform_quests()  # Выполнение квестов
    bot.farming()


# Парсинг баланса
def parse_balance(balance):
    """Парсинг баланса из строки в число."""
    try:
        return float(balance) if balance.replace('.', '', 1).isdigit() else 0.0
    except (ValueError, TypeError):
        return 0.0


# Расчет следующего выполнения
def calculate_next_schedule(schedule_time):
    """Расчет времени следующего выполнения."""
    if ":" in schedule_time:
        hours, minutes, seconds = map(int, schedule_time.split(":"))
        return datetime.now() + timedelta(hours=hours, minutes=minutes, seconds=seconds) + timedelta(minutes=random.randint(5, 30))
    return datetime.now() + timedelta(hours=8)  # Стандартное время, если данные недоступны


# Обновление информации о балансе
def update_balance_info(account, username, balance, next_schedule, status, balance_dict):
    """Обновление информации о балансе и таймерах."""
    with balance_lock:
        balance_dict[account] = {
            "username": username,
            "balance": balance,
            "next_schedule": next_schedule.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status
        }

        # Обновляем данные таймеров в файле
        timers_data = load_timers()
        timers_data[account] = {
            "username": username,
            "next_schedule": next_schedule.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "balance": balance
        }
        save_timers(timers_data)


# Планирование следующего запуска
def schedule_next_run(account, next_schedule, balance_dict, active_timers):
    delay = (next_schedule - datetime.now()).total_seconds()
    if delay > 0:
        with balance_lock:
            timers_data = load_timers()
            account_data = balance_dict.get(account, {})
            username = account_data.get("username", "N/A")
            balance = account_data.get("balance", 0.0)

            timers_data[account] = {
                "username": username,
                "next_schedule": next_schedule.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "Active",
                "balance": balance
            }
            save_timers(timers_data)

        def run_after_delay():
            with balance_lock:
                timers_data = load_timers()
                timers_data.pop(account, None)
                save_timers(timers_data)
            process_account(account, balance_dict, active_timers)

        timer = Timer(delay, run_after_delay)
        active_timers.append(timer)
        timer.start()
        logger.info(f"Account {account}: Timer set for {next_schedule.strftime('%Y-%m-%d %H:%M:%S')}.")





# Планирование повторной попытки
def schedule_retry(account, next_retry_time, balance_dict, active_timers, retry_delay):
    """Планирование повторной попытки выполнения."""
    #retry_delay = random.randint(1800, 4200)  # 30–70 минут
    #next_retry_time = datetime.now() + timedelta(seconds=retry_delay)
    
    # Обновляем информацию о следующем запуске
    update_balance_info(account, "N/A", 0.0, next_retry_time, "ERROR", balance_dict)

    # Планируем повторный запуск process_account
    timer = Timer(
        retry_delay,
        process_account,  # process_account создаст новый bot
        args=(account, balance_dict, active_timers)
    )
    active_timers.append(timer)
    timer.start()
    
    logger.info(f"Account {account}: Retry scheduled at {next_retry_time}")


def generate_and_display_table(data, table_type="balance", show_total=True):
    """
    Универсальная функция для генерации и вывода таблиц.

    :param data: Данные для отображения (balance_dict или timers_data).
    :param table_type: Тип таблицы ("balance" или "timers").
    :param show_total: Показывать ли общий баланс (только для таблицы балансов).
    """
    table = PrettyTable()
    total_balance = 0

    if table_type == "balance":
        table.field_names = ["ID", "Username", "Balance", "Next Scheduled Time", "Status"]
        with balance_lock:
            sorted_data = sorted(
                data.items(),
                key=lambda item: datetime.strptime(item[1]["next_schedule"], "%Y-%m-%d %H:%M:%S")
                if item[1]["next_schedule"] != "N/A" else datetime.max
            )

            for account, details in sorted_data:
                balance = int(details["balance"]) if details["balance"] == int(details["balance"]) else round(details["balance"])
                next_schedule = (
                    datetime.strptime(details["next_schedule"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
                    if details["next_schedule"] != "N/A" else "N/A"
                )
                color = Fore.RED if details["status"] == "ERROR" else Fore.CYAN
                table.add_row([
                    f"{color}{account}{Style.RESET_ALL}",
                    f"{color}{details['username']}{Style.RESET_ALL}",
                    f"{color}{balance}{Style.RESET_ALL}",
                    f"{color}{next_schedule}{Style.RESET_ALL}",
                    f"{color}{details['status']}{Style.RESET_ALL}"
                ])
                if details["status"] != "ERROR":
                    total_balance += balance

        logger.info("\nCurrent Balance Table:\n" + str(table))
        if show_total:
            logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:d}{Style.RESET_ALL}")

    elif table_type == "timers":
        table.field_names = ["Account ID", "Username", "Next Scheduled Time", "Status"]
        sorted_data = sorted(
            data.items(),
            key=lambda item: datetime.strptime(item[1]["next_schedule"], "%Y-%m-%d %H:%M:%S")
        )

        for account, details in sorted_data:
            username = details.get("username", "N/A")
            next_schedule = details["next_schedule"]
            status = details["status"]
            color = Fore.GREEN if status == "Active" else Fore.RED
            table.add_row([
                f"{color}{account}{Style.RESET_ALL}",
                f"{color}{username}{Style.RESET_ALL}",
                f"{color}{next_schedule}{Style.RESET_ALL}",
                f"{color}{status}{Style.RESET_ALL}"
            ])

        logger.info("\nActive Timers Table:\n" + str(table))

def sync_timers_with_balance(balance_dict):
    """
    Синхронизирует данные активных таймеров с балансами.
    Загружает данные из timers.json и добавляет их в balance_dict,
    если соответствующие аккаунты отсутствуют или их данные устарели.
    """
    timers_data = load_timers()
    with balance_lock:
        for account, timer_info in timers_data.items():
            # Если аккаунт отсутствует в balance_dict или его данные устарели, добавляем/обновляем его
            if account not in balance_dict or balance_dict[account]["next_schedule"] != timer_info["next_schedule"]:
                balance_dict[account] = {
                    "username": timer_info.get("username", "N/A"),
                    "balance": timer_info.get("balance", 0.0),  # Загружаем баланс из таймеров
                    "next_schedule": timer_info["next_schedule"],
                    "status": timer_info["status"]
                }



if __name__ == "__main__":
    try:
        reset_balances()
        accounts = read_accounts_from_file()
        random.shuffle(accounts)
        write_accounts_to_file(accounts)

        active_timers = []
        timers_data = load_timers()
        # Синхронизация таймеров с балансами
        sync_timers_with_balance(balance_dict)
        # Вывод таблицы активных таймеров
        logger.info("Loading active timers...")
        generate_and_display_table(timers_data, table_type="timers")

        logger.info("Starting account processing cycle.")

        # Обработка каждого аккаунта
        for account in accounts:
            if exit_flag:  # Проверка флага выхода
                logger.info("Exit flag detected. Stopping account processing.")
                break
            if account in timers_data:
                timer_info = timers_data[account]
                next_schedule = datetime.strptime(timer_info["next_schedule"], "%Y-%m-%d %H:%M:%S")
                if next_schedule > datetime.now():
                    # Планируем запуск по сохраненному таймеру
                    schedule_next_run(account, next_schedule, balance_dict, active_timers)
                else:
                    # Таймер истек, запускаем немедленно
                    process_account(account, balance_dict, active_timers)
            else:        
                try:
                    process_account(account, balance_dict, active_timers)  # Обработка аккаунта
                except KeyboardInterrupt:
                    logger.info("KeyboardInterrupt detected during account processing.")
                    exit_flag = True
                    break  # Прерываем цикл обработки аккаунтов
                except Exception as e:
                    logger.warning(f"Error while processing account {account}: {e}")

                # Проверка флага выхода после обработки аккаунта
                if exit_flag:
                    logger.info("Exit flag detected. Stopping account processing.")
                    break

        logger.info("All accounts processed. Waiting for timers to complete...")
        while not exit_flag and any(timer.is_alive() for timer in active_timers):
            time.sleep(1)
        
        # Ожидание завершения всех таймеров
        while not exit_flag and any(timer.is_alive() for timer in active_timers):
            time.sleep(1)

        logger.info("Restarting the cycle in 5 minutes...")
        if not exit_flag:
            time.sleep(300)  # Задержка перед повторным запуском

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected in main loop. Exiting...")
        exit_flag = True  # Установка флага выхода
    finally:
        # Остановка всех активных таймеров
        logger.info("Cleaning up active timers...")
        for timer in active_timers:
            if timer.is_alive():
                timer.cancel()
        logger.info("All resources cleaned up. Exiting gracefully.")






