import os
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import FileResponse

from infra.logger import logger
from middleware.auth import getUserInfo
from models.file import create_file, query_file
from models.model import query_model
from models.task import TaskStatus, create_task, update_task
from routes.common import CommonSchemaConfig
from task.infer import publish_talking_head_infer_task, celery_enabled, publish_text2video_task, publish_text2audio_task
from task.infer_http import (
    AudioModeType,
    infer_text2video_queue,
    infer_audio2video_queue,
    infer_text2audio_queue,
    InferText2AudioPayload,
    InferText2VideoPayload,
    InferAudio2VideoPayload,
    azure_tts,
    rvc_infer,
    srt_infer,
)
from utils.file import createDir

router = APIRouter(
    prefix="/infer",
)

ASR_MODEL_NAME = "Asr2srt"


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
            audio_path,
            model.audio_model,
            os.path.join(output_dir, f"{task.id}.wav", model.audio_config["pitch"]),
        )
    return FileResponse(file_path)


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
        raise HTTPException(status_code=404, detail=f"model {model_name} not found")

    audio_file = await query_file(file_id)
    if audio_file is None:
        raise HTTPException(status_code=404, detail=f"file {file_id} not found")

    user = getUserInfo(req)

    if celery_enabled and audio_file.cos:
        rst = publish_talking_head_infer_task(str(audio_file.id), model.video_model)
        return JSONResponse({"task_id": rst.id})

    task = await infer_audio2video_queue.append(
        InferAudio2VideoPayload(
            model_name=model_name,
            audio_id=file_id,
            user_id=user["user_id"],
        ).to_json()
    )

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


class Text2VideoRequest(BaseModel):
    text: str
    model_name: str
    audio_profile: str = "zh-CN-YunxiNeural (Male)"
    mode: AudioModeType = AudioModeType.RVC
    gen_srt: bool = Field(
        False, description="是否同步生成字幕文件，默认不生成。若为True,将在任务详情中返回 res.output_srt_file_id"
    )  # 是否同步生成 字幕文件


class Text2VideoResponse(BaseModel):
    task_id: int


@router.post("/text2video", response_model=Text2VideoResponse)
async def infer_text2video(body: Text2VideoRequest, req: Request):
    user = getUserInfo(req)
    logger.debug("user: %s", user)

    models = await query_model(name=body.model_name)
    if len(models) == 0:
        raise HTTPException(status_code=404, detail=f"model {body.model_name} not found")
    model = models[0]
    if model is None:
        raise HTTPException(status_code=404, detail=f"model {body.model_name} not found")

    if celery_enabled:
        rst = publish_text2video_task(
            model_type=body.mode,
            text=body.text,
            model_name=body.model_name,
            audio_profile=body.audio_profile,
            pitch=model.audio_config.get("pitch", 0),
            speaker=model.video_model,
            gen_srt=body.gen_srt,
        )
        return JSONResponse({"task_id": rst.id})

    task = await infer_text2video_queue.append(
        InferText2VideoPayload(
            text=body.text,
            model_name=body.model_name,
            audio_profile=body.audio_profile,
            mode=body.mode,
            gen_srt=body.gen_srt,
            user_id=user["user_id"],
        ).to_json()
    )
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
    mode: AudioModeType = AudioModeType.RVC  # 1 for azure, 2 for gpt
    gen_srt: bool = Field(
        False, description="是否同步生成字幕文件，默认不生成。若为True,将在任务详情中返回 res.output_srt_file_id"
    )  # 是否同步生成 字幕文件


class Text2AudioResponse(BaseModel):
    task_id: int


@router.post("/text2audio", response_model=Text2AudioResponse)
async def infer_text2audio(body: Text2AudioRequest, req: Request):
    user = getUserInfo(req)
    logger.debug("user: %s", user)
    models = await query_model(name=body.model_name)
    model = models[0]
    if model is None:
        raise HTTPException(status_code=404, detail=f"model {body.model_name} not found")

    if celery_enabled:
        rst = publish_text2audio_task(
            model_type=body.mode,
            text=body.text,
            model_name=body.model_name,
            audio_profile=body.audio_profile,
            pitch=model.audio_config.get("pitch", 0),
            gen_srt=body.gen_srt,
        )
        return JSONResponse({"task_id": rst.id})


    task = await infer_text2audio_queue.append(
        InferText2AudioPayload(
            text=body.text,
            model_name=body.model_name,
            audio_profile=body.audio_profile,
            mode=body.mode,
            gen_srt=body.gen_srt,
            user_id=user["user_id"],
        ).to_json()
    )

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
        description="音频的原始文案信息，需要与音频内容一致，否则会导致错误。若不提供，将会尝试推理音频内容，部分文案会出错。执行成功后，可在任务详情查看res.output_srt_file_id",
    )
    file_id: int = Field(description="音频id")


class Audio2AsrResponse(BaseModel):
    output_srt_file_id: int
    task_id: int


@router.post("/audio2srt", response_model=Audio2AsrResponse, include_in_schema=False)
async def infer_asr(body: AudioAsrRequest, req: Request):
    user = getUserInfo(req)
    user_id = user["user_id"]
    logger.debug("user: %s", user)

    res = await query_file(body.file_id)
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
