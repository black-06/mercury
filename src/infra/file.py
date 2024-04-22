from fastapi import UploadFile
import os
import shutil

WORKSPACE = "/data/prod"


async def save_file(
    upload_file: UploadFile,
    work_path: str,
):
    file_path = os.path.join(WORKSPACE, work_path)
    file_dir = os.path.dirname(file_path)

    if not os.path.exists(file_dir):
        os.makedirs(file_dir)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
