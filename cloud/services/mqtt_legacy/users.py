from utils import utils_ftn
from logger import CustomLogger

class MetabaseUsers:
    def __init__(self, logger: CustomLogger, base_url: str):
        self.console = logger
        self.base_url = base_url

    async def get(self, path: str):
        url = f"{self.base_url}/{path}"
        url = url if url.endswith('/') else url + '/'
        return await utils_ftn.get_all(url)
    
    async def add(self, path: str, payload):
        url = f"{self.base_url}/{path}"
        url = url if url.endswith('/') else url + '/'
        return await utils_ftn.insert(path, payload)
