import os

from celery import Celery, group
from celery.result import AsyncResult, GroupResult

from task.infer_http import AudioModeType

celery_enabled = os.environ.get("CELERY_ENABLED", True)
celery_broker = os.environ.get("CELERY_BROKER")
celery_backend = os.environ.get("CELERY_BACKEND")
celery_app = Celery("tasks", broker=celery_broker, backend=celery_backend)


@celery_app.task(name="cosy_infer")
def cosy_infer_task(text: str, model_name: str) -> str:
    """
    COSY TTS 服务
    :param text: 音频文字内容
    :param model_name: 使用的模型
    :return: 合成的音频文件 cos key
    """
    pass


@celery_app.task(name="rvc_infer")
def rvc_infer_task(text: str, audio_profile: str, model_name: str, pitch: int) -> str:
    """
    RVC TTS 服务
    :param text: 音频文字内容
    :param audio_profile: 微软 TTS 配置
    :param model_name: 音色转换模型
    :param pitch: TODO
    :return: 合成的音频文件 cos key
    """
    pass


@celery_app.task(name="srt_infer")
def srt_infer_task(audio_cos: str, text: str) -> str:
    """
    根据音频文件生成字幕服务
    :param audio_cos: 音频文件
    :param text: 文本
    :return: 字幕文件 cos key
    """
    pass


@celery_app.task(name="talking_head_infer")
def talking_head_infer_task(audio_cos: str, speaker: str) -> str:
    """
    根据音频生成数字人视频服务
    :param audio_cos: 音频文件
    :param speaker: 使用的数字人
    :return: 视频文件
    """
    pass


def publish_cosy_infer_task(text: str, model_name: str) -> AsyncResult:
    return cosy_infer_task.delay(text, model_name)


def publish_rvc_infer_task(text: str, audio_profile: str, model_name: str, pitch: int) -> AsyncResult:
    return rvc_infer_task.delay(text, audio_profile, model_name, pitch)


def publish_srt_infer_task(audio_cos: str, text: str) -> AsyncResult:
    return srt_infer_task.delay(audio_cos, text)


def publish_talking_head_infer_task(audio_cos: str, speaker: str) -> AsyncResult:
    return talking_head_infer_task.delay(audio_cos, speaker)


def publish_text2video_task(
    model_type: AudioModeType,
    text: str,
    model_name: str,
    audio_profile: str,
    pitch: int,
    speaker: str,
    gen_srt: bool,
) -> GroupResult | AsyncResult:
    if model_type == AudioModeType.COSYVOICE:
        tts = cosy_infer_task.s(text, model_name)
    else:
        tts = rvc_infer_task.s(text, audio_profile, model_name, pitch)

    talking_head = talking_head_infer_task.s(speaker)
    if gen_srt:
        return (tts | group(talking_head, srt_infer_task.s(text))).delay()
    else:
        return (tts | talking_head).delay()


def publish_text2audio_task(
    model_type: AudioModeType,
    text: str,
    model_name: str,
    audio_profile: str,
    pitch: int,
    gen_srt: bool,
) -> AsyncResult:
    if model_type == AudioModeType.COSYVOICE:
        tts = cosy_infer_task.s(text, model_name)
    else:
        tts = rvc_infer_task.s(text, audio_profile, model_name, pitch)
    if gen_srt:
        return (tts | srt_infer_task.s(text)).delay()
    else:
        return tts.delay()
