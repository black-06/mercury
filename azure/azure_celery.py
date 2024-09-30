import os
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk
from celery import Celery
from qcloud_cos import CosConfig, CosS3Client

azure_speech_key = os.getenv("AZURE_SPEECH_KEY")
azure_speech_region = os.getenv("AZURE_SPEECH_REGION")

celery_broker = os.environ.get("CELERY_BROKER")
celery_backend = os.environ.get("CELERY_BACKEND")
celery_app = Celery("tasks", broker=celery_broker, backend=celery_backend)

cos_secret_id = os.environ.get("COS_SECRET_ID")
cos_secret_key = os.environ.get("COS_SECRET_KEY")
cos_region = os.environ.get("COS_REGION")
cos_bucket = os.environ.get("COS_BUCKET")
cos_config = CosConfig(Region=cos_region, SecretId=cos_secret_id, SecretKey=cos_secret_key)
cos_client = CosS3Client(cos_config)

cos_local = Path("/cos")


def get_local_path(key: str) -> Path:
    path = cos_local / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def upload_cos_file(key: str):
    cos_client.upload_file(Bucket=cos_bucket, Key=key, LocalFilePath=get_local_path(key))


@celery_app.task(name="azure_infer", queue="azure_infer")
def azure_infer_task(text: str, audio_profile: str, output_cos: str) -> str:
    """
    微软 TTS 服务
    :param text: 音频文字内容
    :param audio_profile: 配置
    :param output_cos: 合成的音频文件 COS key
    :return: output_cos
    """

    dest = get_local_path(output_cos)

    speech_config = speechsdk.SpeechConfig(subscription=azure_speech_key, region=azure_speech_region)
    # remove all (xxx), example: "zh-CN-XiaoxiaoNeural (Female)" to be "zh-CN-XiaoxiaoNeural"
    speech_config.speech_synthesis_voice_name = audio_profile.split(" (")[0]
    audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True, filename=str(dest))

    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

    speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()
    if speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            raise Exception(f"error details: {cancellation_details.error_details}")

    if speech_synthesis_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        upload_cos_file(output_cos)
        return output_cos
    elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            raise Exception(cancellation_details.error_details)
    else:
        raise Exception(f"unknown reason: {speech_synthesis_result.reason}")
