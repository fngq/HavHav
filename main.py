from app.server import app
import logging
import threading
import uvicorn
import webbrowser


def main():
    host = "127.0.0.1"
    port = 8090
    url = f"http://{host}:{port}"
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, port=port, host=host, log_level='debug')

if __name__ == "__main__":
    main()
