import asyncio
import os
import shutil
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from middleware.auth import getUserInfo
from infra.logger import logger
from models.file import query_file
from models.task import Task, TaskStatus, create_task, update_task
from models.model import create_model, query_model, Model, update_model
from routes.common import CommonSchemaConfig
from utils.file import createDir

router = APIRouter(
    prefix="/train",
    include_in_schema=False,
)


def gen_output_dir(model: str, user_id: int, task_id: int):
    output_dir_path = os.path.join(
        "/data",
        "prod",
        str(user_id),
        model,
        "generated",
        str(task_id),
    )
    createDir(output_dir_path)
    return output_dir_path


class TrainAudioRequestBody(BaseModel):
    class Config(CommonSchemaConfig):
        pass

    model_name: str
    epoch: Optional[int] = 200
    file_ids: List[int]


async def train_request(
    body: TrainAudioRequestBody, task: Task, model: Model, ref_dir_name: str
):

    logger.debug("starting training request")

    response = requests.post(
        "http://127.0.0.1:3334/train?name="
        + body.model_name
        + "&ref_dir_name="
        + ref_dir_name
        + "&epoch="
        + str(body.epoch)
    )

    if not response.ok:
        await update_task(task.id, status=TaskStatus.FAILED)

    logger.info("train completed")

    await update_model(model.id, audio_model=body.model_name + ".pth")
    await update_task(task.id, status=TaskStatus.SUCCEEDED)


def wrapped_train_request(
    body: TrainAudioRequestBody, task: Task, model: Model, ref_dir_name: str
):
    asyncio.run(train_request(body, task, model, ref_dir_name))


def run_async_in_thread(task):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(task)
    loop.close()


@router.post("/audio_model")
async def train_audio_model(
    req: Request,
    body: TrainAudioRequestBody,
):
    user = getUserInfo(req)

    models = await query_model(name=body.model_name)

    task = await create_task()
    model = None
    if len(models) == 0:
        model = await create_model(name=body.model_name)
    else:
        model = models[0]

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

    # update task status after request completed
    asyncio.create_task(train_request(body, task, model, ref_dir_name))

    return JSONResponse(
        {
            "task_id": task.id,
        }
    )

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

    task = await create_task()
    model = None
    if len(models) == 0:
        model = await create_model(name=body.model_name)
    else:
        model = models[0]

    await update_model(model.id, video_model=body.speaker)

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

    # query request
    response = requests.post(
        "http://0.0.0.0:8000/talking-head/train",
        json={
            "speaker": body.speaker,
            "callback_url": f"http://0.0.0.0:3333/internal/task/{task.id}",
            "callback_method": "put",
        },
        headers={"Content-Type": "application/json"},
    )

    if not response.ok:
        raise HTTPException(status_code=response.status_code,
                            detail=response.json())

    logger.debug(f"response code: {response.status_code}")

    return JSONResponse(
        {
            "task_id": task.id,
        }
    )
