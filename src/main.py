from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from infra.db import database, metadata, engine
from middleware.auth import AuthMiddleware
from middleware.exception import ExceptionMiddleware
from routes.task import router as taskRouter
from routes.infer import router as inferRouter
from routes.file import router as fileRouter
from routes.user import router as userRouter
from routes.internal import router as internalRouter
from routes.model import router as modelRouter
from routes.train import router as trainRouter

from task.infer_http import infer_text2audio_queue, infer_audio2video_queue, infer_text2video_queue
from routes.train import train_audio_queue, train_video_queue

current_path = os.path.abspath(__file__)
project_root = os.path.dirname(current_path)
os.environ['PROJECT_ROOT'] = project_root

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()  # establish connection
    metadata.create_all(engine)  # init tables
    
    infer_text2audio_queue.schedule_task_processing()
    infer_audio2video_queue.schedule_task_processing()
    infer_text2video_queue.schedule_task_processing()
    train_audio_queue.schedule_task_processing()
    train_video_queue.schedule_task_processing()
    
    yield
    await database.disconnect()


app = FastAPI(lifespan=lifespan)

app.add_middleware(AuthMiddleware)
app.add_middleware(ExceptionMiddleware)

app.include_router(taskRouter)
app.include_router(inferRouter)
app.include_router(fileRouter)
app.include_router(userRouter)
app.include_router(internalRouter)
app.include_router(modelRouter)
app.include_router(trainRouter)
