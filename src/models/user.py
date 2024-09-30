from typing import Any, Optional

import ormar

from infra.db import BaseModel, base_ormar_config
from infra.token import get_token, gen_token, set_token


class User(BaseModel):
    ormar_config = base_ormar_config.copy(tablename="user")

    id: Optional[int] = ormar.Integer(primary_key=True, autoincrement=True)
    account: str = ormar.String(max_length=100, unique=True)
    password: str = ormar.String(max_length=100)


def query_user(user_id: Optional[int]):
    q = User.objects
    if user_id is not None:
        q = q.filter(id=user_id)
    list = q.all()
    # remove all password
    for item in list:
        item.password = ""
    return list


def delete_user(user_id: int):
    return User.objects.delete(id=user_id)


async def create_user(account, password):
    user = await User.objects.create(account=account, password=password)
    user.password = ""
    return user


async def update_user(user_id: int, **kwargs: Any):
    t = await user.objects.get(id=user_id)
    user = await t.update(**kwargs)
    user.password = ""
    return user


async def get_user_token(account: str, password: str):
    user = await User.objects.get(account=account, password=password)
    if user is None:
        raise Exception("user not found")
    token = get_token(user.id)
    if token is None:
        token = gen_token(user.id, user.account)
        set_token(user.id, token)
    return token
