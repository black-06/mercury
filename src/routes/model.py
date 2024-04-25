from typing import Optional, Union
from fastapi import APIRouter
from pydantic import BaseModel
import models.model as modelModel
from infra.logger import logger


router = APIRouter(
    prefix="/models",
)


@router.get("")
async def get_models(model_id: Optional[int] = None, model_name: Optional[str] = None):
    res = await modelModel.query_model(name=model_name, model_id=model_id)
    return res


class CreateModelReqBody(BaseModel):
    name: str
    audio_model: str
    video_model: str


@router.post("")
async def create_model(body: CreateModelReqBody):
    return await modelModel.create_model(
        name=body.name, audio_model=body.audio_model, video_model=body.video_model
    )


class UpdateModelReqBody(BaseModel):
    name: str
    audio_model: str
    video_model: str


@router.put("/{model_id}")
async def update_model(model_id: int, body: UpdateModelReqBody):
    return await modelModel.update_model(
        model_id,
        name=body.name,
        audio_model=body.audio_model,
        video_model=body.video_model,
    )


@router.delete("/{model_id}")
async def update_model(model_id: int):
    return await modelModel.delete_model(model_id)
