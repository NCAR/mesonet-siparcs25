import os
import psycopg2
from utils.config import Config
from .mb import MetabaseConnection as Meta
from users.user_services import UserServices

class MetabaseService(Meta):
    def __init__(self, session, logger, db_name, db_payload):
        super().__init__(session, logger, db_name, db_payload)
        self.user = UserServices(self.session, logger)

    def connect(self, admin, config: Config) -> int:
        # Setup token is created just once. i.e. when there is no user
        cached_token = self.user.get_cached_setup_token()
        settings_token = self.__get_settings_setup_token()

        if cached_token and settings_token:
            # Create new admin else admin already exists
            self.console.log("Creating an Admin ...")
            admin_token = self.user.setup_initial_user(cached_token, admin, config)

            if admin_token:
                self.__clear_settings_setup_token()

        # Now login and connect databases
        self.console.log(f"Connecting to Metabase database: {self.db_name}")
        return self._connect(admin.get("email"), admin.get("password"))
    
    def disconnect(self):
        self.session.close()
    
    def __clear_settings_setup_token(self):
        console = self.console
        try:
            query = "DELETE FROM setting WHERE key = 'setup-token';"
            self._mb_delete(query)
            console.warning("Setup token deleted successfully.")
        except Exception as e:
            console.error(f"Error deleting setup token: {e}")
        finally:
            self._mb_close()

    def __get_settings_setup_token(self):
        console = self.console
        try:
            query = "SELECT value FROM setting WHERE key = 'setup-token';"
            token = self._mb_get(query)
            if token and token[0]:
                console.warning(f"Setup token retrieved successfully: {token[0]}")
                return token[0]
            else:
                console.log("No setup token found. Metabase may already be initialized.")
                return None
        except Exception as e:
            console.error(f"Error retrieving setup token: {e}")
            return None
        finally:
            self._mb_close()





