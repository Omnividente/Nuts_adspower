import os
import sys
import subprocess
import requests
import hashlib
import logging
import json
from threading import Timer
from datetime import datetime, timedelta

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

TIMER_FILE = "timers.json"


class UpdateManager:
    def __init__(self, settings):
        """
        :param settings: Словарь настроек, загружаемый из settings.txt.
        """
        self.settings = settings
        self.update_enabled = settings.get("ENABLE_UPDATES", "true").lower() == "true"
        self.repo_url = settings.get("REPO_URL", "").strip()
        self.file_list = settings.get("FILES_TO_UPDATE", "").strip().split(",")
        self.local_dir = os.path.dirname(os.path.abspath(__file__))
        self.update_interval = int(settings.get("UPDATE_INTERVAL", 3 * 3600))  # Интервал в секундах
        self.git_available = self.check_git_installed()

    def check_git_installed(self):
        """Проверяет, установлен ли Git."""
        try:
            subprocess.check_output(["git", "--version"], stderr=subprocess.STDOUT, text=True)
            logger.info("Git is installed and available.")
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.warning("Git is not installed. Falling back to direct file updates.")
            return False

    def update_with_git(self):
        """Обновляет скрипт через Git."""
        if not self.update_enabled:
            logger.info("Updates are disabled in settings.")
            return False

        if not self.git_available:
            logger.warning("Git is not available. Skipping Git update.")
            return False

        try:
            result = subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT, text=True)
            logger.info(f"Git output:\n{result}")
            if "Already up to date." not in result:
                logger.info("Script updated successfully via Git.")
                return True  # Обновление выполнено
            else:
                logger.info("No updates found via Git.")
                return False  # Обновления нет
        except subprocess.CalledProcessError as e:
            logger.error(f"Error updating with Git:\n{e.output}")
            return False

    def get_remote_file_hash(self, file_url):
        """Получает хэш удалённого файла (MD5)."""
        try:
            response = requests.get(file_url, stream=True)
            response.raise_for_status()
            md5 = hashlib.md5()
            for chunk in response.iter_content(chunk_size=4096):
                md5.update(chunk)
            return md5.hexdigest()
        except requests.RequestException as e:
            logger.error(f"Error fetching remote file hash for {file_url}: {e}")
            return None

    def get_local_file_hash(self, file_path):
        """Вычисляет хэш локального файла (MD5)."""
        if not os.path.exists(file_path):
            return None
        md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(4096):
                    md5.update(chunk)
            return md5.hexdigest()
        except IOError as e:
            logger.error(f"Error reading local file {file_path}: {e}")
            return None

    def convert_to_raw_url(self, repo_url, file_name):
        """
        Преобразует URL репозитория в raw-ссылку для указанного файла.
        Поддерживает:
        - https://github.com/username/repository
        - git@github.com:username/repository.git
        - https://github.com/username/repository.git
        :param repo_url: Ссылка на репозиторий.
        :param file_name: Имя файла для формирования ссылки.
        :return: Преобразованный raw URL.
        """
        # Убираем ".git" и обрабатываем SSH-ссылки
        if repo_url.endswith(".git"):
            repo_url = repo_url.replace(".git", "")
        if repo_url.startswith("git@github.com:"):
            repo_url = repo_url.replace("git@github.com:", "https://github.com/")

        # Используем ветку по умолчанию
        branch = self.settings.get("DEFAULT_BRANCH", "main")  # "main" — ветка по умолчанию
        raw_url = repo_url.replace("github.com", "raw.githubusercontent.com")
        raw_url = f"{raw_url}/{branch}/{file_name.strip()}"

        return raw_url    

    def update_file(self, file_name):
        """Обновляет файл, если он изменился."""
        if not self.repo_url:
            logger.warning("REPO_URL is not configured in settings.")
            return False

        # Генерируем raw-ссылку для файла
        remote_url = self.convert_to_raw_url(self.repo_url, file_name.strip())
        local_path = os.path.join(self.local_dir, file_name.strip())

        logger.info(f"Checking for updates to {file_name} from {remote_url}...")

        remote_hash = self.get_remote_file_hash(remote_url)
        local_hash = self.get_local_file_hash(local_path)

        if remote_hash and remote_hash != local_hash:
            logger.info(f"Updating file {file_name}...")
            try:
                response = requests.get(remote_url)
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"File {file_name} updated successfully.")

                # Перезапуск, если обновился сам update_manager.py
                if file_name.strip() == "update_manager.py":
                    logger.info("update_manager.py updated. Restarting script...")
                    self.restart_script()

                return True
            except requests.RequestException as e:
                logger.error(f"Error updating file {file_name}: {e}")
                return False
        else:
            logger.info(f"No updates found for {file_name}.")
            return False



    def update_with_files(self):
        """Обновляет файлы из списка через прямое скачивание."""
        if not self.update_enabled:
            logger.info("Updates are disabled in settings.")
            return False

        if not self.repo_url:
            logger.warning("REPO_URL is not configured in settings.")
            return False

        logger.info("Checking for updates via direct file download...")
        updated = False
        for file_name in self.file_list:
            if self.update_file(file_name):
                updated = True

                # Немедленный выход, если обновился update_manager.py
                if file_name.strip() == "update_manager.py":
                    return updated
        return updated



    def check_and_update_all(self):
        """Проверяет и обновляет файлы через Git или прямое скачивание."""
        logger.info("Checking for updates...")

        if self.git_available:  # Проверяем наличие Git
            if self.update_with_git():
                self.restart_script()
                return

        # Если Git недоступен или обновлений через Git нет, используем файлы
        if self.update_with_files():
            self.restart_script()
            return

        logger.info("No updates found.")


    def restart_script(self):
        """Перезапускает текущий скрипт."""
        logger.info("Restarting script to apply updates...")
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def save_timers_to_file(self, balance_dict):
        """Сохраняет активные таймеры в файл."""
        if not balance_dict:
            logger.warning("No active timers to save.")
            return

        timers_to_save = []
        for account, data in balance_dict.items():
            timers_to_save.append({
                "account": account,
                "next_schedule": data.get("next_schedule", "N/A"),
            })

        try:
            with open(TIMER_FILE, "w") as f:
                json.dump(timers_to_save, f)
            logger.info(f"Timers saved to {TIMER_FILE}.")
        except Exception as e:
            logger.error(f"Error saving timers to file: {e}")

    def load_timers_from_file(self):
        """Загружает таймеры из файла."""
        if not os.path.exists(TIMER_FILE):
            logger.info("No timers file found. Skipping restoration.")
            return []

        try:
            with open(TIMER_FILE, "r") as f:
                restored_timers = json.load(f)
            logger.info(f"Restored {len(restored_timers)} timers from {TIMER_FILE}.")
            return restored_timers
        except Exception as e:
            logger.error(f"Error loading timers from file: {e}")
            return []

    def restore_timers(self, balance_dict, process_account_callback):
        """Восстанавливает активные таймеры из сохранённых данных."""
        restored_timers = self.load_timers_from_file()
        if not restored_timers:
            logger.info("No timers to restore.")
            return

        for timer_data in restored_timers:
            account = timer_data["account"]
            next_schedule_str = timer_data["next_schedule"]
            try:
                next_schedule = datetime.strptime(next_schedule_str, "%Y-%m-%d %H:%M:%S")
                delay = (next_schedule - datetime.now()).total_seconds()

                if delay > 0:
                    timer = Timer(
                        delay,
                        process_account_callback,
                        args=(account, balance_dict)
                    )
                    timer.start()
                    logger.info(f"Restored timer for account {account}, scheduled in {delay:.2f} seconds.")
            except Exception as e:
                logger.error(f"Error restoring timer for account {account}: {e}")

    def schedule_update_check(self):
        """Планирует проверку обновлений."""
        if not self.update_enabled:
            logger.info("Updates are disabled in settings. Skipping scheduled update check.")
            return

        next_check_time = datetime.now() + timedelta(seconds=self.update_interval)
        logger.info(f"Scheduling next update check at {next_check_time.strftime('%Y-%m-%d %H:%M:%S')}.")

        timer = Timer(self.update_interval, self.check_and_update_all)
        timer.start()
