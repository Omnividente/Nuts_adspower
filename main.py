import logging
import random
import time
import keyboard
from telegram_bot_automation import TelegramBotAutomation
from utils import read_accounts_from_file, write_accounts_to_file, reset_balances, print_balance_table, export_balances_to_csv, update_balance_table
from colorama import Fore, Style
from prettytable import PrettyTable
from termcolor import colored

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

def process_accounts():
    while True:
        reset_balances()
        accounts = read_accounts_from_file()
        random.shuffle(accounts)
        write_accounts_to_file(accounts)

        account_balances = []
        accounts_with_zero_balance = []

        # Main cycle processing
        logger.info("Starting main cycle for account processing.")
        for account in accounts:
            retry_count = 0
            success = False
            bot = None
            balance = 0.0

            while retry_count < 3 and not success:
                try:
                    bot = TelegramBotAutomation(account, settings)
                    if not bot.navigate_to_bot():
                        raise Exception("Failed to navigate to bot")
                    bot.username = bot.get_username() if hasattr(bot, 'get_username') else "N/A"
                    if not bot.send_message(settings['TELEGRAM_GROUP_URL']):
                        raise Exception("Failed to send message")
                    if not bot.click_link():
                        raise Exception("Failed to click link")
                    bot.preparing_account()
                    balance = bot.get_balance()
                    if isinstance(balance, bool):
                        balance = 0.0
                    if not isinstance(balance, (int, float)):
                        balance = 0.0
                    bot.farming()
                    bot.get_time()
                    balance = bot.get_balance()
                    if isinstance(balance, bool):
                        balance = 0.0
                    if not isinstance(balance, (int, float)):
                        balance = 0.0
                    logger.info(f"Account {account}: Processing completed successfully.")
                    success = True
                    update_balance_table(account, bot.username, balance)  # Replace "Username" with actual username if available
                except Exception as e:
                    logger.warning(f"Account {account}: Error occurred on attempt {retry_count + 1}: {e}")
                    retry_count += 1
                finally:
                    logger.info("-------------END-----------")
                    bot.browser_manager.close_browser()
                    logger.info("-------------END-----------")
                    sleep_time = random.randint(5, 15)
                    logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                    time.sleep(sleep_time)

                if retry_count >= 3:
                    logger.warning(f"Account {account}: Failed after 3 attempts.")

            if not success:
                logger.warning(f"Account {account}: Moving to next account after 3 failed attempts.")
                update_balance_table(account, bot.username if bot and bot.username else "N/A", "ERROR")

            account_balances.append((account, bot.username if bot and bot.username else "N/A", balance if success and isinstance(balance, (int, float)) else 0.0, "Success" if success else "ERROR"))

            # Collect accounts with zero balance for retry
            if balance == 0.0:
                accounts_with_zero_balance.append(account)

        # Retry accounts with zero balance
        retry_account_balances = []
        logger.info("Starting retry cycle for accounts with zero balance.")
        for account in accounts_with_zero_balance:
            retry_count = 0
            success = False
            bot = None
            balance = 0.0

            while retry_count < 3 and not success:
                try:
                    bot = TelegramBotAutomation(account, settings)
                    if not bot.navigate_to_bot():
                        raise Exception("Failed to navigate to bot")
                    bot.username = bot.get_username() if hasattr(bot, 'get_username') else "N/A"
                    if not bot.send_message(settings['TELEGRAM_GROUP_URL']):
                        raise Exception("Failed to send message")
                    if not bot.click_link():
                        raise Exception("Failed to click link")
                    bot.preparing_account()
                    balance = bot.get_balance()
                    if isinstance(balance, bool):
                        balance = 0.0
                    if not isinstance(balance, (int, float)):
                        balance = 0.0
                    bot.farming()
                    bot.get_time()
                    balance = bot.get_balance()
                    if isinstance(balance, bool):
                        balance = 0.0
                    if not isinstance(balance, (int, float)):
                        balance = 0.0
                    logger.info(f"Account {account}: Retried processing completed successfully.")
                    success = True
                    update_balance_table(account, bot.username, balance)
                except Exception as e:
                    logger.warning(f"Account {account}: Error occurred on retry attempt {retry_count + 1}: {e}")
                    retry_count += 1
                finally:
                    if bot:
                        logger.info("-------------END-----------")
                        bot.browser_manager.close_browser()
                        logger.info("-------------END-----------")
                    sleep_time = random.randint(5, 15)
                    logger.info(f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                    time.sleep(sleep_time)

                if retry_count >= 3:
                    logger.warning(f"Account {account}: Failed after 3 retry attempts.")
                    update_balance_table(account, bot.username if bot and bot.username else "N/A", "ERROR")

            retry_account_balances.append((account, bot.username if bot and bot.username else "N/A", balance if success and isinstance(balance, (int, float)) else 0.0, "Success" if success else "ERROR"))

        # Print balance tables for both the main cycle and the retry cycle
        logger.info("\nMain Cycle Balance Table:")
        main_table = PrettyTable()
        main_table.field_names = ["ID", "Username", "Balance", "Status"]
        total_balance = 0.0
        for serial_number, username, balance, status in account_balances:
            row = [serial_number, username if username else 'N/A', balance, status]
            if balance == 0.0:
                main_table.add_row([colored(cell, 'red') for cell in row])
            else:
                main_table.add_row([colored(cell, 'cyan') for cell in row])
                if isinstance(balance, (int, float)):
                    total_balance += balance

        logger.info("\n" + str(main_table))
        logger.info(f"Total Balance: {Fore.MAGENTA}{total_balance:,.2f}{Style.RESET_ALL}")

        logger.info("\nRetry Cycle Balance Table:")
        retry_table = PrettyTable()
        retry_table.field_names = ["ID", "Username", "Balance", "Status"]
        total_retry_balance = 0.0
        for serial_number, username, balance, status in retry_account_balances:
            row = [serial_number, username if username else 'N/A', balance, status]
            retry_table.add_row([colored(cell, 'yellow') for cell in row])
            if status == "Success" and isinstance(balance, (int, float)):
                total_retry_balance += balance

        logger.info("\n" + str(retry_table))
        logger.info(f"Total Retry Balance: {Fore.MAGENTA}{total_retry_balance:,.2f}{Style.RESET_ALL}")

        logger.info("All accounts processed. Waiting 8 hours before restarting.")
        for hour in range(8):
            logger.info(f"Waiting... {8 - hour} hours left till restart.")
            time.sleep(60 * 60)

if __name__ == "__main__":
    try:
        process_accounts()
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Exiting...")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
