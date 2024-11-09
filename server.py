import os
import logging
from download import Jmanager,Jtask
from fastapi import APIRouter, FastAPI,Request
from starlette.responses import FileResponse 
from fastapi import status, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware

logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",datefmt='%Y-%m-%d,%H:%M:%S'
)
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch) 
# fh = logging.FileHandler(filename='./server.log')
# fh.setFormatter(formatter)
# logger.addHandler(fh)


StaticPath = "./static"

app = FastAPI(docs_url=None,
    redoc_url=None,
    openapi_url=None,)

router = APIRouter()

app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

app.mount("/static", StaticFiles(directory=StaticPath), name="static")

manager = Jmanager(logger,StaticPath)

@app.middleware("http")
async def auth(request:Request,call_next):

    resp = await call_next(request)
    resp.headers["X-token"] = "abc321"
    return resp

@app.on_event("shutdown")
async def close():
    logger.info(f"task manager shuting down")
    manager.Close()

@app.get("/")
async def root():
    return FileResponse('index.html') 

@app.get("/api/task/add")
async def add_task(request:Request,url:str):
    logger.info(f"add task {url}")
    try:
        manager.CreateTask(url,0)
    except Exception as e :
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail = str(e),
        )
    return {"code":1,"msg":"ok","url":url}

@app.get("/api/task/list")
async def list_task(request:Request):
    tasks = manager.Tasks()
    return tasks

@app.get("/api/task/stop")
async def stop_task(request:Request,url:str):
    ret = manager.StopTask(url)
    return {"code":1,"msg":ret}

@app.get("/api/file/list")
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


    