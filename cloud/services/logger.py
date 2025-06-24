import logging
import json

# Define ANSI escape sequences for colors
LOG_COLORS = {
    'DEBUG': "\033[94m",    # Blue
    'INFO': "\033[92m",     # Green
    'WARNING': "\033[93m",  # Yellow
    'ERROR': "\033[91m",    # Red
    'CRITICAL': "\033[95m", # Magenta
    'RESET': "\033[0m"      # Reset to default
}

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
        }
        return json.dumps(log_record)

class ColorFormatter(logging.Formatter):
    def format(self, record):
        log_color = LOG_COLORS.get(record.levelname, LOG_COLORS['RESET'])
        message = super().format(record)
        return f"{log_color}{message}{LOG_COLORS['RESET']}"
    
import os

class CustomLogger:
    def __init__(self, level=logging.DEBUG, name=__name__, log_dir=None):
        self.__logger = logging.getLogger(name)
        self.__logger.setLevel(level)
        self.__logger.propagate = False

        if not self.__logger.handlers:
            # Colored console output
            stream_handler = logging.StreamHandler()
            stream_formatter = ColorFormatter("%(asctime)s - %(levelname)s - %(message)s")
            stream_handler.setFormatter(stream_formatter)
            self.__logger.addHandler(stream_handler)

            # Log to file. Ensure log directory exists
            if log_dir is not None:
                os.makedirs(log_dir, exist_ok=True)
                file_path = os.path.join(log_dir, f"{name}.json.log")
                file_handler = logging.FileHandler(file_path)
                file_formatter = JsonFormatter()
                file_handler.setFormatter(file_formatter)
                self.__logger.addHandler(file_handler)

    def debug(self, msg):
        self.__logger.debug(msg)

    def log(self, msg):
        self.__logger.info(msg)

    def error(self, msg):
        self.__logger.error(msg)

    def exception(self, msg):
        self.__logger.exception(msg)

    def warning(self, msg):
        self.__logger.warning(msg)

    def critical(self, msg): 
        self.__logger.critical(msg)

    def reset(self):
        # Reset the logger to its initial state
        for handler in self.__logger.handlers[:]:
            self.__logger.removeHandler(handler)
        self.__logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = ColorFormatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        self.__logger.addHandler(handler)
        self.debug("Logger has been reset.")
