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
from middleware.auth import getUserInfo
from infra.logger import logger
from models.file import create_file
from models.task import TaskStatus, create_task, update_task
from models.model import query_model
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


@router.post("/audio")
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
        raise HTTPException(status_code=404, detail=f"model {model_name} not found")

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
            audio_path, model.audio_model, os.path.join(output_dir, f"{task.id}.wav")
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
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            if cancellation_details.error_details:
                raise HTTPException(
                    status_code=500,
                    detail="Error details: {}".format(
                        cancellation_details.error_details
                    ),
                )
    return file_path


async def rvc_infer(audio_path: str, model_name: str, output_path: str):
    response = requests.post(
        "http://127.0.0.1:3334/rvc?model_name="
        + model_name
        + "&output_path="
        + output_path
        + "&audio_path="
        + audio_path,
    )
    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@router.post("/video")
async def infer_video(user: str, model_id: str, task: str):
    return PlainTextResponse("WIP")
    response = requests.post(
        "http://127.0.0.1:8000/talking-head/inference",
        json={
            "path": f"/data/talking_prod/{user}/{model_id}/generated/{task}/gen-hr.wav"
        },
        headers={"Content-Type": "application/json"},
    )
    return FileResponse(response.json()["path"])


class Config:
    protected_namespaces = ()


class Text2VideoRequest(BaseModel):
    class Config(Config):
        pass

    text: str
    model_name: str
    audio_profile: str = "zh-CN-YunxiNeural (Male)"


@router.post("/text2video")
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

    file = await create_file(output_video_path, user["user_id"])

    await update_task(
        task.id,
        status=TaskStatus.PENDING,
        res={
            "output_video_file_id": file.id,
        },
    )

    file_path = await azure_tts(body.text, body.audio_profile, output_dir_path)

    file_path = await rvc_infer(file_path, model.audio_model, output_audio_path)

    # infer video asyncously
    response = requests.post(
        "http://0.0.0.0:8000/talking-head/inference",
        json={
            "input_audio_path": file_path,
            "output_video_path": output_video_path,
            "speaker": model.video_model,
            "callback_url": f"http://0.0.0.0:3333/internal/task/{task.id}",
            "callback_method": "put",
        },
        headers={"Content-Type": "application/json"},
    )

    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=response.json())

    logger.debug(f"response code: {response.status_code}")

    return JSONResponse(
        {
            "task_id": task.id,
        }
    )
