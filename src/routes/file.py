import shutil
import uuid

from fastapi import APIRouter, HTTPException, Request, UploadFile
from starlette.responses import Response, RedirectResponse, FileResponse

from middleware.auth import getUserInfo
from models.file import File, get_cos_download_url, create_cos_file, get_local_path, upload_cos_file

router = APIRouter(
    prefix="/file",
)


@router.post("/upload", response_model=File)
async def upload_video(
    file: UploadFile,
    req: Request,
):
    user = getUserInfo(req)
    key = f"upload/{uuid.uuid4().hex}"
    # write to local
    dest = get_local_path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as writer:
        shutil.copyfileobj(file.file, writer)
    # create and upload
    file_model = await create_cos_file(file.filename, key, user["user_id"])
    upload_cos_file(file_model)
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

    file_path = get_local_path(file.key)
    if not file_path.exists():
        return RedirectResponse(url=get_cos_download_url(file))

    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=file.name,
    )
