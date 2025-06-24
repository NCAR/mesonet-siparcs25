import requests
from logger import CustomLogger
from utils.session import Session

class ConnectDB:
    def __init__(self, session: Session, logger: CustomLogger, db_name: str):
        self.session = session
        self.db_name = db_name
        self.console = logger
        self.console.debug(f"Initializing metabase connection with name: {db_name}")

    def __can_connect(self):
        res = self.session.get("health").json()
        if res.get("status") == "ok":
            return True
        return False

    def validate_db(self):
        db_id = None
        res = self.session.get("database")

        if res is not None and res.status_code == 200:
            existing_dbs = res.json().get("data")
            for db in existing_dbs:
                if db.get("name") == self.db_name:
                    db_id = db.get("id")
                    self.console.log(f"Database '{self.db_name}' already exists in metabase (id={db.get('id')})")
                    break
    
        return db_id

    def connect(self, username, password, db_payload):
        healthy_con = self.__can_connect()

        if healthy_con:
            self.session.create_session(username, password)
            db_id = self.validate_db()

            if db_id is None:
                res = self.session.post("database", body=db_payload)

                if res.status_code == 200:
                    self.console.log("Database added to Metabase!")
                else:
                    self.console.log(f"Failed: {res.text} to authenticate user")
        else:
            raise requests.exceptions.ConnectionError("Metabase is not ready yet!")
