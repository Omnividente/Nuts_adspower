import os
import subprocess
import requests
import sys
import time
from threading import Lock
from utils import setup_logger, load_settings, GlobalFlags, stop_event
from colorama import Fore, Style

logger = setup_logger()
update_lock = Lock()

# ========================= Классы ==========================


class GitUpdater:
    """
    Класс для обновления через Git.
    """
    @staticmethod
    def is_git_installed():
        try:
            subprocess.run(["git", "--version"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True)
            logger.debug("Git is installed on the system.")
            return True
        except FileNotFoundError:
            logger.debug("Git is not installed on this system.")
            return False
        except Exception as e:
            logger.error(f"Error while checking for Git installation: {e}")
            return False

    @staticmethod
    def check_updates():
        try:
            logger.debug("Checking for updates via Git...")
            subprocess.run(["git", "fetch"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True)
            result = subprocess.run(
                ["git", "status", "-uno"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            output = result.stdout.decode("utf-8")
            logger.debug(f"Git status output: {output}")
            return "Your branch is behind" in output
        except Exception as e:
            logger.warning(f"Git update check failed: {e}")
            return False

    @staticmethod
    def perform_update():
        try:
            logger.info("Updating via Git...")
            subprocess.run(["git", "pull"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True)
            logger.info("Update completed successfully via Git.")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git pull failed due to local changes: {e}")
            try:
                logger.info("Resetting local changes...")
                subprocess.run(["git", "reset", "--hard"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                logger.info("Retrying git pull after resetting changes...")
                subprocess.run(["git", "pull"], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, check=True)
                logger.info(
                    "Update completed successfully after resetting local changes.")
                return True
            except subprocess.CalledProcessError as reset_error:
                logger.error(
                    f"Update failed even after resetting changes: {reset_error}")
                return False


class FileUpdater:
    """
    Класс для обновления файлов напрямую через raw URL.
    """
    @staticmethod
    def check_updates():
        """
        Проверяет обновления для локальных файлов на основе удалённого репозитория.
        Если указан файл remote_files_for_update, загружает список файлов из него.
        """
        settings = load_settings()
        repo_url = settings.get("REPOSITORY_URL")
        files_to_update = [file.strip() for file in settings.get(
            "FILES_TO_UPDATE", "").split(",") if file.strip()]
        branch = "main"  # Укажите ветку

        if not repo_url:
            logger.error("Repository URL is not specified in settings.")
            return False, []

        # Проверяем наличие специального файла remote_files_for_update
        if "remote_files_for_update" in files_to_update:
            logger.info("Fetching file list from remote_files_for_update...")
            try:
                # Формируем URL для получения файла remote_files_for_update
                timestamp = int(time.time())
                raw_url = f"https://raw.githubusercontent.com/{repo_url.split('/')[-2]}/{repo_url.split('/')[-1]}/{branch}/remote_files_for_update?nocache={timestamp}"
                headers = {"Cache-Control": "no-cache"}
                response = requests.get(raw_url, headers=headers, timeout=10)
                response.raise_for_status()

                # Загрузка и парсинг файла
                remote_files_content = response.text.strip()
                files_to_update = [
                    file.strip() for file in remote_files_content.splitlines() if file.strip()]
                logger.info(f"Fetched files from remote_files_for_update: {files_to_update}")
            except Exception as e:
                logger.error(f"Failed to fetch remote_files_for_update: {e}")
                return False, []

        if not files_to_update:
            logger.error("No files specified in FILES_TO_UPDATE or remote_files_for_update.")
            return False, []

        updates = []
        headers = {
            "Cache-Control": "no-cache"  # Принудительное обновление без кэширования
        }

        for file_path in files_to_update:
            try:
                # Формируем URL для получения файла через raw.githubusercontent.com с параметром для обхода кэша
                timestamp = int(time.time())
                raw_url = f"https://raw.githubusercontent.com/{repo_url.split('/')[-2]}/{repo_url.split('/')[-1]}/{branch}/{file_path}?nocache={timestamp}"

                # Отправляем запрос
                response = requests.get(raw_url, headers=headers, timeout=10)
                response.raise_for_status()

                # Получаем удалённое содержимое файла
                remote_content = response.content

                # Проверяем локальный файл
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        local_content = f.read()
                    # Сравниваем локальное и удалённое содержимое
                    if local_content != remote_content:
                        updates.append(file_path)
                else:
                    updates.append(file_path)

            except Exception as e:
                logger.error(f"Error checking file {file_path}: {e}")

        # Логируем список обновлений в конце
        if updates:
            logger.info(f"Updates found for the following files: {updates}")
        else:
            logger.debug("No updates found.")

        return bool(updates), updates


    @staticmethod
    def perform_update(update_files, repo_url, stop_on_failure=True):
        """
        Обновляет файлы через URL и создаёт резервные копии.
        Возвращает True при успешном обновлении всех файлов, иначе False.
        """
        logger.info("Updating files directly via raw URLs...")
        if repo_url.endswith(".git"):
            repo_url = repo_url[:-4]

        branch = "main"  # Укажите ветку
        success = True   # Флаг успешности

        for file_path in update_files:
            try:
                logger.info(f"Updating file: {file_path}")

                # Добавление уникального параметра для обхода кэша
                timestamp = int(time.time())
                raw_url = (
                    f"https://raw.githubusercontent.com/"
                    f"{repo_url.split('/')[-2]}/{repo_url.split('/')[-1]}/{branch}/{file_path}?nocache={timestamp}"
                )

                # Установка заголовка Cache-Control для запросов
                headers = {"Cache-Control": "no-cache"}
                response = requests.get(raw_url, headers=headers, timeout=10)
                response.raise_for_status()

                content = response.content

                # Создание резервной копии
                backup_path = f"{file_path}.backup"
                if os.path.exists(backup_path):
                    os.remove(backup_path)

                if os.path.exists(file_path):
                    os.rename(file_path, backup_path)

                # Запись файла
                with open(file_path, "wb") as f:
                    f.write(content)

                logger.info(f"File {file_path} updated successfully.")

            except Exception as e:
                logger.error(f"Error updating file {file_path}: {e}")
                success = False
                if stop_on_failure:
                    raise  # Немедленное прерывание, если флаг установлен

        return success


# ========================= Основная логика ==========================


def restart_script():
    # signal.signal(signal.SIGINT, signal.default_int_handler)
    """Перезапускает текущий скрипт."""
    python = sys.executable  # Путь к Python
    args = [python] + sys.argv  # Все аргументы командной строки
    try:
        # Создаём новый процесс
        GlobalFlags.interrupted = True
        logger.info("Restarting script...",
                    extra={'color': Fore.YELLOW})
        os.spawnv(os.P_WAIT, python, args)

    except KeyboardInterrupt:
        if not GlobalFlags.interrupted:  # Обрабатываем только один раз
            logger.warning("Restart interrupted by KeyboardInterrupt.")
            GlobalFlags.interrupted = True
        sys.exit(1)  # Завершаем текущий процесс с кодом ошибки
    except Exception as e:
        logger.error(f"Error during script restart: {e}")
        sys.exit(1)  # Завершаем текущий процесс с кодом ошибки
    finally:
        if not GlobalFlags.interrupted:
            logger.info("Exiting current process.")
        sys.exit(0)


def check_and_update(priority_task_queue, is_task_active):
    """
    Проверяет обновления и выполняет необходимые действия.
    """
    settings = load_settings()
    auto_update_enabled = settings.get("AUTO_UPDATE", "true").lower() == "true"

    try:
        if GitUpdater.is_git_installed() and GitUpdater.check_updates():
            logger.info("Git updates found. Performing update...")
            if GitUpdater.perform_update():
                logger.debug(
                    "Update successful. Stopping processes for restart...")
                stop_event.set()  # Останавливаем потоки
                stop_event.restart_mode = True
        else:
            updates_available, update_files = FileUpdater.check_updates()
            if updates_available:
                if auto_update_enabled:
                    logger.info("File updates found. Performing update...")
                    if FileUpdater.perform_update(
                        update_files, settings.get("REPOSITORY_URL")
                    ):
                        stop_event.set()  # Останавливаем потоки
                        stop_event.restart_mode = True
                else:
                    logger.info(
                        "Automatic updates are disabled. Updates available:")
                    for file in update_files:
                        logger.info(f" - {file}")
            else:
                logger.debug("No updates found.")

    except Exception as e:
        logger.error(f"Error during check_and_update: {e}")
