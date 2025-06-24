from logger import CustomLogger
from utils.session import Session

class User:
    def __init__(self, session: Session, logger: CustomLogger):
        self.session = session
        self.console = logger
        self.console.debug("Initializing User management")

    def get_setup_token(self):
        return self.session.get_setup_token()

    def setup_initial_user(self, setup_token, user_data, prefs):
        path = "setup"
        body = {
            "token": setup_token,
            "user": user_data,
            "prefs": prefs
        }
        res = self.session.post(path, body)

        if res.status_code == 200:
            self.console.log(f"Admin created and login sucessfully")   
