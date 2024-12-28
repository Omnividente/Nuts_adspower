import logging
from colorama import Fore, Style, init
from logging.handlers import RotatingFileHandler
import os
import threading
import atexit
import sys
import re
import ctypes
import requests
import importlib
import time
import glob

# Инициализация colorama для Windows
init(autoreset=True)

# Глобальный stop_event для управления остановкой
stop_event = threading.Event()
visible = threading.Event()
stop_event.restart_mode = False

# Глобальная переменная для логгера
logger = None
# Класс для форматирования логов
# Цвета для Windows API (альтернативный способ)
WINDOWS_COLORS = {
    logging.DEBUG: 11,    # Aqua
    logging.INFO: 10,     # Green
    logging.WARNING: 14,  # Yellow
    logging.ERROR: 12,    # Red
    logging.CRITICAL: 13  # Magenta
}


# Проверка поддержки ANSI
def supports_ansi():
    """
    Проверяет поддержку ANSI-кодов в текущей консоли.
    Возвращает True, если поддержка обнаружена, иначе False.
    """
    if os.name == 'nt':  # Windows
        # Проверяем переменные среды для новых консолей
        if 'ANSICON' in os.environ or 'WT_SESSION' in os.environ:
            return True
        try:
            # Попытка включить поддержку ANSI через Windows API
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, 7)
            return True
        except Exception:
            return False
    # Для Unix-систем просто проверяем, является ли вывод терминалом
    return sys.stdout.isatty()


def supports_windows_api():
    """Проверяет поддержку Windows API для цвета через ctypes."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        return True
    except Exception:
        return False


def get_color(color_code):
    """
    Возвращает цвет для вывода на консоль.
    Приоритет: ANSI -> Windows API -> Без цвета.
    """
    if supports_ansi():
        return color_code  # ANSI-коды поддерживаются
    elif supports_windows_api():
        return color_code  # Windows API через colorama
    return ""  # Цвета не поддерживаются


# Альтернативный способ для старых Windows-консолей
class WindowsColorHandler(logging.StreamHandler):
    """
    Обработчик для вывода логов с цветами в старых Windows-консолях.
    Использует Windows API для изменения цвета текста.
    """

    def emit(self, record):
        try:
            message = self.format(record)
            color = WINDOWS_COLORS.get(
                record.levelno, 7)  # 7 = Default (White)
            # Получаем дескриптор консоли и устанавливаем цвет
            handle = ctypes.windll.kernel32.GetStdHandle(-11)
            ctypes.windll.kernel32.SetConsoleTextAttribute(handle, color)
            sys.stderr.write(f"{message}\n")
            sys.stderr.flush()
            # Возвращаем цвет по умолчанию
            ctypes.windll.kernel32.SetConsoleTextAttribute(handle, 7)
        except Exception:
            self.handleError(record)


# Форматтер для удаления ANSI-кодов из логов
class StripAnsiFormatter(logging.Formatter):
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def format(self, record):
        msg = super().format(record)
        return self.ANSI_ESCAPE.sub('', msg)


# Цветной форматтер с поддержкой ANSI
class CustomFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def __init__(self, fmt=None, datefmt="%Y-%m-%d %H:%M:%S", ansi_supported=True):
        super().__init__(fmt, datefmt)
        self.ansi_supported = ansi_supported

    def format(self, record):
        record.asctime = self.formatTime(record, self.datefmt)
        log_message = super().format(record)

        if not self.ansi_supported:
            return log_message

        log_message = log_message.replace(
            record.asctime, f"{Fore.LIGHTYELLOW_EX}{record.asctime}{Style.RESET_ALL}"
        )
        temp_color = getattr(record, 'color', None)
        if temp_color:
            levelname = f"{temp_color}{record.levelname}{Style.RESET_ALL}"
            message_color = temp_color
        else:
            levelname = f"{self.COLORS.get(record.levelno, Fore.WHITE)}{record.levelname}{Style.RESET_ALL}"
            message_color = self.COLORS.get(record.levelno, Fore.WHITE)

        log_message = log_message.replace(record.levelname, levelname)
        log_message = log_message.replace(
            record.msg, f"{message_color}{record.msg}{Style.RESET_ALL}")
        return log_message
# Глобальная блокировка для защиты операций с файлами логов
log_lock = threading.Lock()

class SafeRotatingFileHandler(RotatingFileHandler):
    def doRollover(self):
        """
        Переопределённый метод для безопасной ротации файла логов.
        Закрывает файл перед ротацией и использует блокировку.
        """
        with log_lock:
            if self.stream:
                self.stream.close()
                self.stream = None
            # Выполняем стандартную ротацию
            super().doRollover()
            # Пересоздаём файловый поток после ротации
            self.stream = self._open()

# Настройка логгера

def setup_logger(debug_mode=False, log_to_file=True, log_file_size=512 * 1024, backup_count=1, log_dir="."):
    """
    Настройка логирования с разными уровнями для консоли и файла, с ротацией логов.
    :param debug_mode: Если True, в консоль выводятся DEBUG сообщения.
    :param log_to_file: Если True, логи записываются в файл.
    :param log_file_size: Максимальный размер файла логов (в байтах).
    :param backup_count: Количество резервных копий файла логов.
    :param log_dir: Директория для хранения файлов логов.
    """
    global stop_event  # Убедимся, что функция использует глобальную переменную stop_event
    logger = logging.getLogger("application_logger")  # Используем фиксированное имя логгера
    logger.setLevel(logging.DEBUG)  # Устанавливаем самый высокий уровень для логгера

    # Создаём временный обработчик для логирования на этапе удаления файлов
    temp_handler = logging.StreamHandler()
    temp_handler.setFormatter(CustomFormatter("%(asctime)s - %(levelname)s - %(message)s"))
    temp_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    logger.addHandler(temp_handler)

    # Удаляем старые обработчики (если есть)
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    # Проверяем stop_event перед продолжением
    if stop_event.is_set():
        temp_handler.setLevel(logging.INFO)  # Уменьшаем уровень логирования
        logger.info("Stop event detected during setup. Logger setup aborted.")
        logging.shutdown()
        return logger

    # Создаём директорию для логов, если она не существует
    if log_to_file:
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
                logger.debug(f"Log directory created: {log_dir}")
            except Exception as e:
                logger.error(f"Failed to create log directory: {log_dir}. Error: {e}")
                raise

    # Удаляем старые файлы логов
    if log_to_file:
        log_pattern = os.path.join(log_dir, "debug.log*")
        for log_file in glob.glob(log_pattern):
            try:
                os.remove(log_file)
                logger.debug(f"Log file deleted: {log_file}")
            except PermissionError:
                logger.debug(f"Failed to delete log file {log_file}: file is locked.")
            except Exception as e:
                logger.error(f"Error deleting log file {log_file}: {e}")

    # Удаляем временный обработчик после завершения инициализации
    logger.removeHandler(temp_handler)

    # Проверка поддержки ANSI
    ansi_supported = supports_ansi()

    # Форматтеры
    console_formatter = CustomFormatter(
        "%(asctime)s - %(levelname)s - %(message)s", ansi_supported=ansi_supported
    )
    file_formatter = StripAnsiFormatter("%(asctime)s - %(levelname)s - %(message)s")

    # Обработчик для консоли
    if ansi_supported:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
    else:
        # Альтернативный обработчик для старых Windows-консолей
        console_handler = WindowsColorHandler()
        console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Уровень логирования для консоли
    console_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    logger.addHandler(console_handler)

    # Обработчик для файла с ротацией
    if log_to_file:
        log_file = os.path.join(log_dir, "debug.log")
        try:
            file_handler = SafeRotatingFileHandler(
                log_file, mode='a', maxBytes=log_file_size, backupCount=backup_count, encoding="utf-8"
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
        except PermissionError:
            logger.warning("Failed to create log file due to permission issues.")

    # Регистрация безопасного завершения работы логгера при выходе
    def shutdown_logging():
        logger.debug("Shutting down logging...")
        logging.shutdown()

    # Проверяем stop_event перед завершением настройки
    if stop_event.is_set():
        logger.shutdown_logging("Stop event detected. Shutting down logging.")
        shutdown_logging()
        return logger

    atexit.register(shutdown_logging)
    return logger


# Загрузка настроек
def load_settings():
    settings = {}
    try:
        with open('settings.txt', 'r', encoding='utf-8') as f:
            for line in f:
                # Удаляем лишние пробелы и проверяем пустую строку или комментарий
                line = line.strip()
                if not line or line.startswith('#'):
                    continue  # Пропускаем пустые строки и комментарии

                # Проверяем наличие символа '='
                if '=' not in line:
                    logging.warning(f"Ignoring invalid setting: {line}")
                    continue

                # Разделяем только по первому '='
                key, value = line.split('=', 1)
                # Удаляем комментарии из значения
                value = value.split('#')[0].strip()
                settings[key.strip()] = value
    except FileNotFoundError:
        logging.error("Settings file 'settings.txt' not found.")
    except Exception as e:
        logging.error(f"Error reading settings file: {e}")
    return settings
# Функция для настройки логирования


def is_debug_enabled():
    """
    Проверяет, включён ли режим DEBUG для глобального логгера.
    """
    global logger
    if logger is None:
        setup_logger()
    return logger.isEnabledFor(logging.DEBUG)


# Настроим логирование (если не было настроено ранее)
logger = setup_logger(debug_mode=False, log_dir="./log")

balances = []


def read_accounts_from_file():
    """
    Reads accounts from the 'accounts.txt' file.
    """
    try:
        with open('accounts.txt', 'r') as file:
            accounts = [line.strip() for line in file if line.strip()]
            logger.debug(
                f"Successfully read {len(accounts)} accounts from accounts.txt.")
            return accounts
    except FileNotFoundError:
        logger.debug("The accounts.txt file was not found.")
        return []
    except Exception as e:
        logger.debug(
            f"An unexpected error occurred while reading accounts.txt: {e}")
        return []


def parse_accounts_parameter(accounts_param):
    """
    Parses the accounts parameter from settings.txt.
    """
    accounts_set = set()
    accounts_param = accounts_param.replace(' ', '')  # Remove spaces
    if not accounts_param:
        return []

    parts = accounts_param.split(',')
    for part in parts:
        if '-' in part:
            try:
                start, end = part.split('-')
                start, end = int(start), int(end)
                accounts_set.update(range(start, end + 1))
            except ValueError:
                logger.debug(
                    f"Invalid range '{part}' in the accounts parameter.")
        else:
            try:
                accounts_set.add(int(part))
            except ValueError:
                logger.debug(
                    f"Invalid account number '{part}' in the accounts parameter.")
    return sorted(accounts_set)


def get_all_profiles():
    """
    Retrieves all profiles via the AdsPower local API.
    """
    url = "http://localhost:50325/api/v1/user/list"
    page = 1
    profiles = []

    while True:
        params = {"page": page, "page_size": 100}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            if data.get("code") != 0:
                logger.debug(f"API error: {data.get('msg')}")
                break

            current_profiles = data["data"]["list"]
            if not current_profiles:
                break

            profiles.extend(current_profiles)
            page += 1

            stop_event.wait(1)
        except requests.RequestException as e:
            logger.debug(f"An error occurred while accessing the API: {e}")
            break

    return profiles


def get_accounts():
    """
    Determines the list of accounts to process.
    """
    settings = load_settings()
    accounts_param = settings.get('ACCOUNTS', '').strip()

    if accounts_param:
        accounts = parse_accounts_parameter(accounts_param)
        if accounts:
            logger.info(f"Accounts retrieved from settings")
            logger.debug(f"{accounts}")
            return accounts
        else:
            logger.debug(
                "The accounts parameter in settings is empty after parsing.")
    else:
        logger.debug("The accounts parameter is missing in settings.")

    # Read from accounts.txt
    accounts_from_file = read_accounts_from_file()
    if accounts_from_file:
        logger.info(f"Accounts retrieved from accounts.txt")
        logger.debug(f"{accounts_from_file}")
        return accounts_from_file

    # Retrieve all profiles
    profiles = get_all_profiles()
    if profiles:
        accounts_from_profiles = [profile['serial_number']
                                  for profile in profiles]
        logger.info(f"Accounts retrieved from ADS profiles")
        logger.debug(f"{accounts_from_profiles}")
        return accounts_from_profiles

    # If nothing could be retrieved
    logger.error("Failed to retrieve the account list from any source.")
    return []


def reset_balances():
    global balances
    balances = []
    logger.debug("Balances reset successfully.")


def get_max_games(settings):
    """
    Возвращает максимальное количество игр из настроек.

    :param settings: Словарь с настройками.
    :return: Целое число максимального количества игр или None, если значение не указано или некорректно.
    """
    # Приводим ключи в нижний регистр
    settings = {k.lower(): v for k, v in settings.items()}
    max_games = settings.get('max_games', None)

    # Если значение max_games задано, проверяем его корректность
    if max_games:
        if max_games.isdigit():
            if is_debug_enabled():
                logger.debug(f"Max games set to {max_games}.")
            return int(max_games)
        else:
            logger.warning(
                f"Invalid value for 'max_games': {max_games}. Using all available games.")
    else:
        if is_debug_enabled():
            logger.debug(
                "'max_games' not found in settings. No limit applied.")

    return None  # Если max_games не задано или указано некорректно, возвращаем None

def check_requirements(requirements_file="requirements.txt"):
    """
    Проверяет зависимости из файла requirements.txt.
    Если зависимости отсутствуют, выводит предупреждение и завершает выполнение.
    :param requirements_file: Путь к файлу requirements.txt
    """    

    try:
        # Читаем зависимости из requirements.txt
        with open(requirements_file, "r") as f:
            requirements = f.read().splitlines()

        missing_packages = []
        for req in requirements:
            # Удаляем указание версии (если есть) для проверки пакета
            package = req.split("==")[0].strip()
            try:
                importlib.import_module(package)
            except ImportError:
                missing_packages.append(req)

        # Если есть недостающие зависимости
        if missing_packages:
            logger.error("Some dependencies are missing:")
            for pkg in missing_packages:
                logger.error(f"  - {pkg}")

            logger.error("\nYou can install them using the command:")
            logger.error(f"pip install -r {requirements_file}\n")

            # Завершаем выполнение
            stop_event.set()

        logger.info("All dependencies are installed.")

    except FileNotFoundError:
        logger.critical(f"Error: The file {requirements_file} was not found.")
        stop_event.set()
    except Exception as e:
        logger.critical(f"Unknown error: {str(e)}")
        stop_event.set()

class GlobalFlags:
    interrupted = False
