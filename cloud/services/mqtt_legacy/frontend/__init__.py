from logger import CustomLogger
from typing import Any

'''
    This class is for managing the metabase frontend at real-time.
        1. Dashbaords
        2. Models
        3. Cards
        4. Collections
'''

class FrontendService:
    def __init__(self, logger: CustomLogger, mb_url: str):
        self.console = logger
        self.mb_url = mb_url

    def manage(self) -> Any:
        pass