import requests
from fastapi import APIRouter, Depends
from apis.connection import get_mb, logger as console, Session
from emails.email_service import EmailService
from .schema import SMTPSettings, EmailResponse

router = APIRouter(prefix="/metabase/email", tags=["Email"])

@router.put("/", response_model=EmailResponse)
async def setup_email(smtp_data: SMTPSettings, session: Session = Depends(get_mb)):
    async def __(email: EmailService):
        smtp_config = SMTPSettings(**smtp_data.model_dump(by_alias=True))
        return await email.setup(smtp_config)

    return await main(session, __)

async def main(session: Session, callback):
    try:
        email_service = EmailService(session, console)
        return await callback(email_service)
    
    except requests.exceptions.Timeout:
        console.exception("The request timed out")
    except requests.exceptions.ConnectionError as e:
        console.exception(f"Failed to connect to the server: {e}")
    except requests.exceptions.HTTPError as e:
        console.exception(f"HTTP error occurred: {e}")
        return {
            "error": True,
            "message": f"Ouch! There is something wrong with your request.",
            "status": e.response.status_code if e.response else 400,
            "reason": e.response.text if e.response else str(e),
        }
    except requests.exceptions.JSONDecodeError as e:
        console.exception(f"Response was not valid JSON. {e}")
    except requests.exceptions.RequestException as e:
        console.exception(f"An unexpected error occurred: {e}")
    except Exception as e:
        console.exception(f"Error occurred: {e}")
