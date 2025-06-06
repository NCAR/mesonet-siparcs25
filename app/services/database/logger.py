import logging

class CustomLogger:
    def __init__(self, level=logging.DEBUG, name=__name__):
        self.__logger = logging.getLogger(name)
        handler = logging.StreamHandler()
        self.__logger.addHandler(handler)
        self.__logger.setLevel(logging.DEBUG)

    def debug(self, msg):
        self.__logger.debug(msg)

    def log(self, msg):
        self.__logger.info(msg)

    def error(self, msg):
        self.__logger.error(msg)

    def exception(self, msg):
        self.__logger.exception(msg)