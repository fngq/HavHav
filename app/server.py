# -*- coding: utf-8 -*- 

from .jable.jable import Jmanager,Jtask
from fastapi import FastAPI
from starlette.responses import FileResponse 
from fastapi.staticfiles import StaticFiles

from .midware import init_midware
from .router import init_routers,StaticPath


app = FastAPI(docs_url=None,
    redoc_url=None,
    openapi_url=None,)

init_midware(app)

init_routers(app)

app.mount("/static", StaticFiles(directory=StaticPath), name="static")

@app.get("/")
async def root():
    return FileResponse('index.html') 

    