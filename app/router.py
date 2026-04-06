# -*- coding: utf-8 -*-
import logging
import os
import traceback

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse

from .jable.jable import Jmanager

logger = logging.getLogger("app")
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    "%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",datefmt='%Y-%m-%d,%H:%M:%S'
)
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch) 

StaticPath = "./static"
DownloadPath = "./downloads" 

router = APIRouter(
    prefix='/task',
    tags=['task'],
)


def get_manager(request: Request) -> Jmanager:
    return request.app.state.manager



#@router.on_event("startup")
async def startup_event(app: FastAPI):
    logger.info("router startup")
    app.state.manager = Jmanager(logger, downloadDir=DownloadPath)

#@router.on_event("shutdown")
async def shutdown_event(app: FastAPI):
    logger.info("router closing")
    manager = getattr(app.state, "manager", None)
    if manager is not None:
        manager.close()

@router.get("/add")
async def add_task(request:Request,url:str):
    url = url.strip()
    logger.info(f"add task {url}")
    try:
        ret = get_manager(request).add_task(url)
    except Exception as e :
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail = str(e),
        )
    return {"code":1,"msg":"ok","url":url,"result":ret}

@router.get("/start")
async def start_task(request:Request,name:str):
    ret = get_manager(request).start_task(name)
    return {"code":1,"msg":ret}

@router.get("/list")
async def list_task(request:Request):
    tasks = get_manager(request).task_list()
    return tasks

@router.get("/stop")
async def stop_task(request:Request,name:str):
    ret = get_manager(request).stop_task(name)
    return {"code":1,"msg":ret}

@router.get("/clean")
async def clean(request:Request,name:str):
    r = get_manager(request).clean_task(name)
    return {"code":1,"msg":r}

@router.get("/remove")
async def remove(request:Request,name:str):
    r = get_manager(request).remove_task(name)
    return {"code":1,"msg":r}

@router.get("/flist")
async def file_list(request:Request):
    files = os.listdir(StaticPath)
    dirs = []
    for file in files :
        if os.path.isdir(os.path.join(StaticPath,file)):
            d = {"name":file}
            cover = os.path.join(StaticPath,file,f"{file}.jpg")
            if os.path.exists(cover):
                cover = cover.lstrip(".")
                d["cover"] = cover
            v = os.path.join(StaticPath,file,f"{file}.mp4")
            if os.path.exists(v):
                v = v.lstrip(".")
                d['file'] = v
            dirs.append(d)
    return dirs

filerouter = APIRouter()
@filerouter.get("/{file_path:path}")
async def srvfile(file_path: str, request: Request):
    logger.debug(f"serve file {file_path}")
    full_path = os.path.normpath(os.path.join(DownloadPath, file_path))
    base_path = os.path.abspath(DownloadPath)
    abs_path = os.path.abspath(full_path)
    filename = file_path.split('/')[-1]
    if os.path.commonpath([base_path, abs_path]) != base_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    file_size = os.path.getsize(abs_path)
    logger.debug(f"file size {file_size}")
    headers = {
        "Content-Length": str(file_size),
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'attachment; filename*=UTF-8\'\'{filename}',
        "Content-Type": "application/octet-stream"
    }
    
    return FileResponse(
        path=abs_path,
        headers=headers,
        filename=filename,
    )

class EndpointFilter(logging.Filter):
    def __init__(self,path):
        self.path = path
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find(self.path) == -1

def init_routers(app: FastAPI):
    @app.on_event("startup")
    async def _startup():
        await startup_event(app)

    @app.on_event("shutdown")
    async def _shutdown():
        await shutdown_event(app)

    app.include_router(router, prefix='/api', tags=['v1'])
    app.include_router(filerouter,prefix=DownloadPath.lstrip('.'))
    logging.getLogger("uvicorn.access").addFilter(EndpointFilter(DownloadPath.lstrip('.')))
    # app.mount("/downloads", StaticFiles(directory=DownloadPath), name="downloads")
