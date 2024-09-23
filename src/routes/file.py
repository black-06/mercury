import os
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from starlette.responses import FileResponse, RedirectResponse

from infra.file import upload_cos, get_cos_download_url
from middleware.auth import getUserInfo
from models.file import create_file, File

router = APIRouter(
    prefix="/file",
)


@router.post("/upload", response_model=File)
async def upload_video(
    file: UploadFile,
    model_name: str,
    req: Request,
):
    user = getUserInfo(req)
    user_id = user["user_id"]

    file_model = await create_file(file.filename, user_id)
    upload_cos(file_model.id, file)
    return file_model


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

    if res.cos:
        url = get_cos_download_url(res.id, res.path)
        return RedirectResponse(url=url)
    else:
        base_name = os.path.basename(res.path)
        encoded_basename = quote(base_name)
        return FileResponse(
            res.path,
            media_type="application/octet-stream",
            filename=encoded_basename,
        )
