import os
from typing import Optional
import uuid
from fastapi import APIRouter, Request, HTTPException
import azure.cognitiveservices.speech as speechsdk
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
import requests
from starlette.responses import FileResponse
from infra.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION
from infra.file import get_file_absolute_path
from middleware.auth import getUserInfo
from infra.logger import logger
from models.file import create_file, query_file
from models.task import Task, TaskStatus, create_task, update_task
from models.model import query_model, Model
from routes.common import CommonSchemaConfig
from utils.file import createDir


router = APIRouter(
    prefix="/infer",
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
    response = requests.post(
        "http://127.0.0.1:3334/rvc?model_name="
        + model_name
        + "&output_path="
        + output_path
        + "&audio_path="
        + audio_path
        + "&pitch="
        + str(pitch),
    )
    if not response.ok:
        raise HTTPException(
            status_code=response.status_code, detail=response.text)
    return response.json()

async def gpt_infer(text: str, model_name: str, output_path: str):
    response = requests.post(
        "http://127.0.0.1:9880/infer",
        json={
            "text": text,
            "model_name": model_name,
            "output_path": output_path
        },
        headers={"Content-Type": "application/json"},
    )
    if not response.ok:
        raise HTTPException(
            status_code=response.status_code, detail=response.text)
    return output_path

async def cosy_infer(text: str, model_name: str, output_path: str):
    response = requests.post(
        "http://127.0.0.1:3335/infer",
        json={
            "text": text,
            "model_name": model_name,
            "output_path": output_path
        },
        headers={"Content-Type": "application/json"},
    )
    if not response.ok:
        raise HTTPException(
            status_code=response.status_code, detail=response.text)
    return output_path

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

    task = await create_task()

    output_dir_path = gen_output_dir(model.name, user["user_id"], task.id)

    output_video_path = os.path.join(output_dir_path, f"{task.id}.mp4")

    video_file = await create_file(output_video_path, user["user_id"])

    await update_task(
        task.id,
        status=TaskStatus.PENDING,
        res={
            "input_audio_file_id": audio_file.id,
            "output_video_file_id": video_file.id,
        },
    )

    # infer video asyncously
    internal_infer_video(
        get_file_absolute_path(audio_file.path), model, output_video_path, task
    )

    return JSONResponse(
        {
            "task_id": task.id,
        }
    )


def internal_infer_video(
    audio_path: str, model: Model, output_video_path: str, task: Task
):
    logger.debug(
        f"audio_path: {audio_path}, output_video_path: {output_video_path}, model: {model.name}, task_id: {task.id}"
    )
    response = requests.post(
        "http://0.0.0.0:8000/talking-head/inference",
        json={
            "input_audio_path": audio_path,
            "output_video_path": output_video_path,
            "speaker": model.video_model,
            "callback_url": f"http://0.0.0.0:3333/internal/task/{task.id}",
            "callback_method": "put",
        },
        headers={"Content-Type": "application/json"},
    )

    if not response.ok:
        raise HTTPException(status_code=response.status_code,
                            detail=response.json())

    logger.debug(f"response code: {response.status_code}")


class Text2VideoRequest(BaseModel):
    class Config(CommonSchemaConfig):
        pass

    text: str
    model_name: str
    audio_profile: str = "zh-CN-YunxiNeural (Male)"
    mode: int = 1 # 1 for azure, 2 for gpt


class Text2VideoResponse(BaseModel):
    task_id: int


@router.post("/text2video", response_model=Text2VideoResponse)
async def infer_text2video(body: Text2VideoRequest, req: Request):
    user = getUserInfo(req)
    logger.debug("user: %s", user)

    models = await query_model(name=body.model_name)
    model = models[0]
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"model {body.model_name} not found"
        )

    task = await create_task()

    output_dir_path = gen_output_dir(model.name, user["user_id"], task.id)

    output_video_path = os.path.join(output_dir_path, f"{task.id}.mp4")
    output_audio_path = os.path.join(output_dir_path, f"{task.id}.wav")

    audio_file = await create_file(output_audio_path, user["user_id"])
    video_file = await create_file(output_video_path, user["user_id"])

    await update_task(
        task.id,
        status=TaskStatus.PENDING,
        res={
            "output_audio_file_id": audio_file.id,
            "output_video_file_id": video_file.id,
        },
    )

    if body.mode == 2:
        # file_path = await gpt_infer(body.text, model.name, output_audio_path)
        file_path = await cosy_infer(body.text, model.name, output_audio_path)
    else:
        file_path = await azure_tts(body.text, body.audio_profile, output_dir_path)

        file_path = await rvc_infer(
            file_path, model.audio_model, output_audio_path, model.audio_config["pitch"]
        )

    # infer video asyncously
    internal_infer_video(file_path, model, output_video_path, task)

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
    mode: int = 1 # 1 for azure, 2 for gpt

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

    task = await create_task()

    output_dir_path = gen_output_dir(model.name, user["user_id"], task.id)

    output_audio_path = os.path.join(output_dir_path, f"{task.id}.wav")

    audio_file = await create_file(output_audio_path, user["user_id"])

    await update_task(
        task.id,
        status=TaskStatus.PENDING,
        res={
            "output_audio_file_id": audio_file.id,
        },
    )

    if body.mode == 2:
        file_path = await cosy_infer(body.text, model.name, output_audio_path)
        # file_path = await gpt_infer(body.text, model.name, output_audio_path)
    else:
        file_path = await azure_tts(body.text, body.audio_profile, output_dir_path)
        file_path = await rvc_infer(
            file_path, model.audio_model, output_audio_path, model.audio_config["pitch"]
        )

    await update_task(
        task.id,
        status=TaskStatus.SUCCEEDED,
    )

    return JSONResponse(
        {
            "task_id": task.id,
        }
    )
