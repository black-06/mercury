import json
from infra import logger
from infra.r import r
import time
from typing import Callable, Any
import asyncio

from models.task import Task, TaskStatus, create_task, update_task


class QTask():
    def __init__(self, task_id, payload: dict, max_retry: int = 0):
        self.payload = payload
        self.task_id = task_id
        self.retry_count = 0
        self.max_retry = max_retry
    
    @classmethod
    def from_json(cls, json_str):
        data = json.loads(json_str)
        return cls(**data)

class TaskQueue():
    def __init__(self, name, handler: Callable[[int, any], TaskStatus | None], handle_sleep:int = 60 * 20, retry_sleep:int = 60):
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
        self._schedule_task_processing()
        
    def _generate_key(self):
        """Generates a unique key for the queue."""
        return f"rqueue_{self.name}"
    
    def _get_queue(self):
        """Retrieves the queue from the redis."""
        queue_data = r.get(self.key) or []
        return [QTask.from_json(task) for task in queue_data]
    
    def __set_queue(self):
        """Updates the queue in the redis."""
        r.set(self.key, json.dumps( self.task_list ), ex=-1)
    
    def _schedule_task_processing(self):
        """Schedules the task processing in a separate thread or process."""
        asyncio.create_task(self._process_tasks())
        
            
    async def _process_tasks(self):
        """Processes tasks in the queue."""
        while True:
            if len(self.task_list) == 0:
                time.sleep(5)
                continue
            
            task = self.task_list.pop(0)
            
            try:
                logger.debug("processing task: %s", task)
                
                task_status = await self.handler(task.task_id,task.payload)
                update_task(
                    task.task_id, 
                    status=task_status if task_status else TaskStatus.SUCCESS
                )
                
                self._save_queue()
                logger.debug("process task success: %s", task)
                time.sleep(self.handle_sleep)
            except Exception as e:
                logger.error("process task error, task: %s, error: %s", task, e)
                task.retry_count += 1
                if task.retry_count > task.max_retry: 
                    await update_task(task.task_id, status=TaskStatus.FAILED, res={
                        "message": str(e),
                    })
                else: 
                    self.task_list.append(task)
                    
                self.__set_queue()
                time.sleep(self.retry_sleep)
                
    async def append(self, payload: dict, max_retry: int = 0) -> Task:
        """Appends a new task to the queue. return model Task"""
        task = await create_task()
        qt = QTask(task_id=task.id, payload=payload, max_retry=max_retry)
        
        self.task_list.append(qt)
        self.__set_queue()
        return task