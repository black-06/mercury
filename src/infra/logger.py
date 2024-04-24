import logging
from logging import getLogger, StreamHandler, Formatter, DEBUG
import sys

# from logging.config import dictConfig

# dictConfig()
logger = logging.getLogger("mercury")
logger.setLevel(DEBUG)

# Create a StreamHandler to log to stdout and stderr
stdout_handler = StreamHandler(sys.stdout)
stderr_handler = StreamHandler(sys.stderr)

# Set the formatter for the handlers
formatter = Formatter('%(asctime)s %(levelname)s: %(message)s')
stdout_handler.setFormatter(formatter)
stderr_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(stdout_handler)
logger.addHandler(stderr_handler)