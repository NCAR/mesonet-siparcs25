from apis.emails.types import SMTPSettings
from logger import CustomLogger
from utils.session import Session
from utils.odm import ODM
from utils.payload import Payload

class EmailService(ODM):
    def __init__(self, session: Session, logger: CustomLogger):
        super().__init__(session)
        self.console = logger

    async def setup(self, smtp_data: SMTPSettings):
        console = self.console
        smtp_settings = Payload() \
            .reset() \
            .set_attr("email-smtp-host", smtp_data.host) \
            .set_attr("email-smtp-port", smtp_data.port) \
            .set_attr("email-smtp-security", smtp_data.security) \
            .set_attr("email-smtp-username", smtp_data.username) \
            .set_attr("email-smtp-password", smtp_data.password) \
            .set_attr("email-from-address", smtp_data.from_address) \
            .set_attr("email-from-name", smtp_data.from_name) \
            .build()

        res_data = await self.update_async(path="email", data=smtp_settings)
        if res_data:
            console.log(f"SMTP Email has been setup successfully for {smtp_data.username}.")

        return res_data
