import requests
from logger import CustomLogger
from utils.session import Session
from .mb_db import MetabaseDB as MetaDB

class MetabaseConnection(MetaDB):
    def __init__(self, session: Session, logger: CustomLogger, db_name: str, db_payload: dict):
        super().__init__()
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
    
    def _connect_db(self, username, password) -> int:
        healthy_con = self._can_connect()
        db_id = None

        if healthy_con:
            self.session.create(username, password)
            db_id = self._validate_db()

            if db_id is None:
                res = self.session.post("database", body=self.db_payload)

                if res.status_code == 200:
                    db_id = res.json().get("id")
                    self.console.log("Database added to Metabase!")
                else:
                    self.console.log(f"Failed: {res.text} to authenticate user")
        else:
            raise requests.exceptions.ConnectionError("Metabase is not ready yet!")

        return db_id
    
    def _setup_email(self, smtp_settings):
        console = self.console
        res = self.session.put(path="email", body=smtp_settings)

        if res.status_code == 200:
            console.log(f"Email settings for {smtp_settings.get('email-smtp-username')} have been successfully setup.")
        else:
            raise requests.exceptions.HTTPError("Problem setting up the email in metabase.")
        
    def _change_site_url(self, payload: dict) -> None :
        console = self.console
        res = self.session.put(path="setting/site-url", body=payload)

        if res.status_code == 204:
            console.log(f"Site URL is changed to {payload.get('value')}.")
        else:
            raise requests.exceptions.HTTPError("Problem setting up the email in metabase.")