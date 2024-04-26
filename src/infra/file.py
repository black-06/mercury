from fastapi import UploadFile
import os
import shutil
from utils.file import createDir

WORKSPACE = "/data/prod"


async def save_file(
    upload_file: UploadFile,
    work_path: str,
):
    file_path = os.path.join(WORKSPACE, work_path)
    file_dir = os.path.dirname(file_path)

    createDir(file_dir)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
