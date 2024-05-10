from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from urllib.parse import quote
import os
from starlette.responses import FileResponse
from infra.file import WORKSPACE, save_file
from middleware.auth import getUserInfo
import models.file as FileModel

router = APIRouter(
    prefix="/file",
)


@router.post("/upload", response_model=FileModel.File)
async def upload_video(
    file: UploadFile,
    model_name: str,
    req: Request,
):
    user = getUserInfo(req)
    user_id = user["user_id"]

    raw_dir_path = os.path.join(
        WORKSPACE,
        str(user_id),
        model_name,
        "_raw",
    )

    file_path = os.path.join(raw_dir_path, file.filename)

    await save_file(file, file_path)
    return await FileModel.create_file(file_path, user_id)

class DownloadResponse(Response):
    media_type = "application/octet-stream"
    schema = {}

@router.get("/download", response_class=DownloadResponse)
async def download_file(file_id: int, req: Request):
    user = getUserInfo(req)
    user_id = user["user_id"]

    res = await FileModel.query_file(file_id)
    if not res:
        raise HTTPException(status_code=404, detail="file not found")

    if res.user_id != user_id:
        raise HTTPException(status_code=403, detail="no permission")
    base_name = os.path.basename(res.path)
    encoded_basename = quote(base_name)

    return FileResponse(
        res.path,
        media_type="application/octet-stream",
        filename=encoded_basename,
    )
