import asyncio
import json
import os
import shutil
import httpx
from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from common.task_queue import TaskQueue
from models.task import TaskStatus
from pydantic import BaseModel
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
    def tostring(self):
        return json.dumps(self.__dict__)

async def train_audio_task_handler(task_id: int, task_str: str) -> None:
    task = TrainAudioTask(**json.loads(task_str))
    await slice_for_cosy_voice(task.model_name, task_id,task.ref_dir_name)
    await train_rvc(task.model_name, task.ref_dir_name, task.epoch, )

class TrainVideoTask():
    def __init__(self, speaker: str):
        self.speaker = speaker
    def tostring(self):
        return json.dumps(self.__dict__)

async def train_video_task_handler(task_id: int, task_str: str) -> TaskStatus:
    task = TrainVideoTask(**json.loads(task_str))
    # talking-head是否存在正在进行的任务
    while True:
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.get("http://0.0.0.0:8000/talking-head/train-ready")
        if response.status_code != 200:
            raise Exception(f"status_code {response.status_code}, {response.json()}")
        if response.json().get("ready", False):
            break
        await asyncio.sleep(5)

    # taking-head start train
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://0.0.0.0:8000/talking-head/train",
            json={
                "speaker": task.speaker,
                "callback_url": f"http://0.0.0.0:3333/internal/task/{task_id}",
                "callback_method": "put",
            },
        )
    if not response.status_code == 200:
        raise Exception(f"talking-head response error, code: {response.status_code}")
    # 视频训练的状态通过回调接口更新
    return TaskStatus.PENDING
        
train_audio_queue = TaskQueue(
    TRAIN_AUDIO_KEY,
    handler=train_audio_task_handler, 
)
train_video_queue = TaskQueue(
    TRAIN_VIDEO_KEY, 
    handler=train_video_task_handler, 
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
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://0.0.0.0:3336/audio/slice_audio",
            json={
                "audio_file": ref_dir_name,
                "output_dir": output_dir_name,
                "min_length": 8,
                "max_length": 12,
                "keep_silent": 0.5,
                "sliding_slice": False
            },
        )
    
    if not response.status_code == 200:
        raise Exception(f"slice audio failed, code: {response.status_code}")
    
# 训练rvc模型
async def train_rvc(model_name: str, ref_dir_name: str, epoch: int):
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://127.0.0.1:3334/train?name="
            + model_name
            + "&ref_dir_name="
            + ref_dir_name
            + "&epoch="
            + str(epoch)
        )

    if not response.status_code == 200:
        raise Exception(f"response error, code: {response.status_code}")

@router.post("/audio_model")
async def train_audio_model(
    req: Request,
    body: TrainAudioRequestBody,
):
    user = getUserInfo(req)
    
    models = await query_model(name=body.model_name)
    model = None
    if len(models) == 0:
        model = await create_model(name=body.model_name)
    else:
        model = models[0]
    await update_model(model.id, audio_model=body.model_name + ".pth")

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
        

    task = await train_audio_queue.append(TrainAudioTask(body.model_name, ref_dir_name, body.epoch).tostring())

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

    task = await train_video_queue.append(TrainVideoTask(body.speaker).tostring())

    return JSONResponse(
        {
            "task_id": task.id,
        }
    )
