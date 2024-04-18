from typing import Optional
import ormar
from infra.db import database, metadata, base_ormar_config


class Task(ormar.Model):
    ormar_config = base_ormar_config.copy(tablename="task")

    id: Optional[int] = ormar.Integer(primary_key=True, autoincrement=True)
    status: Optional[int] = ormar.Integer(default=0)  # TODO enums
    res: any = ormar.JSON(default={})


def query_task(task_id: Optional[int]):
    if task_id is None:
        return Task.objects.all()  # TODO this is sloppy
    return Task.objects.filter(id=task_id).all()


def delete_task(task_id: int):
    return Task.objects.delete(id=task_id)


async def create_task():
    return await Task.objects.create(status=1, res={})


async def update_task(task_id: int, task: Task):
    t = await Task.objects.get(id=task_id)
    t.status = task.status
    return await t.update()
