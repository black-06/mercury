from fastapi import APIRouter
from pydantic import BaseModel

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


class CreateUserResponse(BaseModel):
    id: int
    account: str


@router.post("/", response_model=CreateUserResponse)
async def create_user(body: LoginBody):
    user = await create_user_model(body.account, body.password)
    return user
