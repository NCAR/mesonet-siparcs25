from typing import List, cast
import requests
from fastapi import APIRouter, Depends, HTTPException
from utils.session import Session
from apis.connection import get_mb, logger as console
from groups.group_services import GroupServices
from .schema import GroupCreate, GroupResponse, Membership, MembershipRes, APIResponse

router = APIRouter(prefix="/metabase", tags=["Groups"])

@router.get("/group", response_model=List[GroupResponse])
async def add_group(session: Session = Depends(get_mb)):
    async def __(group: GroupServices):
        path = "permissions/group"
        return await group.get_all(path)
    return await main(session, __)

@router.post("/group", response_model=GroupResponse | dict)
async def add_group(data: GroupCreate, session: Session = Depends(get_mb)):
    async def __(group: GroupServices):
        path = "permissions/group"
        body = GroupCreate(**data.model_dump(by_alias=True))
        group = await group.create(path, body)

        if not group:
            return cast(dict, group)
        
        return cast(GroupResponse, group)

    return await main(session, __)

@router.post("/membership", response_model=APIResponse[MembershipRes | dict])
async def add_member(data: Membership, session: Session = Depends(get_mb)):
    async def __(group: GroupServices):
        path = "permissions/membership"
        group = await group.membership(path, data)

        if not group:
            return cast(APIResponse[dict], group)
        
        return cast(APIResponse[MembershipRes], group)

    return await main(session, __)

async def main(session: Session, callback):
    try:
        group_name = "ncar"
        email_service = GroupServices(session, console, name=group_name)
        return await callback(email_service)
    
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
    except Exception as e:
        console.exception(f"Error occurred: {e}")
