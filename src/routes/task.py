from typing import List, Optional
from fastapi import APIRouter
import models.task as taskModel


router = APIRouter(
    prefix="/tasks",
)


@router.get("", response_model=List[taskModel.Task])
async def get_tasks(task_id: Optional[int] = None):
    res = await taskModel.query_task(task_id)
    return res


@router.post("", response_model=taskModel.Task)
async def create_task():
    return await taskModel.create_task()


@router.put("/{task_id}", response_model=taskModel.Task)
async def update_task(task_id: int, task: taskModel.Task):
    return await taskModel.update_task(task_id, status=task.status)


@router.delete("/{task_id}", response_model=int)
async def delete_task(task_id: int):
    return await taskModel.delete_task(task_id)
