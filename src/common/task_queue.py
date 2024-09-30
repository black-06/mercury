import asyncio
import json
from typing import Callable, Union

from infra.r import r
from infra.logger import logger
from models.task import Task, TaskStatus, create_task, query_task, update_task


class QTask:
    def __init__(self, task_id: int, payload: str, max_retry: int = 0):
        self.payload = payload
        self.task_id = task_id
        self.retry_count = 0
        self.max_retry = max_retry

    @classmethod
    def from_json(cls, j):
        return cls(task_id=j["task_id"], payload=j["payload"], max_retry=j["max_retry"])

    def to_dict(self):
        return {
            "payload": self.payload,
            "task_id": self.task_id,
            "retry_count": self.retry_count,
            "max_retry": self.max_retry,
        }


class TaskQueue:
    def __init__(
        self,
        name: str,
        handler: Callable[[int, any], Union[TaskStatus, None]],
        handle_sleep: int = 5,
        retry_sleep: int = 5,
        max_parallel_tasks: int = 1,
    ):
        """
        name: 区分任务队列
        handler: 处理任务的方法
        handle_sleep: 上一个任务完成后，开始下一个任务的时间间隔
        retry_sleep: 处理失败后，重试的时间间隔
        """
        self.name = name
        self.handler = handler
        self.handle_sleep = handle_sleep
        self.retry_sleep = retry_sleep
        self.key = self._generate_key()
        self.task_list = self._get_queue()
        self.max_parallel_tasks = max_parallel_tasks
        self.active_tasks = []

    def _generate_key(self):
        """Generates a unique key for the queue."""
        return f"rqueue_{self.name}"

    def _get_queue(self):
        """Retrieves the queue from the redis."""
        queue_data_b = r.get(self.key) or b"[]"
        queue_data = json.loads(queue_data_b)
        return [QTask.from_json(task) for task in queue_data]

    def __set_queue(self):
        """Updates the queue in the redis."""
        r.set(self.key, json.dumps([task.to_dict() for task in self.task_list]), ex=None)

    def schedule_task_processing(self):
        """Schedules the task processing in a separate thread or process."""
        asyncio.create_task(self._process_tasks())

    async def _process_tasks(self):
        """Processes tasks in the queue."""
        while True:
            if len(self.task_list) == 0:
                await asyncio.sleep(5)
                continue

            while len(self.active_tasks) < self.max_parallel_tasks and self.task_list:
                qtask = self.task_list.pop(0)
                task = asyncio.create_task(self._process_single_task(qtask))
                self.active_tasks.append(task)
                task.add_done_callback(lambda t: self.active_tasks.remove(t))

            await asyncio.sleep(1)

    async def _process_single_task(self, qtask: QTask):
        try:
            logger.debug("processing task: %s", qtask.to_dict())

            task_status = await self.handler(qtask.task_id, qtask.payload)
            await update_task(qtask.task_id, status=task_status if task_status else TaskStatus.SUCCEEDED)

            self.__set_queue()
            logger.debug("process task success: %s", qtask.task_id)
            await asyncio.sleep(self.handle_sleep)
        except Exception as e:
            logger.error("process task error, task: %s, error: %s", qtask.to_dict(), e)
            qtask.retry_count += 1
            if qtask.retry_count > qtask.max_retry:
                tasks = await query_task(task_id=qtask.task_id)
                if len(tasks) == 1:
                    task = tasks[0]
                    res = task.res
                    res["message"] = str(e)
                    await update_task(qtask.task_id, status=TaskStatus.FAILED, res=res)
            else:
                self.task_list.append(qtask)
            self.__set_queue()
            await asyncio.sleep(self.retry_sleep)

    async def append(self, payload: str, max_retry: int = 0) -> Task:
        """Appends a new task to the queue. return model Task"""
        if len(self.task_list) >= 10:
            raise Exception("队列超出最大长度限制")
        task = await create_task()
        qt = QTask(task_id=task.id, payload=payload, max_retry=max_retry)

        self.task_list.append(qt)
        self.__set_queue()
        return task
