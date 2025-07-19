import requests
from .req import Req
from logger import CustomLogger

class Session(Req):
    def __init__(self, logger: CustomLogger, base_url):
        self.console = logger
        self.base_url = base_url
        self.active_token = None
        super().__init__(self.base_url)

    def create(self, username, password):
        console = self.console
        data = {
            "username": username,
            "password": password
        }
        res = self.post("session", body=data)

        if not (200 <= res.status_code < 300):
            console.error(f"Login failed: {res.text}")
            raise requests.exceptions.HTTPError(res.text)
            
        self.active_token = res.json().get("id")
        self.set_session_header(self.active_token)

    def close(self):
        self.delete("session")

    def set_session_header(self, data):
        self.add_header("X-Metabase-Session", data)
