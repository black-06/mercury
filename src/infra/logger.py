import logging
import sys

logger = logging.getLogger("mercury")
logger.setLevel(logging.DEBUG)

stdout_handler = logging.StreamHandler(sys.stdout)

formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

stdout_handler.setFormatter(formatter)

logger.addHandler(stdout_handler)
