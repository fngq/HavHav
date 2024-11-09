import os
import logging
from .jable.jable import Jmanager,Jtask
from fastapi import APIRouter, FastAPI,Request
from starlette.responses import FileResponse 
from fastapi import status, HTTPException
from fastapi.staticfiles import StaticFiles

from .midware import init_midware

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

@app.on_event("shutdown")
async def close():
    logger.info(f"task manager shuting down")
    manager.Close()

init_midware(app)

app.mount("/static", StaticFiles(directory=StaticPath), name="static")

@app.get("/")
async def root():
    return FileResponse('index.html') 



    