from contextlib import asynccontextmanager
from fastapi import FastAPI
from infra.db import database, metadata, engine
from middleware.auth import AuthMiddleware
from routes.task import router as taskRouter
from routes.infer import router as inferRouter
from routes.file import router as fileRouter
from routes.user import router as userRouter
from routes.internal import router as internalRouter
from routes.model import router as modelRouter


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()  # establish connection
    metadata.create_all(engine)  # init tables
    yield
    await database.disconnect()


app = FastAPI(lifespan=lifespan)

app.add_middleware(AuthMiddleware)

app.include_router(taskRouter)
app.include_router(inferRouter)
app.include_router(fileRouter)
app.include_router(userRouter)
app.include_router(internalRouter)
app.include_router(modelRouter)
