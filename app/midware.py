from fastapi import FastAPI,Request
from fastapi.middleware.gzip import GZipMiddleware



async def auth(request:Request,call_next):
    resp = await call_next(request)
    resp.headers["X-token"] = "abc321"
    return resp

def init_midware(app:FastAPI):
    # app.middleware('http')(auth)
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
    
    return 