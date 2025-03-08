import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
LOG_FILE_DIR = Path.joinpath(Path(__file__).parents[1], "documents", "logs")
DOCKER_VOLUME_DIR = os.getenv("LOG_FOLDER_PATH")


def custom_file_handler():
    dir = f'{DOCKER_VOLUME_DIR}{datetime.now().strftime("%y%m%d")}'
    if not os.path.exists(dir):
        os.makedirs(dir)

    file_path = f'{dir}/ke_llm.log'
    format_log = '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s'

    logger = logging.getLogger("ke_log")
    logger.setLevel(logging.INFO)

    # File handler
    file_handler = logging.FileHandler(filename=file_path, encoding='utf-8')
    file_formatter = logging.Formatter(fmt=format_log, style='%')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(file_formatter)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(fmt=format_log, style='%'))
    logger.addHandler(console_handler)

    logger.debug("logger is started")
