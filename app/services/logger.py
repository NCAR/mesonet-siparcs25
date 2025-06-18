import logging

class CustomLogger:
    def __init__(self, level=logging.DEBUG, name=__name__):
        self.__logger = logging.getLogger(name)
        self.__logger.setLevel(level)

        # Prevent adding multiple handlers
        if not self.__logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.__logger.addHandler(handler)

    def debug(self, msg):
        self.__logger.debug(msg)

    def log(self, msg):
        self.__logger.info(msg)

    def error(self, msg):
        self.__logger.error(msg)

    def exception(self, msg):
        self.__logger.exception(msg)
