from typing import Any, Optional

import ormar

from infra.db import BaseModel, base_ormar_config


class Model(BaseModel):
    ormar_config = base_ormar_config.copy(tablename="model")

    id: Optional[int] = ormar.Integer(primary_key=True, autoincrement=True)
    name: Optional[str] = ormar.String(max_length=100, unique=True)
    audio_model: Optional[str] = ormar.String(default="", max_length=100, description="RVC model path")
    audio_config: any = ormar.JSON(default={})
    video_model: Optional[str] = ormar.String(default="", max_length=100, description="talking head model path")
    video_config: any = ormar.JSON(default={})


def query_model(name: Optional[str] = None, model_id: Optional[int] = None):
    q = Model.objects
    if name is not None:
        q = q.filter(name=name)
    if model_id is not None:
        q = q.filter(id=model_id)
    return q.all()


async def create_model(**kwargs: Any):
    return await Model.objects.create(**kwargs)


async def update_model(model_id: int, **kwargs: Any):
    t = await Model.objects.get(id=model_id)
    model = await t.update(**kwargs)
    return model


def delete_model(model_id: int):
    return Model.objects.delete(id=model_id)
