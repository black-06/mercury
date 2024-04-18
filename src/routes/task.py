from typing import Optional
from fastapi import APIRouter
import models.task as taskModel


router = APIRouter(
    prefix="/tasks",
)


@router.get("")
async def get_tasks(task_id: Optional[int] = None):
    print("get_tasks, task_id:", task_id)
    res = await taskModel.query_task(task_id)
    print("get_tasks, res:", res)
    return res


@router.post("")
async def create_task():
    return await taskModel.create_task()


@router.put("/{task_id}")
async def update_task(task_id: int, task: taskModel.Task):
    return await taskModel.update_task(task_id, taskModel.Task(status=task.status))


@router.delete("/{task_id}")
async def update_task(task_id: int):
    return await taskModel.delete_task(task_id)
