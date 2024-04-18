from contextlib import asynccontextmanager
from fastapi import FastAPI
from infra.db import database, metadata, engine
from routes.task import router as taskRouter
from routes.infer import router as inferRouter


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()  # establish connection
    metadata.create_all(engine)  # init tables
    yield
    await database.disconnect()


app = FastAPI(lifespan=lifespan)

app.include_router(taskRouter)
app.include_router(inferRouter)
