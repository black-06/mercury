import os
import sys
import traceback
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from infra.logger import logger

class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            root_dir = os.environ.get("PROJECT_ROOT")
            middleware_dir = os.path.dirname(os.path.abspath(__file__))
            
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb = traceback.extract_tb(exc_traceback)
            
            # 打印异常发生时的文件名和行号（仅限于项目根目录下的文件，忽略middleware中的文件）
            error_message = f"{exc_type.__name__}: {exc_value}"
            for filename, line_number in [(filename, line_number) \
                for filename, line_number, _, _  in tb \
                if filename.startswith(root_dir) and not filename.startswith(middleware_dir) ] :
                error_message += f"\n | error in {filename} at line {line_number}"
            
            logger.error(f"{error_message}")
            
            return JSONResponse(
                status_code=500,
                content={"detail": f"{exc_type.__name__}: {exc_value}"}
            )