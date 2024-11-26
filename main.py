import logging
import random
import time
from telegram_bot_automation import TelegramBotAutomation
from utils import read_accounts_from_file, write_accounts_to_file, reset_balances
from colorama import Fore, Style
from prettytable import PrettyTable
from datetime import datetime, timedelta
from threading import Timer, Lock
from update_manager import UpdateManager
import os

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

# Создание объекта UpdateManager
update_manager = UpdateManager(settings)

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
active_bots = []


# Основная обработка аккаунта
def process_account(account, balance_dict, active_timers):
    global exit_flag

    logger.info(f"Processing account: {account}")
    retry_count = 0
    success = False

    while retry_count < 3 and not success and not exit_flag:
        try:
            # Инициализация объекта TelegramBotAutomation для каждой попытки
            bot = TelegramBotAutomation(account, settings)
            active_bots.append(bot)  # Добавляем объект в список активных ботов
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
        except Exception as e:
            retry_count += 1
            logger.warning(f"Account {account}: Error on attempt {retry_count}: {e}")
            if retry_count >= 3:
                # Обновляем баланс с данными об ошибке
                retry_delay = random.randint(1800, 4200)  # 30–70 минут
                next_retry_time = datetime.now() + timedelta(seconds=retry_delay)
                update_balance_info(account, "N/A", 0.0, next_retry_time, "ERROR", balance_dict)
                schedule_retry(account, next_retry_time, balance_dict, active_timers)
        finally:
            try:
                if bot:
                    bot.browser_manager.close_browser()  # Закрываем браузер
                    active_bots.remove(bot)  # Удаляем объект из списка активных ботов
            except Exception as e:
                logger.warning(f"Failed to close browser for account {account}: {e}")
            time.sleep(random.randint(5, 15))  # Пауза между попытками

    if not success:
        logger.error(f"Account {account}: Failed after 3 retries.")

    # Вызов таблицы после обработки аккаунта
    generate_and_display_balance_table(balance_dict, show_total=True)

update_manager.restore_timers(balance_dict, process_account)




# Навигация и выполнение действий с ботом
def navigate_and_perform_actions(bot):
    """Навигация и выполнение всех задач с ботом."""
    if not bot.navigate_to_bot():
        raise Exception("Failed to navigate to bot")
    if not bot.send_message(settings['TELEGRAM_GROUP_URL']):
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
    """Обновление информации о балансе."""
    with balance_lock:
        balance_dict[account] = {
            "username": username,
            "balance": balance,
            "next_schedule": next_schedule.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status
        }


# Планирование следующего запуска
def schedule_next_run(account, next_schedule, balance_dict, active_timers):
    delay = (next_schedule - datetime.now()).total_seconds()
    if delay > 0:
        timer = Timer(
            delay,
            process_account,  # Передаём только account
            args=(account, balance_dict, active_timers)
        )
        active_timers.append(timer)
        timer.start()
        logger.info(f"Account {account}: Timer set for {next_schedule.strftime('%Y-%m-%d %H:%M:%S')}.")




# Планирование повторной попытки
def schedule_retry(account, balance_dict, active_timers):
    """Планирование повторной попытки выполнения."""
    retry_delay = random.randint(1800, 4200)  # 30–70 минут
    next_retry_time = datetime.now() + timedelta(seconds=retry_delay)
    
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



# Генерация и вывод таблицы балансов
from colorama import Fore, Style

def generate_and_display_balance_table(balance_dict, show_total=True):
    """Генерация таблицы балансов и её вывод."""
    table = PrettyTable()
    table.field_names = ["ID", "Username", "Balance", "Next Scheduled Time", "Status"]
    total_balance = 0

    with balance_lock:
        # Сортировка аккаунтов по времени следующего запуска
        sorted_accounts = sorted(
            balance_dict.items(),
            key=lambda item: datetime.strptime(item[1]["next_schedule"], "%Y-%m-%d %H:%M:%S")
            if item[1]["next_schedule"] != "N/A" else datetime.max
        )

        for account, data in sorted_accounts:
            # Преобразуем баланс в целое число
            balance = int(data["balance"]) if data["balance"] == int(data["balance"]) else round(data["balance"])

            # Преобразуем время в читаемый формат
            next_schedule = (
                datetime.strptime(data["next_schedule"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
                if data["next_schedule"] != "N/A" else "N/A"
            )

            # Выбираем цвет для строки в зависимости от статуса
            if data["status"] == "ERROR":
                color = Fore.RED
            else:
                color = Fore.CYAN

            # Добавляем строку с цветами
            table.add_row([
                f"{color}{account}{Style.RESET_ALL}",
                f"{color}{data['username']}{Style.RESET_ALL}",
                f"{color}{balance}{Style.RESET_ALL}",
                f"{color}{next_schedule}{Style.RESET_ALL}",
                f"{color}{data['status']}{Style.RESET_ALL}"
            ])
            if data["status"] != "ERROR":
                total_balance += balance

    # Вывод таблицы в лог
    logger.info("\nCurrent Balance Table:\n" + str(table))
    if show_total:
        logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:d}{Style.RESET_ALL}")

def wait_for_timers_to_finish(active_timers):
    """Ожидает завершения всех таймеров."""
    for timer in active_timers:
        if timer.is_alive():
            logger.info(f"Waiting for timer {timer} to finish...")
            timer.join()  # Ожидаем завершения таймера



if __name__ == "__main__":
    try:
        # Проверяем обновления перед запуском основного цикла
        update_manager.check_and_update_all()

        # Планируем периодическую проверку обновлений
        update_manager.schedule_update_check()
        #
        reset_balances()
        accounts = read_accounts_from_file()
        random.shuffle(accounts)
        write_accounts_to_file(accounts)

        active_timers = []

        logger.info("Starting account processing cycle.")

        # Обработка каждого аккаунта
        for account in accounts:
            if exit_flag:
                break

            try:
                # Передаём обработку аккаунта в process_account
                process_account(account, balance_dict, active_timers)
            except Exception as e:
                logger.warning(f"Error while processing account {account}: {e}")

        # Генерация таблицы после завершения обработки всех аккаунтов
        logger.info("Generating final balance table...")
        generate_and_display_balance_table(balance_dict, show_total=True)

        logger.info("All accounts processed. Waiting for timers to complete...")
        while not exit_flag and any(t.is_alive() for t in active_timers):
            time.sleep(1)

        logger.info("Restarting the cycle in 5 minutes...")
        time.sleep(300)  # 5 минут

    except KeyboardInterrupt:
        logger.info("Exiting on user interrupt...")
        exit_flag = True
        update_manager.save_timers_to_file(balance_dict)

        # Остановка всех таймеров
        logger.info("Cancelling all timers...")
        for timer in active_timers:
            if timer.is_alive():
                timer.cancel()

        # Закрытие всех активных браузеров
        logger.info("Closing all active browsers...")
        for bot in list(active_bots):
            try:
                bot.browser_manager.close_browser()
                logger.info(f"Browser for bot {bot} closed successfully.")
            except Exception as e:
                logger.warning(f"Failed to close browser: {e}")
            finally:
                active_bots.remove(bot)

        # Лог активных потоков
        logger.info("Logging active threads before exit...")
        log_active_threads()

        # Принудительное завершение
        logger.info("All resources cleaned up. Forcing exit...")
        os._exit(0)






