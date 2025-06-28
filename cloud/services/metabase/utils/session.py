from .req import Req

class Session(Req):
    def __init__(self, base_url):
        self.base_url = base_url
        self.active_token = None
        super().__init__(self.base_url)

    def create(self, username, password):
        data = {
            "username": username,
            "password": password
        }
        res = self.post("session", body=data).json()
        self.active_token = res.get("id")
        self.set_session_header(self.active_token)

    def close(self):
        self.delete("session")

    def set_session_header(self, data):
        self.add_header("X-Metabase-Session", data)
