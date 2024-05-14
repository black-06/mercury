import datetime
from typing import Any, Optional
import ormar
from infra.db import BaseModel, base_ormar_config
from enum import Enum


class TaskStatus(int, Enum):
    UNKNOWN = 0
    PENDING = 1
    SUCCEEDED = 2
    FAILED = 3


class Task(BaseModel):
    ormar_config = base_ormar_config.copy(tablename="task")

    id: Optional[int] = ormar.Integer(primary_key=True, autoincrement=True)
    status: Optional[TaskStatus] = ormar.Enum(enum_class=TaskStatus)
    res: any = ormar.JSON(default={})
    create_time: datetime.datetime = ormar.DateTime(default=datetime.datetime.now)


def query_task(task_id: Optional[int]):
    q = Task.objects
    if task_id is not None:
        q = q.filter(id=task_id)
    return q.all()


def delete_task(task_id: int):
    return Task.objects.delete(id=task_id)


async def create_task():
    return await Task.objects.create(status=TaskStatus.PENDING, res={})


async def update_task(task_id: int, **kwargs: Any):
    t = await Task.objects.get(id=task_id)
    return await t.update(**kwargs)

