from utils import utils_ftn
from logger import CustomLogger

class MetabaseUsers:
    def __init__(self, logger: CustomLogger, url):
        self.console = logger
        self.url = url

    async def get(self, path: str):
        res = await utils_ftn.get_all(path=path)
        self.console.log(res)