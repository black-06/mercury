from fastapi import UploadFile, HTTPException
from urllib.parse import quote
from fastapi.responses import StreamingResponse 
import os
import shutil

WORKSPACE = "/data/talking-prod"

async def save_file(
    upload_file: UploadFile,
    work_path: str,
):
    file_path = os.path.join(WORKSPACE, work_path)
    file_dir = os.path.dirname(file_path)
    
    if not os.path.exists(file_dir):  
        os.makedirs(file_dir) 
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)



async def send_file(
    work_path: str,
):  
    file_path = os.path.join(WORKSPACE, work_path)
    base_name = os.path.basename(file_path)
    encoded_basename = quote(base_name) 
    
    if not os.path.isfile(file_path):  
        raise HTTPException(status_code=404, detail=f"File not found")  
      
    async def file_stream():  
        with open(file_path, "rb") as file:  
            while True:  
                chunk = file.read(4096) 
                if not chunk:  
                    break  
                yield chunk  
                
    headers = {  
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_basename}"  
    } 
    return StreamingResponse(file_stream(), media_type="application/octet-stream", headers=headers)  
  
  

