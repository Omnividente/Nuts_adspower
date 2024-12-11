import logging
from colorama import Fore, Style, init
from functools import wraps

# Инициализация colorama для Windows
init(autoreset=True)

# Глобальная переменная для логгера
logger = None
# Функция для настройки логирования
# Класс для форматирования логов
# Класс для форматирования логов
# Класс для форматирования логов
class CustomFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def __init__(self, fmt=None, datefmt="%Y-%m-%d %H:%M:%S"):
        """
        Инициализация форматтера с пользовательским форматом и форматом времени.
        """
        super().__init__(fmt, datefmt)
        self.datefmt = datefmt

    def format(self, record):
        """
        Форматирование лог-сообщения с цветами и временем.
        """
        # Форматируем время
        record.asctime = self.formatTime(record, self.datefmt)
        
        # Получаем базовое сообщение
        log_message = super().format(record)

        # Устанавливаем цвет времени
        log_message = log_message.replace(
            record.asctime, f"{Fore.LIGHTYELLOW_EX}{record.asctime}{Style.RESET_ALL}"
        )

        # Проверяем, есть ли временный цвет для уровня логирования
        temp_color = getattr(record, 'color', None)  # Получаем временный цвет из record

        if temp_color:
            # Если указан временный цвет, используем его
            levelname = f"{temp_color}{record.levelname}{Style.RESET_ALL}"
            log_message = log_message.replace(record.levelname, levelname)
            message_color = temp_color
        else:
            # Стандартный цвет для уровня логирования
            levelname = f"{self.COLORS.get(record.levelno, Fore.WHITE)}{record.levelname}{Style.RESET_ALL}"
            log_message = log_message.replace(record.levelname, levelname)
            message_color = self.COLORS.get(record.levelno, Fore.WHITE)

        # Устанавливаем цвет сообщения
        log_message = log_message.replace(record.msg, f"{message_color}{record.msg}{Style.RESET_ALL}")

        return log_message


# Функция для настройки логирования
def setup_logger():
    global logger
    if logger is None:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)  # Установите уровень логирования на DEBUG или INFO

        # Настроим обработчик для вывода логов в консоль
        handler = logging.StreamHandler()
        handler.setFormatter(CustomFormatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)

    return logger

def is_debug_enabled():
    """
    Проверяет, включён ли режим DEBUG для глобального логгера.
    """
    global logger
    if logger is None:
        setup_logger()
    return logger.isEnabledFor(logging.DEBUG)

# Настроим логирование (если не было настроено ранее)
logger = setup_logger()

balances = []

def read_accounts_from_file():
    try:
        with open('accounts.txt', 'r') as file:
            accounts = [line.strip() for line in file.readlines()]
            logger.debug(f"Successfully read {len(accounts)} accounts from file.")
            return accounts
    except FileNotFoundError:
        logger.error("accounts.txt file not found.")
        return []
    except Exception as e:
        logger.exception(f"Unexpected error while reading accounts file: {str(e)}")
        return []

def reset_balances():
    global balances
    balances = []
    logger.debug("Balances reset successfully.")

def suppress_stacktrace(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (WebDriverException, StaleElementReferenceException) as e:
            error_message = str(e).splitlines()[0]
            logger.warning(f"{func.__name__}: Exception occurred: {error_message}")
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
    return wrapper