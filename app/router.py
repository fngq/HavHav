from fastapi import APIRouter, FastAPI
from jable.jable import Jmanager

router = APIRouter(
    prefix='/task',
    tags=['task']
)


manager = Jmanager(logger,StaticPath)


@router.get("/add")
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

@router.get("/list")
async def list_task(request:Request):
    tasks = manager.Tasks()
    return tasks

@router.get("/stop")
async def stop_task(request:Request,url:str):
    ret = manager.StopTask(url)
    return {"code":1,"msg":ret}

@router.get("/list")
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



def router_v1():
    router = APIRouter()
    router.include_router(router, tags=['Task'])
    return router


def init_routers(app: FastAPI):
    app.include_router(router_v1(), prefix='/api/v1', tags=['v1'])