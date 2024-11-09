from app.server import app
import logging
import uvicorn

def main():
    uvicorn.run(app,port=8090,host="127.0.0.1")

if __name__ == "__main__":
    main()