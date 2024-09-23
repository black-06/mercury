import os
import shutil

from fastapi import UploadFile
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client

from utils.file import createDir

WORKSPACE = "/data/prod"


async def save_file(
    upload_file: UploadFile,
    file_path: str,
):
    file_dir = os.path.dirname(file_path)

    createDir(file_dir)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)


def get_file_absolute_path(file_path: str):
    return os.path.join(WORKSPACE, file_path)


secret_id = os.environ.get("COS_SECRET_ID")
secret_key = os.environ.get("COS_SECRET_KEY")
region = os.environ.get("COS_REGION")
bucket = os.environ.get("COS_BUCKET")

config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
client = CosS3Client(config)


def upload_cos(file_id: int, file: UploadFile):
    return client.upload_file(
        Bucket=bucket,
        Key=str(file_id),
        Body=file.file,
    )


def download_cos(file_id: int, file_path: str):
    return client.download_file(
        Bucket=bucket,
        Key=str(file_id),
        DestFilePath=file_path,
    )


def get_cos_download_url(file_id: int, file_name: str):
    return client.get_presigned_url(
        Bucket=bucket,
        Key=str(file_id),
        Method="GET",
        Expired=300,
        Params={
            "response-content-type": "application/octet-stream",
            "response-content-disposition": f"attachment; filename={file_name}",
        },
    )
