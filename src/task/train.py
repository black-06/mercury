from typing import List

from celery import group
from celery.result import GroupResult

from task.infer import celery_app


@celery_app.task(name="slice_audio")
def slice_audio_task(
    audio_coss: List[str],
    min_length: int,
    max_length: int,
    keep_silent: float,
    sliding_slice: bool,
):
    """
    切分音频作为 cosyvoice 参考音频
    :param audio_coss: 音频文件 cos key list
    :param min_length: 切分的音频最小长度, 单位 s
    :param max_length: 切分的音频最大长度, 单位 s
    :param keep_silent: 前后 0.5 s 静音
    :param sliding_slice: TODO
    """
    pass


@celery_app.task("rvc_train")
def rvc_train_task(audio_coss: List[str], model_name: str, epoch: int):
    """
    训练 rvc 模型
    :param audio_coss: 音频文件 cos key list
    :param model_name: rvc 模型名
    :param epoch: TODO
    """
    pass


@celery_app.task("talking_head_train")
def talking_head_train_task(audio_coss: List[str], speaker: str):
    """
    训练数字人模型
    :param audio_coss: 音频文件 cos key list
    :param speaker: TODO
    """
    pass


def publish_audio_train_task(audio_coss: List[str], model_name: str, epoch: int) -> GroupResult:
    return group(
        slice_audio_task.s(
            audio_coss=audio_coss,
            min_length=8,
            max_length=12,
            keep_silent=0.5,
            sliding_slice=False,
        ),
        rvc_train_task.s(
            audio_coss=audio_coss,
            model_name=model_name,
            epoch=epoch,
        ),
    )()


def publish_video_train_task(audio_coss: List[str], speaker: str):
    return talking_head_train_task.delay(audio_coss, speaker)
