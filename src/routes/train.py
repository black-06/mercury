import os
import shutil
from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from middleware.auth import getUserInfo
from models.file import query_file
from models.model import create_model, query_model, update_model
from routes.common import CommonSchemaConfig
from task.infer import celery_enabled
from task.train import publish_audio_train_task, publish_video_train_task
from task.train_http import train_audio_queue, TrainAudioTask, train_video_queue, TrainVideoTask
from utils.file import createDir

router = APIRouter(
    prefix="/train",
    include_in_schema=False,
)


class TrainAudioRequestBody(BaseModel):
    class Config(CommonSchemaConfig):
        pass

    model_name: str
    epoch: Optional[int] = 200
    file_ids: List[int]


@router.post("/audio_model")
async def train_audio_model(
    req: Request,
    body: TrainAudioRequestBody,
):
    user = getUserInfo(req)

    models = await query_model(name=body.model_name)
    if len(models) == 0:
        model = await create_model(name=body.model_name)
    else:
        model = models[0]
    await update_model(model.id, audio_model=body.model_name + ".pth")

    if celery_enabled:
        rst = publish_audio_train_task([str(fid) for fid in body.file_ids], body.model_name, body.epoch)
        return JSONResponse({"task_id": rst.id})

    ref_dir_name = os.path.join(
        "/home/ubuntu/Projects/Retrieval-based-Voice-Conversion-WebUI/reference",
        body.model_name,
    )

    # delete ref_dir_name
    shutil.rmtree(ref_dir_name, ignore_errors=True)

    createDir(ref_dir_name)

    for file_id in body.file_ids:
        file = await query_file(file_id)
        file_name = os.path.basename(file.path)
        new_file_path = os.path.join(ref_dir_name, file_name)
        shutil.copy(file.path, new_file_path)

    task = await train_audio_queue.append(TrainAudioTask(body.model_name, ref_dir_name, body.epoch).to_json())

    return JSONResponse({"task_id": task.id})


class TrainVideoRequestBody(BaseModel):
    class Config(CommonSchemaConfig):
        pass

    model_name: str
    speaker: str
    file_ids: List[int]


@router.post("/video_model")
async def train_video_model(
    req: Request,
    body: TrainVideoRequestBody,
):
    user = getUserInfo(req)

    models = await query_model(name=body.model_name)
    if len(models) == 0:
        model = await create_model(name=body.model_name)
    else:
        model = models[0]
    await update_model(model.id, video_model=body.speaker)

    if celery_enabled:
        rst = publish_video_train_task([str(fid) for fid in body.file_ids], body.speaker)
        return JSONResponse({"task_id": rst.id})

    ref_dir_name = os.path.join(
        "/home/chaiyujin/talking-head-v0.1/user-data/clip",
        body.speaker,
    )

    # delete ref_dir_name
    shutil.rmtree(ref_dir_name, ignore_errors=True)

    createDir(ref_dir_name)

    count = 0

    for file_id in body.file_ids:
        file = await query_file(file_id)
        file_name = str(count).zfill(2) + ".mp4"
        new_file_path = os.path.join(ref_dir_name, file_name)
        shutil.copy(file.path, new_file_path)
        count = count + 1

    task = await train_video_queue.append(TrainVideoTask(body.speaker).to_json())

    return JSONResponse({"task_id": task.id})
