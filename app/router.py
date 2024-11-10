# -*- coding: utf-8 -*-
from fastapi import APIRouter, FastAPI,Request,HTTPException,status
import traceback
from .jable.jable import Jmanager,Jtask
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",datefmt='%Y-%m-%d,%H:%M:%S'
)
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch) 

StaticPath = "./static"

manager = Jmanager(logger,downloadDir="./downloads")

@asynccontextmanager
async def lifespan(app:FastAPI):
    manager.init()
    yield
    logger.info("router closing")
    manager.close()

router = APIRouter(
    prefix='/task',
    tags=['task'],
    lifespan = lifespan,
)

@router.get("/add")
async def add_task(request:Request,url:str):
    url = url.strip()
    logger.info(f"add task {url}")
    try:
        ret = manager.add_task(url)
    except Exception as e :
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail = str(e),
        )
    return {"code":1,"msg":"ok","url":url}

@router.get("/list")
async def list_task(request:Request):
    logger.info("task list")
    tasks = manager.task_list()
    return tasks

@router.get("/stop")
async def stop_task(request:Request,url:str):
    ret = manager.StopTask(url)
    return {"code":1,"msg":ret}

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


def init_routers(app: FastAPI):
    app.include_router(router, prefix='/api', tags=['v1'])