import requests
from fastapi import APIRouter, Depends
from typing import Any, Optional
from apis.connection import Session, get_mb, logger as console
from collections_.collection_services import CollectionServices
from .schema import CollectionCreate, CollectionRes

router = APIRouter(prefix="/metabase", tags=["Collections"])

@router.post("/parent/collection/", response_model=Optional[CollectionRes])
async def create_parent_collections(data: CollectionCreate, session: Session = Depends(get_mb)):
    async def __(collection: CollectionServices):
        return await collection.create_parent_collection_async(data)
    
    return await main(session, __)

async def main(session: Session, callback):
    try:
        collection_service = CollectionServices(session, console, db_id=0)
        return await callback(collection_service)
    
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
