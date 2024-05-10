import os
from typing import List, Optional
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from infra.file import WORKSPACE
import models.model as modelModel
import models.file as fileModel
from infra.logger import logger


router = APIRouter(
    prefix="/models",
)


@router.get("", response_model=List[modelModel.Model])
async def get_models(model_id: Optional[int] = None, model_name: Optional[str] = None):
    res = await modelModel.query_model(name=model_name, model_id=model_id)
    return res


class CreateModelReqBody(BaseModel):
    name: str
    audio_model: str
    video_model: str


@router.post("", response_model=modelModel.Model)
async def create_model(body: CreateModelReqBody):
    return await modelModel.create_model(
        name=body.name, audio_model=body.audio_model, video_model=body.video_model
    )


class UpdateModelReqBody(BaseModel):
    name: str
    audio_model: str
    video_model: str


@router.put("/{model_id}", response_model=modelModel.Model)
async def update_model(model_id: int, body: UpdateModelReqBody):
    return await modelModel.update_model(
        model_id,
        name=body.name,
        audio_model=body.audio_model,
        video_model=body.video_model,
    )


@router.delete("/{model_id}", response_model=int)
async def delete_model(model_id: int):
    return await modelModel.delete_model(model_id)


class ImageResponse(Response):
    media_type = "image/*"
    schema = {}


@router.get("/preview_image", response_class=ImageResponse)
async def get_preview_image(
    model_id: Optional[int] = None, model_name: Optional[str] = None
):
    res = await modelModel.query_model(name=model_name, model_id=model_id)
    model = res[0]
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    logger.debug(model.video_config)

    if "preview_image_id" not in model.video_config:
        raise HTTPException(
            status_code=404, detail="preview_image_id not found")

    file_id = model.video_config["preview_image_id"]

    file = await fileModel.query_file(file_id)

    if file is None:
        raise HTTPException(status_code=404, detail="File not found")

    base_name = os.path.basename(file.path)
    encoded_basename = quote(base_name)

    return FileResponse(
        os.path.join(WORKSPACE, file.path),
        filename=encoded_basename,
    )
