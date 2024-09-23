from typing import Optional
from infra.db import BaseModel, base_ormar_config
import ormar

class File(BaseModel):
    ormar_config = base_ormar_config.copy(tablename="file")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    path: str = ormar.String(max_length=255, nullable=False)
    user_id: int = ormar.Integer(foreign_key=True, nullable=False)
    cos: bool = ormar.Boolean(default=True, nullable=False)

def query_file(
    file_id: Optional[int],
    path: Optional[str] = None,
):
    q = File.objects
    if file_id is not None:
        q = q.filter(id=file_id)
    if path is not None:
        q = q.filter(path=path)
    return q.first()

async def create_file(path: str, user_id: int):
    return await File.objects.create(path=path, user_id=user_id)

async def delete_file(file_id: int):
    return await File.objects.delete(id=file_id)
