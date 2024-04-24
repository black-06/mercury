from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, status
from infra.token import check_token, decode_token
from infra.logger import logger


def getUserInfo(request: Request):
    return getattr(request.state, "user", None)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/user/login":
            return await call_next(request)

        token = request.headers.get("Authorization")

        if not token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "missing token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = token.split(" ")[1]
        res = check_token(token)
        if not res:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid authentication credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        userInfo = decode_token(token)
        request.state.user = userInfo

        return await call_next(request)
