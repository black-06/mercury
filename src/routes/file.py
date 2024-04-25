from fastapi import APIRouter, Request, UploadFile
from urllib.parse import quote
import os
from starlette.responses import FileResponse
from infra.file import WORKSPACE, save_file
from middleware.auth import getUserInfo
import models.file as FileModel

router = APIRouter(
    prefix="/file",
)


@router.post("/upload")
async def upload_video(
    file: UploadFile,
    model_id: str,
    req: Request,
):
    user = getUserInfo(req)
    user_id = user["user_id"]

    raw_dir_path = os.path.join(
        str(user_id),
        model_id,
        "task",
        "raw",
    )

    # make dir if not exist
    os.makedirs(raw_dir_path, exist_ok=True)

    file_path = os.path.join(raw_dir_path, file.filename)

    await save_file(file, file_path)
    return await FileModel.create_file(file_path, user_id)


@router.get("/download")
async def download(file_id: int, req: Request):
    user = getUserInfo(req)
    user_id = user["user_id"]

    res = await FileModel.query_file(file_id)
    if not res:
        return {"message": "file not found"}

    if res.user_id != user_id:
        return {"message": "no permission"}
    base_name = os.path.basename(res.path)
    encoded_basename = quote(base_name)

    return FileResponse(
        os.path.join(WORKSPACE, res.path),
        media_type="application/octet-stream",
        filename=encoded_basename,
    )
