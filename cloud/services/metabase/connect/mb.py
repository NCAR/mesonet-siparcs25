import requests
from logger import CustomLogger
from utils.session import Session

class MetabaseConnection:
    def __init__(self, session: Session, logger: CustomLogger, db_name: str, db_payload: dict):
        self.session = session
        self.db_name = db_name
        self.db_payload = db_payload
        self.console = logger
        self.console.debug(f"Initializing metabase connection with name: {db_name}")

    def _can_connect(self):
        res = self.session.get("health").json()
        if res.get("status") == "ok":
            return True
        return False

    def _validate_db(self):
        db_id = None
        res = self.session.get("database")

        if res is not None and res.status_code == 200:
            existing_dbs = res.json().get("data")
            for db in existing_dbs:
                if db.get("name") == self.db_name:
                    db_id = db.get("id")
                    break
    
        return db_id
    
    def _connect(self, username, password) -> int:
        healthy_con = self._can_connect()
        db_id = None

        if healthy_con:
            self.session.create_session(username, password)
            db_id = self._validate_db()

            if db_id is None:
                res = self.session.post("database", body=self.db_payload)

                if res.status_code == 200:
                    self.console.log("Database added to Metabase!")
                else:
                    self.console.log(f"Failed: {res.text} to authenticate user")
        else:
            raise requests.exceptions.ConnectionError("Metabase is not ready yet!")
        
        return db_id