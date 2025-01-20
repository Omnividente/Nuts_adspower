
# Telegram Bot Automation for NUTS


## Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Support](#support)

## Features
- Automatic browser launches via AdsPower.
- Game actions: check-ins, game launches, and bonus collection.
- Script updates and automatic update handling.

---

## Installation

1. Ensure the account is logged into [web.telegram.org](https://web.telegram.org/).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration

| **Setting**             | **Description**                                                                                                        | **Example**                                     |
|-------------------------|-------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------|
| **TELEGRAM_GROUP_URL**  | Link to your channel or chat where the bot will look for your referral link to start.                                   | `https://t.me/CryptoProjects_sbt`              |
| **BOT_LINK**            | Referral link.                                                                                                         | `Full Ref Link`    |
| **MAX_GAMES**           | Maximum number of games per session (0 - disabled, empty value plays all available games).                             | `10`                                            |
| **ACCOUNTS**            | Account numbers to process (list of numbers and ranges).                                                              | `1,2,5-7`                                       |
| **REPOSITORY_URL**      | Repository URL for update checking.                                                                                    | `https://github.com/Omnividente/nuts_adspower` |
| **UPDATE_INTERVAL**     | Update check interval in seconds.                                                                                      | `10800`                                         |
| **AUTO_UPDATE**         | (true/false) Enable or disable automatic updates.                                                                      | `true`                                          |
| **FILES_TO_UPDATE**     | List of files to check for updates. Defaults to `remote_files_for_update` in the repository.                           | `main.py, utils.py`                             |

## Working with Accounts

The script processes accounts from three sources in the following order of priority:

1. **`accounts` parameter in the `settings.txt` file:**
   - Format: a list of accounts separated by commas, with support for ranges.
   - Example: `accounts=1, 2, 5-7, 10`.

2. **`accounts.txt` file:**
   - One account per line.
   - Used if the `accounts` parameter in the `settings.txt` is missing or empty.

3. **Profiles from the local AdsPower API:**
   - Used if both of the above sources are missing or empty.
   - Processes all available profiles.

---

## Usage

Run the script:
```bash
cd path/to/script
python main.py
```

Run options:
```
usage: main.py [-h] [--debug] [--account ACCOUNT] [--visible {0,1}]
Run the script with optional debug logging.
options:
  -h, --help         Show this help message and exit
  --debug            Enable debug logging
  --account ACCOUNT  Force processing a specific account
  --visible {0,1}    Set visible mode (1 for visible, 0 for headless)
```

---

## Support

For any questions or issues, contact [here](https://t.me/cryptoprojectssbt).
