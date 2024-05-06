from infra.r import r
from datetime import datetime, timedelta
import jwt

_secret_key = "mercurymercury"
_redis_key = "mercury_token"
_algorithm = "HS256"
_expire_time = 7 * 24 * 60 * 60


def gen_token_key(user_id: int):
    return f"{_redis_key}_{user_id}"


def get_token(user_id: int):
    return r.get(gen_token_key(user_id))


def gen_token(user_id: int, username: str):
    payload_data = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(days=7),
    }
    token = jwt.encode(payload_data, _secret_key, algorithm=_algorithm)
    return token


def set_token(user_id: int, token: str):
    return r.set(gen_token_key(user_id), token, ex=_expire_time)


def clear_token(user_id: int):
    return r.delete(gen_token_key(user_id))


def check_token(token: str):
    res = decode_token(token)
    # check if token expired
    exp_datetime = datetime.fromtimestamp(res["exp"])
    return datetime.utcnow() < exp_datetime


def decode_token(token: str):
    return jwt.decode(token, _secret_key, algorithms=[_algorithm])
