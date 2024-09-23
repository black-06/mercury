import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from enum import Enum

import azure.cognitiveservices.speech as speechsdk
import httpx
from dataclasses_json import DataClassJsonMixin
from fastapi import HTTPException

from common.task_queue import TaskQueue
from infra.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION
from infra.file import get_file_absolute_path
from infra.logger import logger
from models.file import query_file
from models.model import query_model, Model
from models.task import query_task, TaskStatus


class AudioModeType(int, Enum):
    RVC = 1
    COSYVOICE = 2


@dataclass
class InferText2VideoPayload(DataClassJsonMixin):
    text: str
    model_name: str
    audio_profile: str
    mode: AudioModeType
    gen_srt: bool
    user_id: int


@dataclass
class InferAudio2VideoPayload(DataClassJsonMixin):
    model_name: str
    audio_id: int
    user_id: str


@dataclass
class InferText2AudioPayload(DataClassJsonMixin):
    text: str
    model_name: str
    audio_profile: str
    mode: AudioModeType
    gen_srt: bool
    user_id: int


async def cosy_infer(text: str, model_name: str, output_path: str):
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://127.0.0.1:3335/infer",
            json={"text": text, "model_name": model_name, "output_path": output_path},
        )
    if response.status_code == 200:
        return output_path
    else:
        raise Exception(f"cosy_infer err, response: {response}")


async def srt_infer(audio_path: str, output_path: str, text: str = ""):
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://127.0.0.1:3336/audio/gen_audio_srt",
            json={
                "ref_text": text,
                "audio_file": audio_path,
                "output_path": output_path,
            },
        )
    if response.status_code == 200:
        return output_path
    else:
        raise Exception(f"srt_infer err, response: {response}")


async def azure_tts(text: str, audio_profile: str, output_dir: str):
    # randome file name for the audio file
    audio_file_name = "azure_" + str(uuid.uuid4()) + ".wav"
    file_path = os.path.join(output_dir, audio_file_name)

    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True, filename=file_path)

    # remove all (xxx), example: "zh-CN-XiaoxiaoNeural (Female)" to be "zh-CN-XiaoxiaoNeural"
    audio_profile = audio_profile.split(" (")[0]
    speech_config.speech_synthesis_voice_name = audio_profile

    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

    speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()

    if speech_synthesis_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return file_path
    elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            if cancellation_details.error_details:
                raise HTTPException(
                    status_code=500,
                    detail="Error details: {}".format(cancellation_details.error_details),
                )
    return file_path


async def rvc_infer(audio_path: str, model_name: str, output_path: str, pitch: int = 0):
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://127.0.0.1:3334/rvc?model_name="
            + model_name
            + "&output_path="
            + output_path
            + "&audio_path="
            + audio_path
            + "&pitch="
            + str(pitch),
        )
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"rvc_infer err, response: {response}")


async def gpt_infer(text: str, model_name: str, output_path: str):
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://127.0.0.1:9880/infer",
            json={"text": text, "model_name": model_name, "output_path": output_path},
        )
    if response.status_code == 200:
        return output_path
    else:
        raise Exception(f"gpt_infer err, response: {response}")


async def talking_head_infer(audio_path: str, model: Model, output_video_path: str, task_id: int):
    logger.debug(
        f"audio_path: {audio_path}, output_video_path: {output_video_path}, model: {model.name}, task_id: {task_id}"
    )
    while True:
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.get("http://0.0.0.0:8000/talking-head/infer-ready")
        if response.status_code != 200:
            raise Exception(f"status_code {response.status_code}, {response.json()}")
        if response.json().get("ready", True):
            break
        logger.debug("等待进行中的推理任务完成")
        await asyncio.sleep(1)

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://0.0.0.0:8000/talking-head/inference",
            json={
                "input_audio_path": audio_path,
                "output_video_path": output_video_path,
                "speaker": model.video_model,
                "callback_url": f"http://0.0.0.0:3333/internal/task/{task_id}",
                "callback_method": "put",
            },
        )
    if response.status_code != 200:
        logger.debug(f"response code: {response.status_code}")
        raise Exception(f"internal_infer_video err, response code: {response.status_code}, response: {response}")


async def infer_text2audio_task_handler(task_id: int, payload_str: str) -> None:
    # TODO getTask 从中获取fileid
    # 根据file 获取 文件路径
    tasks = await query_task(task_id=task_id)
    task = tasks[0]

    audiofile = await query_file(file_id=task.res["output_audio_file_id"])
    output_audio_path = audiofile.path
    output_dir_path = os.path.dirname(output_audio_path)

    payload = InferText2AudioPayload(**json.loads(payload_str))
    models = await query_model(name=payload.model_name)
    model = models[0]
    rvc_model = model.audio_model
    rvc_pitch = model.audio_config.get("pitch", 0)

    if payload.mode == AudioModeType.COSYVOICE:
        file_path = await cosy_infer(payload.text, payload.model_name, output_audio_path)
    else:
        file_path = await azure_tts(payload.text, payload.audio_profile, output_dir_path)
        file_path = await rvc_infer(file_path, rvc_model, output_audio_path, rvc_pitch)

    if payload.gen_srt:
        srtfile = await query_file(file_id=task.res["output_srt_file_id"])
        output_srt_path = srtfile.path
        await srt_infer(file_path, output_srt_path, payload.text)


async def infer_audio2video_task_handler(task_id: int, payload_str: str) -> TaskStatus:
    tasks = await query_task(task_id=task_id)
    task = tasks[0]
    input_audio_file = await query_file(file_id=task.res["input_audio_file_id"])
    video_file = await query_file(file_id=task.res["output_video_file_id"])

    payload = InferAudio2VideoPayload(**json.loads(payload_str))
    models = await query_model(name=payload.model_name)
    model = models[0]

    # infer video asyncously
    await talking_head_infer(get_file_absolute_path(input_audio_file.path), model, video_file.path, task_id)
    return TaskStatus.PENDING


async def infer_text2video_task_handler(task_id: int, payload_str: str) -> TaskStatus:
    tasks = await query_task(task_id=task_id)
    task = tasks[0]
    audiofile = await query_file(file_id=task.res["output_audio_file_id"])
    output_audio_path = audiofile.path
    output_dir_path = os.path.dirname(output_audio_path)

    payload = InferText2VideoPayload(**json.loads(payload_str))
    models = await query_model(name=payload.model_name)
    model = models[0]

    if payload.mode == AudioModeType.COSYVOICE:
        file_path = await cosy_infer(payload.text, model.name, output_audio_path)
    else:
        file_path = await azure_tts(payload.text, payload.audio_profile, output_dir_path)
        file_path = await rvc_infer(file_path, model.audio_model, output_audio_path, model.audio_config.get("pitch", 0))

    if payload.gen_srt:
        srtfile = await query_file(file_id=task.res["output_srt_file_id"])
        output_srt_path = srtfile.path
        await srt_infer(file_path, output_srt_path, payload.text)

    # infer video asyncously
    videofile = await query_file(file_id=task.res["output_video_file_id"])
    output_video_path = videofile.path

    await talking_head_infer(file_path, model, output_video_path, task_id)
    return TaskStatus.PENDING


infer_text2audio_queue = TaskQueue(
    "INFER_TEXT2AUDIO", handler=infer_text2audio_task_handler, handle_sleep=1, max_parallel_tasks=2
)

infer_audio2video_queue = TaskQueue(
    "INFER_TAUDIO2VIDEO", handler=infer_audio2video_task_handler, handle_sleep=1, max_parallel_tasks=1
)

infer_text2video_queue = TaskQueue(
    "INFER_TEXT2VIDEO", handler=infer_text2video_task_handler, handle_sleep=1, max_parallel_tasks=1
)
