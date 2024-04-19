from typing import Optional
import uuid
from fastapi import APIRouter

import azure.cognitiveservices.speech as speechsdk
import requests


from fastapi.responses import FileResponse

# TODO: read from .env
SPEECH_KEY = "ddd96a5781a64d44aea306651a1235d7"
SPEECH_REGION = "eastasia"


router = APIRouter(
    prefix="/infer",
)


@router.post("/audio")
async def infer_audio(
    text: Optional[str] = None,
    audio_profile: Optional[str] = None,
    audio_path: Optional[str] = None,
    model_id: Optional[str] = None,
    user: Optional[str] = None,
):
    print(text, audio_profile, audio_path, model_id)
    file_path = ""
    if text is not None:
        file_path = await azure_tts(text, audio_profile)
    else:
        file_path = await rvc_infer(audio_path, model_id, user)
    return FileResponse(file_path)


async def azure_tts(
    text: str,
    audio_profile: str,
):
    print(text, audio_profile)

    # randome file name for the audio file
    audio_file_name = str(uuid.uuid4()) + ".wav"
    file_path = "/tmp/" + audio_file_name

    speech_config = speechsdk.SpeechConfig(
        subscription=SPEECH_KEY, region=SPEECH_REGION
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
                raise Exception(
                    "Error details: {}".format(cancellation_details.error_details)
                )
    return file_path


async def rvc_infer(audio_path: str, model_id: str, user: str):
    response = requests.post(
        "http://127.0.0.1:3334/rvc?model_id="
        + model_id
        + "&user="
        + user
        + "&audio_path="
        + audio_path,
    )
    return response.json()



@router.post("/video")
async def infer_video(user: str, model_id: str, task: str):
    response = requests.post(
        "http://127.0.0.1:8000/talking-head/inference",
        json={
            "path": f"/data/talking_prod/{user}/{model_id}/generated/{task}/gen-hr.wav"
        },
        headers={"Content-Type": "application/json"},
    )
    return FileResponse(response.json()["path"])
