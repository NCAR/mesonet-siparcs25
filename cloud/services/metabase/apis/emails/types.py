from pydantic import BaseModel, EmailStr, Field
from typing import Dict, Optional

class SMTPSettings(BaseModel):
    host: str = Field(..., alias="email-smtp-host")
    username: EmailStr = Field(..., alias="email-smtp-username")
    password: str = Field(..., alias="email-smtp-password")
    port: int = Field(..., alias="email-smtp-port")
    security: str = Field(..., alias="email-smtp-security")  # e.g., 'starttls' or 'ssl'
    from_name: str = Field(..., alias="email-from-name")
    from_address: EmailStr = Field(..., alias="email-from-address")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }

class EmailResponse(SMTPSettings):
    with_corrections: Optional[Dict] = Field(default_factory=dict, alias="with-corrections")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }
