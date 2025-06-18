from req import Req

class Session(Req):
    def __init__(self, base_url):
        self.base_url = base_url
        self.setup_token = None
        self.active_token = None
        super().__init__(self.base_url)

    def get_setup_token(self):
        path = "session/properties"
        res = self.get(path).json()
        self.setup_token = res.get("setup-token")
        return self.setup_token

    def create_session(self, username, password):
        data = {
            "username": username,
            "password": password
        }
        res = self.post("session", body=data).json()
        self.active_token = res.get("id")
        self.set_session_header(self.active_token)

    def set_session_header(self, data):
        self.add_header("X-Metabase-Session", data)
