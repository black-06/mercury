import asyncio
import json
import os
from dataclasses import dataclass

import httpx
from dataclasses_json import DataClassJsonMixin

from common.task_queue import TaskQueue
from models.task import TaskStatus
from utils.file import createDir

TRAIN_AUDIO_KEY = "TRAIN_AUDIO"
TRAIN_VIDEO_KEY = "TRAIN_VIDEO"


@dataclass
class TrainAudioTask(DataClassJsonMixin):
    model_name: str
    ref_dir_name: str
    epoch: int


@dataclass
class TrainVideoTask(DataClassJsonMixin):
    speaker: str


async def slice_for_cosy_voice(model_name: str, task_id: int, ref_dir_name: str):
    """
    切分音频作为 cosyvoice 参考音频
    """
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
                "sliding_slice": False,
            },
        )

    if not response.status_code == 200:
        raise Exception(f"slice audio failed, code: {response.status_code}")


async def train_rvc(model_name: str, ref_dir_name: str, epoch: int):
    """
    训练rvc模型
    """
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://127.0.0.1:3334/train?name=" + model_name + "&ref_dir_name=" + ref_dir_name + "&epoch=" + str(epoch)
        )

    if not response.status_code == 200:
        raise Exception(f"response error, code: {response.status_code}")


async def train_audio_task_handler(task_id: int, task_str: str) -> None:
    task = TrainAudioTask(**json.loads(task_str))
    await slice_for_cosy_voice(task.model_name, task_id, task.ref_dir_name)
    await train_rvc(
        task.model_name,
        task.ref_dir_name,
        task.epoch,
    )


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
