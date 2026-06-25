from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ErrorLogCreate(BaseModel):
    message: str
    status: Optional[int] = None
    url: Optional[str] = None
    stack: Optional[str] = None
    user_id: Optional[str] = None

class ErrorLogResponse(ErrorLogCreate):
    id: str
    timestamp: datetime

    model_config = {
        "from_attributes": True
    }
