import requests
from .mb import MetabaseConnection as Meta
from users.user import User

class MetabaseService(Meta):
    def __init__(self, session, logger, db_name, db_payload):
        super().__init__(session, logger, db_name, db_payload)
        self.user = User(self.session, logger)

    def connect(self, admin, config) -> int:
        # Setup token is created just once. i.e. when there is no user
        setup_token = self.user.get_setup_token()

        if setup_token is not None:
            # Create new admin else admin already exists
            self.console.log("Authenticating the Admin ...")
            self.user.setup_initial_user(setup_token, admin, config)

        # Now login and connect databases
        self.console.log(f"Connecting to Metabase database: {self.db_name}")
        return self._connect(admin.get("email"), admin.get("password"))


