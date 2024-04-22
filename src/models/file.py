from enum import Enum
from typing import Optional
from infra.db import base_ormar_config
import ormar

class File(ormar.Model):
    ormar_config = base_ormar_config.copy(tablename="file")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    path: str = ormar.String(max_length=255, nullable=False)
    user_id: int = ormar.Integer(foreign_key=True, nullable=False)

def query_file(
    file_id: Optional[int],
    path: Optional[str] = None,
):
    if file_id is not None:
        return File.objects.filter(id=file_id).first()
    if path is not None:
        return File.objects.filter(path=path).first()
    raise ValueError("file_id or path must be provided")

async def create_file(path: str, user_id: int):
    return await File.objects.create(path=path, user_id=user_id)

async def delete_file(file_id: int):
    return await File.objects.delete(id=file_id)
