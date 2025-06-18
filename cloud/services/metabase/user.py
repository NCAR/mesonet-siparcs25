from logger import CustomLogger

console = CustomLogger()

class User:
    def __init__(self, session):
        self.session = session

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
            console.log(f"Admin created and login sucessfully")   
