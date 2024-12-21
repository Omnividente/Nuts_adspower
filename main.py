import random
import time
from telegram_bot_automation import TelegramBotAutomation
from update_manager import check_and_update, restart_script
from utils import get_accounts, reset_balances, setup_logger, load_settings, is_debug_enabled, GlobalFlags, stop_event, get_color, visible
from colorama import Fore, Style
from prettytable import PrettyTable
from datetime import datetime, timedelta
from threading import Timer, Lock, Thread
from queue import Queue, Empty
import json
import os
import argparse
import sys
import signal
import logging
import shutil
import glob

###################################################################################################################
###################################################################################################################
# Загрузка настроек

settings = load_settings()

# Настройка логирования
logger = logging.getLogger("application_logger")

# Глобальные переменные
bot = None
active_timers = []
balance_dict = {}
balance_lock = Lock()
update_lock = Lock()
task_lock = Lock()
account_lock = Lock()
active_profile_lock = Lock()
task_queue = Queue()
has_logged_queue_empty = False
DEFAULT_UPDATE_INTERVAL = 3 * 60 * 60  # 3 часа по умолчанию
temp_dir = "temp"
TIMERS_FILE = os.path.join(temp_dir, "timers.json")  # Полный путь к файлу
ROOT_TIMERS_FILE = "timers.json"  # Путь к файлу в корневой директории
BACKUP_FILES_PATTERN = "*.backup"
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)
    logger.debug(f"Temporary folder created: {temp_dir}")
if os.path.exists(ROOT_TIMERS_FILE) and not os.path.exists(TIMERS_FILE):
    try:
        shutil.move(ROOT_TIMERS_FILE, TIMERS_FILE)
        logger.debug(f"Timers file copied from root to temp: {TIMERS_FILE}")
    except Exception as e:
        logger.error(f"Failed to copy timers file to temp: {e}")
backup_files = glob.glob(BACKUP_FILES_PATTERN)
for backup_file in backup_files:
    try:
        target_path = os.path.join(temp_dir, os.path.basename(backup_file))
        shutil.move(backup_file, target_path)
        logger.info(f"Backup file moved: {backup_file} -> {target_path}")
    except Exception as e:
        logger.error(f"Failed to move backup file {backup_file} to temp: {e}")
# Проверка и создание файла TIMERS_FILE, если он отсутствует
if not os.path.exists(TIMERS_FILE):
    with open(TIMERS_FILE, "w") as f:
        json.dump({}, f)  # Создаём пустой JSON-файл
    logger.debug(f"Timers file created: {TIMERS_FILE}")
else:
    logger.debug(f"Timers file already exists: {TIMERS_FILE}")


def schedule_periodic_update_check(task_queue: Queue, interval: int = DEFAULT_UPDATE_INTERVAL):
    """
    Планирует периодическую проверку обновлений, добавляя задачу в очередь с учётом stop_event.
    """
    def periodic_task():
        while not stop_event.is_set():  # Цикл, пока не установлен stop_event
            time.sleep(interval)  # Пауза на указанный интервал
            if stop_event.is_set():  # Проверка перед выполнением задачи
                logger.debug(
                    "Stop event set. Cancelling periodic update scheduling.")
                break

            try:
                # Проверка на наличие задачи в очереди
                found = any(
                    isinstance(task, tuple) and len(
                        task) >= 1 and task[0] == "check_updates"
                    for task in list(task_queue.queue)
                )
                if not found:
                    logger.debug("Adding scheduled update check to queue...")
                    task_queue.put(("check_updates", None))
                    logger.debug("Successfully added update check to queue.")
                else:
                    logger.debug(
                        "Scheduled update check already exists in queue.")
            except Exception as e:
                logger.error(f"Error in scheduling update check: {e}")

    # Запуск задачи в отдельном потоке
    logger.debug(
        f"Starting periodic update check thread with interval {interval} seconds.")
    Thread(target=periodic_task, daemon=True).start()


def load_timers():
    """
    Загружает таймеры из JSON-файла, фильтрует устаревшие и возвращает актуальные данные.

    :return: Словарь с таймерами.
    """
    if not os.path.exists(TIMERS_FILE):
        if is_debug_enabled():
            logger.debug(
                f"Timers file '{TIMERS_FILE}' does not exist. Returning empty dictionary.")
        return {}

    try:
        with open(TIMERS_FILE, "r") as f:
            timers = json.load(f)

        current_time = datetime.now()

        # Фильтруем устаревшие таймеры
        filtered_timers = {
            account: data
            for account, data in timers.items()
            if datetime.strptime(data["next_schedule"], "%Y-%m-%d %H:%M:%S") > current_time
        }

        if is_debug_enabled():
            logger.debug(
                f"Loaded {len(timers)} timers, {len(filtered_timers)} remain after filtering.")

        # Сохраняем обновлённый список таймеров
        save_timers(filtered_timers)

        return filtered_timers
    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to parse timers file '{TIMERS_FILE}'. Invalid JSON format: {e}")
    except KeyError as e:
        logger.error(
            f"Missing key in timers data. Details: {e}")
        if is_debug_enabled():
            logger.debug(
                f"Full timers content causing the issue:", exc_info=True)
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while loading timers.")
        if is_debug_enabled():
            logger.debug(
                f"Error details: {str(e)}", exc_info=True)

    return {}


def save_timers(timers):
    """
    Сохраняет таймеры в JSON-файл.

    :param timers: Словарь с таймерами.
    """
    try:
        with open(TIMERS_FILE, "w") as f:
            json.dump(timers, f, indent=4)

        if is_debug_enabled():
            logger.debug(
                f"Successfully saved {len(timers)} timers to file '{TIMERS_FILE}'.")
    except IOError as e:
        logger.error(
            f"Failed to write timers to file '{TIMERS_FILE}'. Check file permissions or disk space.")
        if is_debug_enabled():
            logger.debug(
                f"IOError details: {str(e)}", exc_info=True)
    except Exception as e:
        logger.error("An unexpected error occurred while saving timers.")
        if is_debug_enabled():
            logger.debug(
                f"Error details: {str(e)}", exc_info=True)


# Основная обработка аккаунта
def process_account(account, balance_dict, active_timers):
    """
    Обрабатывает указанный аккаунт, выполняя задания и обновляя данные балансов.
    Если другой аккаунт уже обрабатывается, ждёт его завершения.
    """

    logger.info(f"Processing account: {account}")
    retry_count = 0
    success = False
    message_logged = False
    global bot
    # Ожидаем освобождения глобальной блокировки
    while not stop_event.is_set():
        # Пытаемся захватить блокировку
        if active_profile_lock.acquire(blocking=False):
            try:
                logger.debug(
                    f"#{account}: Starting processing for account: {account}")
                with account_lock:
                    while retry_count < 3 and not success and not stop_event.is_set():
                        try:
                            if stop_event.is_set():
                                logger.info(
                                    f"#{account}: Detected stop event. Exiting process_account.")
                                return
                            # Инициализация объекта TelegramBotAutomation
                            bot = TelegramBotAutomation(account, settings)

                            navigate_and_perform_actions(bot)

                            # Получение данных аккаунта
                            username = bot.get_username()
                            if not username or username == "N/A":  # Проверка имени пользователя
                                raise Exception(
                                    f"#{account}: Invalid username")

                            balance = parse_balance(bot.get_balance())
                            if balance <= 0:  # Проверка баланса
                                raise Exception(
                                    f"#{account}: Invalid balance")

                            next_schedule = calculate_next_schedule(
                                bot.get_time())

                            # Обновление баланса
                            update_balance_info(
                                account, username, balance, next_schedule, "Success", balance_dict)
                            success = True

                            logger.info(
                                f"#{account}: Next schedule: {next_schedule.strftime('%Y-%m-%d %H:%M:%S')}")

                            # Установка таймера для следующего запуска
                            if next_schedule:
                                schedule_next_run(
                                    account, next_schedule, balance_dict, active_timers)

                        except KeyboardInterrupt:
                            if not GlobalFlags.interrupted:
                                logger.info("KeyboardInterrupt detected.Exiting...",
                                            extra={'color': Fore.RED})
                                GlobalFlags.interrupted = True
                            logger.info("KeyboardInterrupt detected in process_account. Exiting...", extra={
                                'color': Fore.RED})
                            stop_event.set()  # Устанавливаем флаг выхода
                            return    # Прерывание поднимается выше для обработки в __main__
                        except Exception as e:
                            retry_count += 1
                            if stop_event.is_set():
                                logger.debug(
                                    f"#{account}: Detected stop event during retry. Exiting.")
                                return
                            logger.warning(
                                f"#{account}: Error on attempt {retry_count}: {e}")
                            update_balance_info(
                                account, "N/A", 0.0, datetime.now(), "ERROR", balance_dict)
                            if retry_count >= 3:
                                retry_delay = random.randint(
                                    1800, 4200)  # 30–70 минут
                                next_retry_time = datetime.now() + timedelta(seconds=retry_delay)
                                schedule_retry(
                                    account, next_retry_time, balance_dict, active_timers, retry_delay)
                        finally:
                            if not stop_event.is_set():
                                if bot:
                                    try:
                                        bot.browser_manager.close_browser()
                                    except Exception as e:
                                        logger.warning(
                                            f"#{account}: Failed to close browser: {e}")

                # Генерация и отображение таблицы только при успешной обработке
                if success:
                    generate_and_display_table(
                        balance_dict, table_type="balance", show_total=True)

            finally:
                active_profile_lock.release()  # Освобождаем блокировку
                message_logged = False
                logger.debug(
                    f"#{account}: Completed processing for account: {account}")
            break  # Выходим из цикла ожидания
        else:
            if not message_logged:
                logger.debug(
                    f"#{account}: is waiting for the active profile to complete...")
                message_logged = True  # Устанавливаем флаг, чтобы не дублировать сообщение
            time.sleep(1)  # Период ожидания
        if stop_event.is_set():
            logger.info(
                f"#{account}: Detected stop event in outer loop. Exiting process_account.")
            return

# Навигация и выполнение действий с ботом


def navigate_and_perform_actions(bot):
    """
    Навигация и выполнение всех задач с ботом.
    """
    if stop_event.is_set():
        logger.info("Stop event detected. Aborting navigation and actions.")
        return

    if not bot.navigate_to_bot():
        raise Exception("Failed to navigate to bot")

    if stop_event.is_set():
        logger.debug("Stop event detected. Aborting after navigation.")
        return

    if not bot.send_message():
        raise Exception("Failed to send message")

    if stop_event.is_set():
        logger.debug("Stop event detected. Aborting after sending message.")
        return

    if not bot.click_link():
        raise Exception("Failed to start app")

    if stop_event.is_set():
        logger.debug("Stop event detected. Aborting after starting app.")
        return

    logger.debug("Preparing account...")
    if not bot.preparing_account():
        raise Exception("Failed to preparing account")

    if stop_event.is_set():
        logger.debug("Stop event detected. Aborting before performing quests.")
        return

    logger.debug("Performing quests...")
    bot.perform_quests()  # Выполнение квестов

    if stop_event.is_set():
        logger.debug("Stop event detected. Aborting before farming.")
        return

    logger.debug("Starting farming...")
    bot.farming()


# Парсинг баланса
def parse_balance(balance):
    """
    Парсинг баланса из строки в число.

    :param balance: Строка с балансом.
    :return: Баланс в формате float или 0.0 при ошибке.
    """
    try:
        if balance is None:
            if is_debug_enabled():
                logger.debug(
                    f"#{account}: Received None for balance. Returning 0.0.")
            return 0.0

        if isinstance(balance, (int, float)):
            if is_debug_enabled():
                logger.debug(
                    f"#{account}: Balance is already numeric: {balance}")
            return float(balance)

        if isinstance(balance, str) and balance.replace('.', '', 1).isdigit():
            parsed_balance = float(balance)
            if is_debug_enabled():
                logger.debug(
                    f"#{account}: Parsed balance successfully: {parsed_balance}")
            return parsed_balance

        if is_debug_enabled():
            logger.debug(
                f"#{account}: Invalid balance format: {balance}. Returning 0.0.")
        return 0.0
    except Exception as e:
        logger.error(f"#{account}: Error parsing balance: {e}")
        if is_debug_enabled():
            logger.debug(
                f"#{account}: Error traceback:", exc_info=True)
        return 0.0


# Расчет следующего выполнения
def calculate_next_schedule(schedule_time):
    """
    Расчёт времени следующего выполнения.

    :param schedule_time: Время в формате "HH:MM:SS" или None.
    :return: Объект datetime с рассчитанным временем.
    """
    try:
        if schedule_time and ":" in schedule_time:
            hours, minutes, seconds = map(int, schedule_time.split(":"))
            next_schedule = datetime.now() + timedelta(hours=hours, minutes=minutes,
                                                       seconds=seconds) + timedelta(minutes=random.randint(5, 30))
            if is_debug_enabled():
                logger.debug(
                    f"#{account}: Next schedule calculated from provided time '{schedule_time}': {next_schedule.strftime('%Y-%m-%d %H:%M:%S')}")
            return next_schedule

        # Если schedule_time недоступно или некорректно
        default_schedule = datetime.now() + timedelta(hours=8)
        if is_debug_enabled():
            logger.debug(
                f"#{account}: Default schedule time applied: {default_schedule.strftime('%Y-%m-%d %H:%M:%S')}")
        return default_schedule

    except Exception as e:
        logger.error(
            f"#{account}: Error calculating next schedule from time '{schedule_time}': {e}")
        if is_debug_enabled():
            logger.debug(
                f"#{account}: Error traceback:", exc_info=True)
        # Возвращаем стандартное значение при ошибке
        fallback_schedule = datetime.now() + timedelta(hours=8)
        if is_debug_enabled():
            logger.debug(
                f"#{account}: Fallback schedule time applied: {fallback_schedule.strftime('%Y-%m-%d %H:%M:%S')}")
        return fallback_schedule


# Обновление информации о балансе
def update_balance_info(account, username, balance, next_schedule, status, balance_dict):
    """
    Обновление информации о балансе и таймерах.

    :param account: Аккаунт.
    :param username: Имя пользователя.
    :param balance: Текущий баланс.
    :param next_schedule: Время следующего запуска.
    :param status: Статус выполнения.
    :param balance_dict: Словарь с балансами.
    """
    try:
        with balance_lock:
            # Обновление баланса в словаре
            balance_dict[account] = {
                "username": username,
                "balance": balance,
                "next_schedule": next_schedule.strftime("%Y-%m-%d %H:%M:%S"),
                "status": status,
            }

            # Загрузка и обновление таймеров
            timers_data = load_timers()
            # Синхронизация данных
            timers_data[account] = balance_dict[account]
            save_timers(timers_data)

            if is_debug_enabled():
                logger.debug(
                    f"#{account}: updated: "
                    f"Username: {username}, Balance: {balance}, Next Schedule: {next_schedule.strftime('%Y-%m-%d %H:%M:%S')}, Status: {status}"
                )
    except Exception as e:
        logger.error(
            f"#{account}: Error updating balance info for account {account}: {e}")
        if is_debug_enabled():
            logger.debug(
                f"#{account}: Error traceback:", exc_info=True)


# Планирование следующего запуска
def schedule_next_run(account, next_schedule, balance_dict, active_timers):
    """
    Планирует следующий запуск для указанного аккаунта.

    :param account: Аккаунт для запуска.
    :param next_schedule: Время следующего запуска.
    :param balance_dict: Словарь с балансами аккаунтов.
    :param active_timers: Список активных таймеров.
    """
    try:
        delay = (next_schedule - datetime.now()).total_seconds()

        if delay > 0:
            with balance_lock:
                if stop_event.is_set():
                    logger.info(
                        f"#{account}: Stop event set. Skipping scheduling for {account}.")
                    return

                timers_data = load_timers()
                account_data = balance_dict.get(account, {})
                username = account_data.get("username", "N/A")
                balance = account_data.get("balance", 0.0)

                # Обновляем информацию о таймере
                timers_data[account] = {
                    "username": username,
                    "next_schedule": next_schedule.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "Active",
                    "balance": balance,
                }
                save_timers(timers_data)

            def run_after_delay():
                """
                Задача, выполняемая после задержки. Добавляет аккаунт в очередь.
                """
                if stop_event.is_set():
                    logger.info(
                        f"#{account}: Stop event set. Skipping execution of scheduled task.")
                    return

                with balance_lock:
                    timers_data = load_timers()
                    timers_data.pop(account, None)
                    save_timers(timers_data)

                # Добавляем задачу в очередь обработки
                logger.debug(
                    f"#{account}: Adding account to task queue after delay.")
                task_queue.put((account, balance_dict, active_timers))

            # Создаём таймер и запускаем его
            timer = Timer(delay, run_after_delay)
            active_timers.append(timer)
            timer.start()

            if is_debug_enabled():
                logger.debug(
                    f"#{account}: Timer set for {next_schedule.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"with a delay of {delay:.2f} seconds."
                )
        else:
            logger.warning(
                f"#{account}: Next schedule for account {account} is in the past ({next_schedule}). Skipping scheduling..."
            )
    except Exception as e:
        logger.error(
            f"#{account}: Error scheduling next run for account {account}: {e}"
        )
        if is_debug_enabled():
            logger.debug(
                f"#{account}: Error traceback:", exc_info=True
            )


def task_queue_processor(task_queue, active_timers):
    global has_logged_queue_empty
    """
    Основной обработчик задач из очереди. Выполняет задачи последовательно.
    """
    logger.debug("Task queue processor started.")
    while not stop_event.is_set():
        try:
            # Получаем задачу из очереди с таймаутом
            task = task_queue.get(timeout=1)
            if stop_event.is_set():  # Проверка после ожидания
                break
            # Проверяем на сигнал завершения
            if task is None:
                logger.debug("Stop signal received. Exiting processor...")
                break

            logger.debug(f"Fetched task: {task}")

            # Обработка задач
            if isinstance(task, tuple):
                if len(task) == 2:  # check_updates
                    task_type, task_data = task
                    if task_type == "check_updates":
                        try:
                            logger.info("Running scheduled update check...")
                            check_and_update(
                                priority_task_queue=task_queue,
                                is_task_active=lambda: not task_queue.empty()
                            )
                        except Exception as e:
                            logger.error(
                                f"Error during scheduled update check: {e}")
                elif len(task) == 3:  # process_account
                    account, balance_dict, active_timers = task
                    try:
                        logger.debug(
                            f"Processing account {account} from queue.")
                        process_account(account, balance_dict, active_timers)
                    except Exception as e:
                        logger.error(
                            f"Error during account processing for {account}: {e}")
                        # Можно логировать статус профиля как "ERROR"
                        update_balance_info(
                            account, "N/A", 0.0, datetime.now(), "ERROR", balance_dict
                        )
                else:
                    logger.warning(f"Unknown task structure: {task}")
            else:
                logger.warning(f"Unexpected task structure: {task}")

            # Помечаем задачу как выполненную
            task_queue.task_done()
            logger.debug(f"Task {task} marked as done.")

        except Empty:
            if stop_event.is_set():
                logger.debug(
                    "Stop event set during queue wait. Exiting processor...")
                break
            if not has_logged_queue_empty:
                logger.debug("Queue is empty, waiting for new tasks.")
                has_logged_queue_empty = True
        except Exception as e:
            logger.error(f"Unhandled exception in task processor: {e}")

    logger.debug("Task queue processor stopped.")


# Планирование повторной попытки
def schedule_retry(account, next_retry_time, balance_dict, active_timers, retry_delay):
    """
    Планирование повторной попытки выполнения.

    :param account: Аккаунт для повторной попытки.
    :param next_retry_time: Время следующей попытки.
    :param balance_dict: Словарь с балансами аккаунтов.
    :param active_timers: Список активных таймеров.
    :param retry_delay: Задержка перед повторной попыткой (в секундах).
    """
    try:
        # Проверка на stop_event перед планированием задачи
        if stop_event.is_set():
            logger.info(
                f"#{account}: Stop event set. Skipping retry scheduling.")
            return

        # Обновляем информацию о следующем запуске
        update_balance_info(account, "N/A", 0.0,
                            next_retry_time, "ERROR", balance_dict)

        def retry_task():
            """
            Запускает повторную попытку process_account после задержки.
            """
            if stop_event.is_set():
                logger.info(
                    f"#{account}: Stop event set. Cancelling retry for account.")
                return  # Прерываем выполнение задачи

            logger.info(f"#{account}: Retrying process_account after delay.")
            process_account(account, balance_dict, active_timers)

        # Создаём таймер и добавляем в активные таймеры
        timer = Timer(retry_delay, retry_task)
        active_timers.append(timer)
        timer.start()

        # Логирование для отладки
        if is_debug_enabled():
            logger.debug(
                f"#{account}: Retry scheduled for {account} at {next_retry_time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"with a delay of {retry_delay} seconds."
            )
    except Exception as e:
        logger.error(
            f"#{account}: Error scheduling retry for account {account}: {e}")
        if is_debug_enabled():
            logger.debug(
                f"#{account}: Error traceback:", exc_info=True)


def generate_and_display_table(data, table_type="balance", show_total=True):
    """
    Универсальная функция для генерации и вывода таблиц.
    """
    try:
        table = PrettyTable()
        total_balance = 0

        if table_type == "balance":
            table.field_names = ["ID", "Username",
                                 "Balance", "Next Scheduled Time", "Status"]
            with balance_lock:
                sorted_data = sorted(
                    data.items(),
                    key=lambda item: datetime.strptime(
                        item[1]["next_schedule"], "%Y-%m-%d %H:%M:%S"
                    ) if item[1]["next_schedule"] != "N/A" else datetime.max
                )

                for account, details in sorted_data:
                    balance = (
                        int(details["balance"])
                        if details["balance"] == int(details["balance"])
                        else round(details["balance"], 2)
                    )
                    next_schedule = (
                        datetime.strptime(
                            details["next_schedule"], "%Y-%m-%d %H:%M:%S"
                        ).strftime("%Y-%m-%d %H:%M:%S")
                        if details["next_schedule"] != "N/A" else "N/A"
                    )
                    # Цвета с приоритетом: ANSI -> Windows API -> Без цвета
                    color = get_color(
                        Fore.RED) if details["status"] == "ERROR" else get_color(Fore.CYAN)
                    reset = get_color(Style.RESET_ALL)

                    table.add_row([
                        f"{color}{account}{reset}",
                        f"{color}{details['username']}{reset}",
                        f"{color}{balance}{reset}",
                        f"{color}{next_schedule}{reset}",
                        f"{color}{details['status']}{reset}",
                    ])
                    if details["status"] != "ERROR":
                        total_balance += balance

            logger.info("\nCurrent Balance Table:\n" + str(table))
            if show_total:
                total_color = get_color(Fore.MAGENTA)
                reset = get_color(Style.RESET_ALL)
                logger.info(
                    f"Total Balance: {total_color}{str(total_balance).rstrip('0').rstrip('.')}{reset}"
                )

        elif table_type == "timers":
            table.field_names = ["Account ID", "Username",
                                 "Next Scheduled Time", "Status"]
            sorted_data = sorted(
                data.items(),
                key=lambda item: datetime.strptime(
                    item[1]["next_schedule"], "%Y-%m-%d %H:%M:%S"),
            )

            for account, details in sorted_data:
                username = details.get("username", "N/A")
                next_schedule = details["next_schedule"]
                status = details["status"]
                color = get_color(
                    Fore.GREEN) if status == "Active" else get_color(Fore.RED)
                reset = get_color(Style.RESET_ALL)

                table.add_row([
                    f"{color}{account}{reset}",
                    f"{color}{username}{reset}",
                    f"{color}{next_schedule}{reset}",
                    f"{color}{status}{reset}",
                ])

            logger.info("\nActive Timers Table:\n" + str(table))

    except Exception as e:
        logger.error(f"Error generating table: {e}")
        if is_debug_enabled():
            logger.debug(f"Error traceback:", exc_info=True)


def sync_timers_with_balance(balance_dict):
    """
    Синхронизирует данные активных таймеров с балансами.
    Загружает данные из timers.json и добавляет их в balance_dict,
    если соответствующие аккаунты отсутствуют или их данные устарели.
    """
    try:
        timers_data = load_timers()
        current_time = datetime.now()

        with balance_lock:
            for account, timer_info in list(timers_data.items()):
                next_schedule = datetime.strptime(
                    timer_info["next_schedule"], "%Y-%m-%d %H:%M:%S")

                # Удаляем устаревшие таймеры
                if next_schedule <= current_time:
                    if is_debug_enabled():
                        logger.debug(
                            f"Timer expired and removed from timers.")
                    timers_data.pop(account)
                    continue

                # Если аккаунт отсутствует в balance_dict или его данные устарели, добавляем/обновляем его
                if account not in balance_dict or balance_dict[account]["next_schedule"] != timer_info["next_schedule"]:
                    balance_dict[account] = {
                        "username": timer_info.get("username", "N/A"),
                        # Загружаем баланс из таймеров
                        "balance": timer_info.get("balance", 0.0),
                        "next_schedule": timer_info["next_schedule"],
                        "status": timer_info["status"]
                    }
                    if is_debug_enabled():
                        logger.debug(
                            f"Timer data synced with balance.")

        # Сохраняем обновленный список таймеров
        save_timers(timers_data)

        if is_debug_enabled():
            logger.debug(
                f"Timers successfully synced with balance dictionary.")

    except Exception as e:
        logger.error(
            f"Error syncing timers with balance: {e}")
        if is_debug_enabled():
            logger.debug(
                f"Error traceback:", exc_info=True)


def cleanup_resources(active_timers, task_queue):
    global bot
    """Останавливает все активные таймеры, выполняет очистку ресурсов и очищает очередь."""
    logger.info("Cleaning up active timers...", extra={'color': Fore.YELLOW})

    # Завершаем все таймеры
    for timer in active_timers:
        logger.debug(f"Discarding timer during cleanup")
        if timer.is_alive():
            timer.cancel()
    active_timers.clear()
    # Очищаем задачи из очереди
    while not task_queue.empty():
        try:
            task = task_queue.get_nowait()  # Извлекаем задачу без ожидания
            logger.debug(f"Discarding task during cleanup: {task}")
            task_queue.task_done()  # Помечаем задачу как выполненную
        except Exception as e:
            logger.error(f"Error while cleaning up task queue: {e}")

    # Закрываем браузер, если он существует
    if bot:
        try:
            bot.browser_manager.close_browser()
        except Exception as e:
            logger.warning(f"Failed to close browser: {e}")

    logger.info("All resources cleaned up. Exiting gracefully.",
                extra={'color': Fore.MAGENTA})


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)

    # Настройка аргументов командной строки
    parser = argparse.ArgumentParser(
        description="Run the script with optional debug logging.")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging")
    parser.add_argument("--account", type=int,
                        help="Force processing a specific account")
    parser.add_argument(
        "--visible", type=int, choices=[0, 1], default=0, help="Set visible mode (1 for visible, 0 for headless)"
    )
    args = parser.parse_args()

    # Установка флага visible
    if args.visible == 1:
        visible.set()
        logger.info("Visible mode enabled.")
    else:
        visible.clear()
        logger.info("Headless mode enabled.")

    # Настройка логирования
    logger = setup_logger(debug_mode=args.debug, log_dir="./log")

    # Принудительный запуск аккаунта
    if args.account:
        account = args.account
        logger.debug(f"Processing account {args.account} in debug mode...")
        try:
            process_account(args.account, balance_dict, active_timers)
            logger.info(
                f"Account {args.account} processing completed. Exiting.")
        except Exception as e:
            logger.error(f"Error during forced account processing: {e}")
        finally:
            cleanup_resources(active_timers, task_queue)
            sys.exit(0)  # Завершаем выполнение после обработки аккаунта

    # Загрузка настроек и таймеров
    timers_data = load_timers()
    update_interval = int(settings.get(
        "UPDATE_INTERVAL", DEFAULT_UPDATE_INTERVAL))
    logger.debug("Performing initial update check...")
    check_and_update(priority_task_queue=task_queue,
                     is_task_active=lambda: not task_queue.empty())
    schedule_periodic_update_check(task_queue, update_interval)

    try:
        reset_balances()
        accounts = get_accounts()
        sync_timers_with_balance(balance_dict)
        generate_and_display_table(timers_data, table_type="timers")
        logger.info("Starting account processing cycle.")

        # Запуск обработчика очереди задач
        task_processor_thread = Thread(
            target=task_queue_processor,
            args=(task_queue, active_timers),
            daemon=True
        )
        task_processor_thread.start()

        # Обработка аккаунтов
        for account in accounts:
            if stop_event.is_set():
                logger.info(
                    "Stop event detected. Stopping account processing.")
                break

            try:
                # Проверяем таймеры и планируем выполнение
                if account in timers_data:
                    timer_info = timers_data[account]
                    next_schedule = datetime.strptime(
                        timer_info["next_schedule"], "%Y-%m-%d %H:%M:%S")
                    if next_schedule > datetime.now():
                        logger.debug(
                            f"#{account}: Account scheduled for {next_schedule}. Skipping immediate processing.")
                        schedule_next_run(
                            account, next_schedule, balance_dict, active_timers)
                        continue

                logger.debug(
                    f"#{account}: Adding account to task queue for processing.")
                task_queue.put((account, balance_dict, active_timers))
            except Exception as e:
                logger.error(f"Error while scheduling account {account}: {e}")

        # Ожидание завершения таймеров
        while not stop_event.is_set() and any(timer.is_alive() for timer in active_timers):
            time.sleep(1)

        # Повторное ожидание цикла
        if not stop_event.is_set():
            logger.info("Restarting the cycle in 5 minutes...")
            time.sleep(300)

    except KeyboardInterrupt:
        if not GlobalFlags.interrupted:
            logger.info("KeyboardInterrupt detected. Exiting...",
                        extra={'color': Fore.RED})
        stop_event.set()
    except Exception as e:
        logger.error(f"Unhandled exception in main loop: {e}")
    finally:
        # Завершаем ресурсы
        logger.debug("Waiting for task queue processor to stop...")
        task_queue.put(None)
        task_processor_thread.join(timeout=5)
        if task_processor_thread.is_alive():
            logger.debug(
                "Task queue processor thread did not terminate in time. Forcing shutdown.")
        cleanup_resources(active_timers, task_queue)

        # Перезапуск или завершение
        if getattr(stop_event, "restart_mode", False):
            restart_script()
        else:
            logger.debug("Main thread exiting gracefully.")
