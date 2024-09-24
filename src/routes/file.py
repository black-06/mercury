from fastapi import APIRouter, HTTPException, Request, UploadFile
from starlette.responses import Response, RedirectResponse

from infra.file import upload_cos, get_cos_download_url
from middleware.auth import getUserInfo
from models.file import File, create_file

router = APIRouter(
    prefix="/file",
)


@router.post("/upload", response_model=File)
async def upload_video(
    file: UploadFile,
    req: Request,
):
    user = getUserInfo(req)
    user_id = user["user_id"]

    file_model = await create_file(name=file.filename, user_id=user_id)
    upload_cos(file_model.id, file)
    return file_model


class DownloadResponse(Response):
    media_type = "application/octet-stream"
    schema = {}


@router.get("/download", response_class=DownloadResponse)
async def download_file(file_id: int, req: Request):
    user = getUserInfo(req)
    user_id = user["user_id"]

    file: File = File.objects.filter(id=file_id, user_id=user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="file not found")

    url = get_cos_download_url(file.id, file.name)
    return RedirectResponse(url=url)
