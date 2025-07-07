from apis.emails.types import SMTPSettings
from logger import CustomLogger
from utils.session import Session
from utils.odm import ODM

class EmailService(ODM):
    def __init__(self, session: Session, logger: CustomLogger):
        super().__init__(session)
        self.console = logger

    async def setup(self, smtp_data: SMTPSettings):
        console = self.console
        console.debug(smtp_data)
        smtp_settings = {
            "email-smtp-host": smtp_data.host,
            "email-smtp-port": "587",
            "email-smtp-security": "starttls",
            "email-smtp-username": "oppongbaahisaacmega@gmail.com",
            "email-smtp-password": "umjsopibixmaqtbr",
            "email-from-address": "isaacob@ncar.edu",
            "email-from-name": "NCAR Metabase"
        }

        res_data = await self.update_async(path="email", data=smtp_settings)
        console.debug(res_data)

        return res_data
