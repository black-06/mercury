from fastapi import APIRouter, Request
from pydantic import BaseModel
from middleware.auth import getUserInfo
from models.user import get_user_token, create_user as create_user_model


router = APIRouter(
    prefix="/user",
)


class LoginBody(BaseModel):
    account: str
    password: str


@router.post("/login")
async def login(
    body: LoginBody,
):
    token = await get_user_token(body.account, body.password)
    return token


@router.post("/")
async def create_user(body: LoginBody, request: Request):
    user = getUserInfo(request)

    token = await create_user_model(body.account, body.password)
    return token
