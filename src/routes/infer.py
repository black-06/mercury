import asyncio
import json
import os
from typing import Optional
import uuid
import httpx
from common.task_queue import TaskQueue
from fastapi import APIRouter, Request, HTTPException
import azure.cognitiveservices.speech as speechsdk
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.responses import FileResponse
from infra.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION
from infra.file import get_file_absolute_path
from middleware.auth import getUserInfo
from infra.logger import logger
from models.file import create_file, query_file
from models.task import Task, TaskStatus, create_task, query_task, update_task
from models.model import query_model, Model
from routes.common import CommonSchemaConfig
from utils.file import createDir
import models.file as FileModel
from enum import Enum

router = APIRouter(
    prefix="/infer",
)

ASR_MODEL_NAME = "Asr2srt"

class AudioMode(int, Enum):
    RVC = 1
    COSYVOICE = 2

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


@router.post("/audio", include_in_schema=False)
async def infer_audio(
    req: Request,
    text: Optional[str] = None,
    audio_profile: Optional[str] = None,
    audio_path: Optional[str] = None,
    model_name: Optional[str] = None,
):

    models = await query_model(name=model_name)
    model = models[0]
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"model {model_name} not found")

    user = getUserInfo(req)
    task = await create_task()
    output_dir = gen_output_dir(model.name, user["user_id"], task.id)

    logger.debug(
        "text: %s, audio_profile: %s, audio_path: %s, model_name: %s, user: %s",
        text,
        audio_profile,
        audio_path,
        model_name,
        user,
    )
    file_path = ""
    if text is not None:
        file_path = await azure_tts(text, audio_profile, output_dir)
    else:
        file_path = await rvc_infer(
            audio_path,
            model.audio_model,
            os.path.join(output_dir, f"{task.id}.wav",
                         model.audio_config["pitch"]),
        )
    return FileResponse(file_path)


async def azure_tts(text: str, audio_profile: str, output_dir: str):
    # randome file name for the audio file
    audio_file_name = "azure_" + str(uuid.uuid4()) + ".wav"
    file_path = os.path.join(output_dir, audio_file_name)

    speech_config = speechsdk.SpeechConfig(
        subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION
    )
    audio_config = speechsdk.audio.AudioOutputConfig(
        use_default_speaker=True, filename=file_path
    )

    # remove all (xxx), example: "zh-CN-XiaoxiaoNeural (Female)" to be "zh-CN-XiaoxiaoNeural"
    audio_profile = audio_profile.split(" (")[0]
    speech_config.speech_synthesis_voice_name = audio_profile

    speech_synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=audio_config
    )

    speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()

    if (
        speech_synthesis_result.reason
        == speechsdk.ResultReason.SynthesizingAudioCompleted
    ):
        return file_path
    elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        print("Speech synthesis canceled: {}".format(
            cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            if cancellation_details.error_details:
                raise HTTPException(
                    status_code=500,
                    detail="Error details: {}".format(
                        cancellation_details.error_details
                    ),
                )
    return file_path


async def rvc_infer(audio_path: str, model_name: str, output_path: str, pitch: int = 0):
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post("http://127.0.0.1:3334/rvc?model_name="
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
            json={
                "text": text,
                "model_name": model_name,
                "output_path": output_path
            },
        )
    if response.status_code == 200:
        return output_path
    else:
        raise Exception(f"gpt_infer err, response: {response}")    

async def cosy_infer(text: str, model_name: str, output_path: str):
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "http://127.0.0.1:3335/infer",
            json={
                "text": text,
                "model_name": model_name,
                "output_path": output_path
            },
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


class InferText2AudioPayload():
    def __init__(self, text: str, model_name: str, audio_profile: str , mode: AudioMode, gen_srt: bool, user_id: int):
        self.text = text
        self.model_name = model_name
        self.audio_profile = audio_profile
        self.mode = mode 
        self.gen_srt = gen_srt # 是否同步生成 字幕文件
        self.user_id = user_id
    def tostirng(self):
        return json.dumps(self.__dict__)
        
async def infer_text2audio_task_handler(task_id: int, payload_str: str ) -> None:
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
    rvc_model=model.audio_model
    rvc_pitch=model.audio_config.get('pitch', 0)
    

    if payload.mode == AudioMode.COSYVOICE:
        file_path = await cosy_infer(payload.text, payload.model_name, output_audio_path)
    else:
        file_path = await azure_tts(payload.text, payload.audio_profile, output_dir_path)
        file_path = await rvc_infer(
            file_path, rvc_model, output_audio_path, rvc_pitch
        )
        
    if payload.gen_srt:
        srtfile = await query_file(file_id=task.res["output_srt_file_id"])
        output_srt_path = srtfile.path
        await srt_infer(file_path, output_srt_path, payload.text)

infer_text2audio_queue = TaskQueue(
    "INFER_TEXT2AUDIO",
    handler=infer_text2audio_task_handler,
    handle_sleep=1,
    max_parallel_tasks=2
)

class InferText2VideoPayload():
    def __init__(self, text: str, model_name: str, audio_profile: str, mode: AudioMode, gen_srt: bool, user_id: int):
        self.text = text
        self.model_name = model_name
        self.audio_profile = audio_profile
        self.mode = mode
        self.gen_srt = gen_srt
        self.user_id = user_id
    def tostirng(self):
        return json.dumps(self.__dict__)
        
async def infer_text2video_task_handler(task_id: int, payload_str: str) -> TaskStatus:  
    tasks = await query_task(task_id=task_id)
    task = tasks[0]
    audiofile = await query_file(file_id=task.res["output_audio_file_id"])
    output_audio_path = audiofile.path
    output_dir_path = os.path.dirname(output_audio_path)
    
    payload = InferText2VideoPayload(**json.loads(payload_str))
    models = await query_model(name=payload.model_name)
    model = models[0]
   
    if payload.mode == AudioMode.COSYVOICE:
        # file_path = await gpt_infer(body.text, model.name, output_audio_path)
        file_path = await cosy_infer(payload.text, model.name, output_audio_path)
    else:
        file_path = await azure_tts(payload.text, payload.audio_profile, output_dir_path)
        file_path = await rvc_infer(
            file_path, model.audio_model, output_audio_path, model.audio_config.get("pitch", 0)
        )

    if payload.gen_srt:
        srtfile = await query_file(file_id=task.res["output_srt_file_id"])
        output_srt_path = srtfile.path
        await srt_infer(file_path, output_srt_path, payload.text)

    # infer video asyncously
    videofile = await query_file(file_id=task.res["output_video_file_id"])
    output_video_path = videofile.path

    await internal_infer_video(file_path, model, output_video_path, task_id)
    return TaskStatus.PENDING


infer_text2vedio_queue = TaskQueue(
    "INFER_TEXT2VIDEO",
    handler=infer_text2video_task_handler,
    handle_sleep=1,
    max_parallel_tasks=1
)


class InferAudio2VideoPayload():
    def __init__(self, model_name: str, audio_id: int, user_id: str):
        self.model_name=model_name
        self.audio_id=audio_id
        self.user_id=user_id
    def tostirng(self):
        return json.dumps(self.__dict__)
        
async def infer_audio2video_task_handler(task_id: int, payload_str: str) -> TaskStatus:
    tasks = await query_task(task_id=task_id)
    task = tasks[0]
    input_audio_file = await query_file(file_id=task.res["input_audio_file_id"])
    video_file = await query_file(file_id=task.res["output_video_file_id"])
    
    payload = InferAudio2VideoPayload(**json.loads(payload_str))
    models = await query_model(name=payload.model_name)
    model = models[0]

    # infer video asyncously
    await internal_infer_video(
        get_file_absolute_path(input_audio_file.path), model, video_file.path, task_id
    )
    return TaskStatus.PENDING
    
        
infer_audio2video_queue = TaskQueue(
    "INFER_TAUDIO2VIDEO",
    handler=infer_audio2video_task_handler,
    handle_sleep=1,
    max_parallel_tasks=1
)

class InferVideoResponse(BaseModel):
    task_id: int


@router.post("/video", response_model=InferVideoResponse)
async def infer_video(
    model_name: str,
    file_id: int,
    req: Request,
):
    models = await query_model(name=model_name)
    model = models[0]

    if model is None:
        raise HTTPException(
            status_code=404, detail=f"model {model_name} not found")

    audio_file = await query_file(file_id)
    if audio_file is None:
        raise HTTPException(
            status_code=404, detail=f"file {file_id} not found")

    user = getUserInfo(req)
    task = await infer_audio2video_queue.append(InferAudio2VideoPayload(
        model_name=model_name,
        audio_id=file_id,
        user_id=user["user_id"],
    ).tostirng())
    
    output_dir_path = gen_output_dir(model.name, user["user_id"], task.id)
    output_video_path = os.path.join(output_dir_path, f"{task.id}.mp4")
    video_file = await create_file(output_video_path, user["user_id"])
    await update_task(
        task.id,
        res={
            "input_audio_file_id": audio_file.id,
            "output_video_file_id": video_file.id,
        },
    )
   
        

    return JSONResponse(
        {
            "task_id": task.id,
        }
    )


async def internal_infer_video(
    audio_path: str, model: Model, output_video_path: str, task_id: int
):
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

class Text2VideoRequest(BaseModel):
    class Config(CommonSchemaConfig):
        pass

    text: str
    model_name: str
    audio_profile: str = "zh-CN-YunxiNeural (Male)"
    mode: AudioMode = AudioMode.RVC
    gen_srt: bool = Field(
        False, 
        description="是否同步生成字幕文件，默认不生成。若为True,将在任务详情中返回 res.output_srt_file_id"
    ) # 是否同步生成 字幕文件


class Text2VideoResponse(BaseModel):
    task_id: int


@router.post("/text2video", response_model=Text2VideoResponse)
async def infer_text2video(body: Text2VideoRequest, req: Request):
    user = getUserInfo(req)
    logger.debug("user: %s", user)

    models = await query_model(name=body.model_name)
    if len(models) == 0:
        raise HTTPException(
            status_code=404, detail=f"model {body.model_name} not found"
        )
    model = models[0]
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"model {body.model_name} not found"
        )

    task = await infer_text2vedio_queue.append(InferText2VideoPayload(
        text=body.text,
        model_name=body.model_name,
        audio_profile=body.audio_profile,
        mode=body.mode,
        gen_srt=body.gen_srt,
        user_id=user["user_id"]
    ).tostirng())
    task_id = task.id
    output_dir_path = gen_output_dir(model.name, user["user_id"], task_id)
    output_video_path = os.path.join(output_dir_path, f"{task_id}.mp4")
    output_audio_path = os.path.join(output_dir_path, f"{task_id}.wav")
    audio_file = await create_file(output_audio_path, user["user_id"])
    video_file = await create_file(output_video_path, user["user_id"])
    
    srt_file_id = 0
    if body.gen_srt:
        output_srt_path = os.path.join(output_dir_path, f"{task_id}.srt")
        srt_file = await create_file(output_srt_path, user["user_id"])
        srt_file_id = srt_file.id
    await update_task(
        task_id,
        res={
            "output_audio_file_id": audio_file.id,
            "output_video_file_id": video_file.id,
            "output_srt_file_id": srt_file_id,
        },
    )

    return JSONResponse(
        {
            "task_id": task.id,
        }
    )


class Text2AudioRequest(BaseModel):
    class Config(CommonSchemaConfig):
        pass

    text: str
    model_name: str
    audio_profile: str = "zh-CN-YunxiNeural (Male)"
    mode: AudioMode = AudioMode.RVC # 1 for azure, 2 for gpt
    gen_srt: bool = Field(
        False, 
        description="是否同步生成字幕文件，默认不生成。若为True,将在任务详情中返回 res.output_srt_file_id"
    ) # 是否同步生成 字幕文件

class Text2AudioResponse(BaseModel):
    task_id: int


@router.post("/text2audio", response_model=Text2AudioResponse)
async def infer_text2audio(body: Text2AudioRequest, req: Request):
    user = getUserInfo(req)
    logger.debug("user: %s", user)
    models = await query_model(name=body.model_name)
    model = models[0]
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"model {body.model_name} not found"
        )

    task = await infer_text2audio_queue.append(InferText2AudioPayload(
        text=body.text,
        model_name=body.model_name,
        audio_profile=body.audio_profile,
        mode=body.mode,
        gen_srt=body.gen_srt,
        user_id=user["user_id"],
    ).tostirng())
    
    task_id = task.id
    output_dir_path = gen_output_dir(body.model_name, user["user_id"], task_id)
    output_audio_path = os.path.join(output_dir_path, f"{task_id}.wav")
    audio_file = await create_file(output_audio_path, user["user_id"])
    srt_file_id = 0
    if body.gen_srt:
        output_srt_path = os.path.join(output_dir_path, f"{task_id}.srt")
        srt_file = await create_file(output_srt_path, user["user_id"])
        srt_file_id = srt_file.id

    await update_task(
        task_id,
        res={
            "output_audio_file_id": audio_file.id,
            "output_srt_file_id": srt_file_id,
        },
    )
        
    return JSONResponse(
        {
            "task_id": task.id,
        }
    )

class AudioAsrRequest(BaseModel):
    class Config(CommonSchemaConfig):
        pass

    text: str = Field(
        "",
        description="音频的原始文案信息，需要与音频内容一致，否则会导致错误。若不提供，将会尝试推理音频内容，部分文案会出错。执行成功后，可在任务详情查看res.output_srt_file_id"
    )
    file_id: int = Field(
        description="音频id"
    )
    
class Audio2AsrResponse(BaseModel):
    output_srt_file_id: int
    task_id: int
    
    
@router.post("/audio2srt", response_model=Audio2AsrResponse, include_in_schema=False)
async def infer_asr(body: AudioAsrRequest, req: Request):
    user = getUserInfo(req)
    user_id = user["user_id"]
    logger.debug("user: %s", user)
    

    res = await FileModel.query_file(body.file_id)
    if not res:
        raise HTTPException(status_code=404, detail="file not found")

    if res.user_id != user_id:
        raise HTTPException(status_code=403, detail="no permission")
    audio_path = res.path
    
    task = await create_task()
    output_srt_dir_path = gen_output_dir(ASR_MODEL_NAME, user["user_id"], task.id)
    output_srt_path = os.path.join(output_srt_dir_path, f"{task.id}.srt")
    
    srt_file = await create_file(output_srt_path, user["user_id"])
    
    await update_task(
        task.id,
        status=TaskStatus.SUCCEEDED,
        res={
            "output_srt_file_id": srt_file.id,
        },
    )
    
    await srt_infer(audio_path, output_srt_path, body.text)
    
    return JSONResponse(
        {
            "task_id": task.id,
            "output_srt_file_id": srt_file.id,
        }
    )