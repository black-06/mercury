import asyncio
import os
import shutil
from typing import List, Optional
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from common.task_queue import RQueue
from models.task import TaskStatus
from pydantic import BaseModel
import requests
from middleware.auth import getUserInfo
from infra.logger import logger
from models.file import query_file
from models.model import create_model, query_model, update_model
from routes.common import CommonSchemaConfig
from utils.file import createDir

TRAIN_AUDIO_KEY = "TRAIN_AUDIO"
TRAIN_VIDEO_KEY = "TRAIN_VIDEO"

class TrainAudioTask():
    def __init__(self, model_name: str, ref_dir_name: str, epoch: int):
        self.model_name = model_name
        self.ref_dir_name = ref_dir_name
        self.epoch = epoch

async def train_audio_task_handler(task_id: int, task: TrainAudioTask) -> None:
    await slice_for_cosy_voice(task.model_name, task_id,task.ref_dir_name)
    await train_rvc(task.model_name, task_id, task.epoch, task.ref_dir_name)

class TrainVideoTask():
    def __init__(self, speaker: str):
        self.speaker = speaker

async def train_video_task_handler(task_id: int, task: TrainVideoTask) -> TaskStatus:
    # talking-head是否存在正在进行的任务
    response = requests.get("http://0.0.0.0:8000/talking-head/train-ready")
    if not response.ok:
        raise Exception(f"talking-head response error, code: {response.status_code}")
    if not response.json().get("ready", False):
        raise Exception("talking-head is not ready")

    # taking-head start train
    response = requests.post(
        "http://0.0.0.0:8000/talking-head/train",
        json={
            "speaker": task.speaker,
            "callback_url": f"http://0.0.0.0:3333/internal/task/{task_id}",
            "callback_method": "put",
        },
        headers={"Content-Type": "application/json"},
    )
    if not response.ok:
        raise Exception(f"talking-head response error, code: {response.status_code}")
    # 视频训练的状态通过回调接口更新
    return TaskStatus.PENDING
        
train_audio_queue = RQueue(
    TRAIN_AUDIO_KEY,
    handler=train_audio_task_handler, 
    handle_sleep=60 * 2, 
    retry_sleep=60
)
train_video_queue = RQueue(
    TRAIN_VIDEO_KEY, 
    handler=train_video_task_handler, 
    handle_sleep=60 * 20, 
    retry_sleep=60 * 5
)


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

# 切分音频作为 cosyvoice 参考音频
async def slice_for_cosy_voice(model_name: str, task_id: int, ref_dir_name: str):
    output_dir_name = os.path.join(
        "/home/ubuntu/Projects/CosyVoice/mercury_workspace",
        model_name,
    )
    createDir(output_dir_name)
    
    response = requests.post(
        "http://0.0.0.0:3336/audio/slice_audio",
        json={
            "audio_file": ref_dir_name,
            "output_dir": output_dir_name,
            "min_length": 8,
            "max_length": 12,
            "keep_silent": 0.5,
            "sliding_slice": False
        },
        headers={"Content-Type": "application/json"},
    )
    
    if not response.ok:
        raise Exception("slice audio failed, code: {response.status_code}")
    
# 训练rvc模型
async def train_rvc(model_name: str, task_id: int, model_id: int, ref_dir_name: str, epoch: int):
    response = requests.post(
        "http://127.0.0.1:3334/train?name="
        + model_name
        + "&ref_dir_name="
        + ref_dir_name
        + "&epoch="
        + str(epoch)
    )

    if not response.ok:
        raise Exception("response error, code: {response.status_code}")

@router.post("/audio_model")
async def train_audio_model(
    req: Request,
    body: TrainAudioRequestBody,
):
    user = getUserInfo(req)
    
    models = await query_model(name=task.model_name)
    model = None
    if len(models) == 0:
        model = await create_model(name=task.model_name)
    else:
        model = models[0]
    await update_model(model.id, audio_model=task.model_name + ".pth")

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
        
    task = train_audio_queue.append(TrainAudioTask(body.model_name, ref_dir_name, body.epoch))

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

    task = await train_video_queue.append(TrainVideoTask(body.speaker))

    return JSONResponse(
        {
            "task_id": task.id,
        }
    )
