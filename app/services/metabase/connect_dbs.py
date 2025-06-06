from logger import CustomLogger
import requests

console = CustomLogger()

class ConnectDB:
    def __init__(self, db_name, session):
        self.session = session
        self.db_name = db_name

    def __can_connect(self):
        res = self.session.get("health").json()
        if res.get("status") == "ok":
            return True
        return False

    def __check_for_db_existence(self):
        db_exist = False
        res = self.session.get("database")

        if res is not None and res.status_code == 200:
            existing_dbs = res.json().get("data")
            for db in existing_dbs:
                if db.get("name") == self.db_name:
                    db_exist = True
                    console.log(f"Database '{self.db_name}' already exists in metabase (id={db.get('id')})")
                    break
    
        return db_exist

    def connect(self, username, password, db_payload):
        healthy_con = self.__can_connect()

        if healthy_con:
            self.session.create_session(username, password)
            db_exist = self.__check_for_db_existence()

            if not db_exist:
                res = self.session.post("database", body=db_payload)

                if res.status_code == 200:
                    console.log("Database added to Metabase!")
                else:
                    console.log(f"Failed: {res.text} to authenticate user")
        else:
            raise requests.exceptions.ConnectionError("Metabase is not ready yet!")
