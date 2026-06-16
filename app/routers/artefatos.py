"""Artifacts router - stub for backward compatibility."""
from fastapi import APIRouter

router = APIRouter(prefix="/artefatos", tags=["Artefatos"])


@router.get("/")
async def listar_artefatos():
    return {"artefatos": []}
