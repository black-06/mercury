import logging
import sys

class ColoredFormatter(logging.Formatter):
    COLOR_CODE = {
        logging.DEBUG: "\033[94m",  # Blue
        logging.INFO: "\033[92m",   # Green
        logging.WARNING: "\033[93m",  # Yellow
        logging.ERROR: "\033[91m",  # Red
        logging.CRITICAL: "\033[95m",  # Magenta
    }
    RESET_CODE = "\033[0m"

    def format(self, record):
        color = self.COLOR_CODE.get(record.levelno)
        message = super().format(record)
        return f"{color}{message}{self.RESET_CODE}"

logger = logging.getLogger("mercury")
logger.setLevel(logging.DEBUG)

stdout_handler = logging.StreamHandler(sys.stdout)

formatter = ColoredFormatter("%(asctime)s %(levelname)s: %(message)s")

stdout_handler.setFormatter(formatter)

logger.addHandler(stdout_handler)
