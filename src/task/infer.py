import os
from typing import Tuple, Optional

from celery import Celery, group
from celery.result import AsyncResult, GroupResult

celery_enabled = os.environ.get("CELERY_ENABLED", True)
celery_broker = os.environ.get("CELERY_BROKER")
celery_backend = os.environ.get("CELERY_BACKEND")
celery_app = Celery("tasks", broker=celery_broker, backend=celery_backend)
celery_app.conf.task_routes = {}


def cosy_cos_helper(model_name: str) -> Tuple[str, str]:
    """
    根据模型名称找到 cosy 对应的参考文本 & 参考视频 COS key
    :param model_name: 模型名
    :return: 参考文本, 参考视频 COS key
    """
    return f"model/cosy/{model_name}.lab", f"model/cosy/{model_name}.wav"


def rvc_cos_helper(model_name: str) -> Tuple[str, str]:
    """
    根据 rvc 模型名称找到对应的 index & model weight COS key
    :param model_name: 模型名
    :return: index, model weight COS key
    """
    return f"model/rvc/{model_name}.index", f"model/rvc/{model_name}.model"


@celery_app.task(name="cosy_infer", queue="cosy_infer")
def cosy_infer_task(
    text: str,
    prompt_text_cos: str,
    prompt_wav_cos: str,
    output_cos: str,
    mode: int = 1,
) -> str:
    """
    COSY TTS 服务
    :param text: 音频文字内容
    :param prompt_text_cos: 参考文本 COS key, 据说是训练 rvc 的时候放入
    :param prompt_wav_cos: 参考音频 COS key
    :param output_cos: 合成的音频文件 COS key
    :param mode: 模式： 1 中文[同语言克隆] 2 中日英混合[跨语言克隆]
    :return: output_cos
    """
    pass


@celery_app.task(name="azure_infer", queue="azure_infer")
def azure_infer_task(text: str, audio_profile: str, output_cos: str) -> str:
    """
    微软 TTS 服务
    :param text: 音频文字内容
    :param audio_profile: 配置
    :param output_cos: 合成的音频文件 COS key
    :return: output_cos
    """
    pass


@celery_app.task(name="rvc_infer", queue="rvc_infer")
def rvc_infer_task(audio_cos: str, index_cos: str, model_cos: str, pitch: int, output_cos: str) -> str:
    """
    RVC TTS 服务
    :param audio_cos: 原始音频 COS key
    :param index_cos: 模型 index COS key
    :param model_cos: 模型 weight COS key
    :param pitch: TODO
    :param output_cos: 转换后的音频 COS key
    :return: output_cos
    """
    pass


@celery_app.task(name="srt_infer", queue="srt_infer")
def srt_infer_task(audio_cos: str, text: str, output_cos: str) -> str:
    """
    根据音频文件生成字幕服务
    :param audio_cos: 音频文件 COS key
    :param text: 文本，原始文案，通过提供原始文案可以使asr结果更准确。请确保文案与音频内容一致
    :param output_cos: 输出的字幕文件 COS key
    :return: output_cos
    """
    pass


@celery_app.task(name="talking_head_infer", queue="talking_head_infer")
def talking_head_infer_task(audio_cos: str, speaker: str, output_cos: str) -> str:
    """
    根据音频生成数字人视频服务
    :param audio_cos: 音频文件
    :param speaker: 使用的数字人
    :param output_cos: 输出的视频文件 COS key
    :return: output_cos
    """
    pass


def publish_cosy_infer_task(text: str, model_name: str, output_cos: str, mode: int = 1) -> AsyncResult:
    prompt_text_cos, prompt_wav_cos = cosy_cos_helper(model_name)
    return cosy_infer_task.delay(text, prompt_text_cos, prompt_wav_cos, output_cos, mode)


def publish_azure_infer_task(text: str, audio_profile: str, output_cos: str) -> AsyncResult:
    return azure_infer_task.delay(text, audio_profile, output_cos)


def publish_rvc_infer_task(audio_cos: str, model_name: str, pitch: int, output_cos: str) -> AsyncResult:
    index_cos, model_cos = rvc_cos_helper(model_name)
    return rvc_infer_task.delay(audio_cos, index_cos, model_cos, pitch, output_cos)


def publish_srt_infer_task(audio_cos: str, text: str, output_cos: str) -> AsyncResult:
    return srt_infer_task.delay(audio_cos, text, output_cos)


def publish_talking_head_infer_task(audio_cos: str, speaker: str, output_cos: str) -> AsyncResult:
    return talking_head_infer_task.delay(audio_cos, speaker, output_cos)


def publish_text_task(
    text: str,
    model_name: str,
    output_audio_cos: str,
    azure_audio_profile: str,
    azure_output_audio_cos: Optional[str],
    pitch: int,
    speaker: Optional[str],
    output_video_cos: Optional[str],
    output_srt_cos: Optional[str],
) -> GroupResult | AsyncResult:
    if azure_output_audio_cos:
        azure = azure_infer_task.s(text, azure_audio_profile, azure_output_audio_cos)
        index_cos, model_cos = rvc_cos_helper(model_name)
        rvc = rvc_infer_task.s(index_cos, model_cos, pitch, output_audio_cos)
        tts = azure | rvc
    else:
        prompt_text_cos, prompt_wav_cos = cosy_cos_helper(model_name)
        tts = cosy_infer_task.s(text, prompt_text_cos, prompt_wav_cos, output_audio_cos, mode=1)
    if output_video_cos and output_srt_cos:
        assert speaker is not None
        talking_head = talking_head_infer_task.s(speaker, output_video_cos)
        srt = srt_infer_task.s(text, output_srt_cos)
        task = tts | group(talking_head, srt)
    elif output_video_cos:
        assert speaker is not None
        talking_head = talking_head_infer_task.s(speaker, output_video_cos)
        task = tts | talking_head
    elif output_srt_cos:
        srt = srt_infer_task.s(text, output_srt_cos)
        task = tts | srt
    else:
        task = tts
    return task.delay()
