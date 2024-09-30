import os
from pathlib import Path
from typing import Optional

import ormar
from qcloud_cos import CosConfig, CosS3Client

from infra.db import BaseModel, base_ormar_config

cos_secret_id = os.environ.get("COS_SECRET_ID")
cos_secret_key = os.environ.get("COS_SECRET_KEY")
cos_region = os.environ.get("COS_REGION")
cos_bucket = os.environ.get("COS_BUCKET")
cos_config = CosConfig(Region=cos_region, SecretId=cos_secret_id, SecretKey=cos_secret_key)
cos_client = CosS3Client(cos_config)
cos_local = Path("/cos")

# 之前没有上 COS 的目录
WORKSPACE = "/data/prod"


class File(BaseModel):
    ormar_config = base_ormar_config.copy(tablename="file")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    name: str = ormar.String(max_length=255, nullable=False, description="raw file name")
    key: str = ormar.String(max_length=255, nullable=True, description="file key in cos")
    user_id: int = ormar.Integer(foreign_key=True, nullable=False)


def query_file(file_id: Optional[int], path: Optional[str] = None):
    q = File.objects
    if file_id is not None:
        q = q.filter(id=file_id)
    if path is not None:
        q = q.filter(path=path)
    return q.first()


def get_local_path(key: str) -> Path:
    # 旧的目录, 保持原状
    if key.startswith(WORKSPACE):
        return Path(key)
    path = cos_local / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


async def create_cos_file(name: str, key: str, user_id: int) -> File:
    return await File.objects.create(name=name, key=key, user_id=user_id)


def upload_cos_file(file: File):
    cos_client.upload_file(Bucket=cos_bucket, Key=file.key, LocalFilePath=get_local_path(file.key))


def download_cos_file(key: str) -> Path:
    dest = get_local_path(key)
    if not dest.exists():
        cos_client.download_file(Bucket=cos_bucket, Key=key, DestFilePath=dest)
    return dest


def get_cos_download_url(file: File):
    return cos_client.get_presigned_url(
        Bucket=cos_bucket,
        Key=file.key,
        Method="GET",
        Expired=300,
        Params={
            "response-content-type": "application/octet-stream",
            "response-content-disposition": f"attachment; filename={file.name}",
        },
    )
