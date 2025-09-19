from jable import Jmanager
import logging
from queue import Queue,Empty
from concurrent.futures import ThreadPoolExecutor
import threading
import time


logger = logging.getLogger('jlog')
logger.setLevel(logging.DEBUG)
DownloadPath = "./downloads" 

def test_jable_laod_history():
    print(f"test jable in {DownloadPath}")
    manager = Jmanager(logger,downloadDir=DownloadPath)
    manager.init()

def test_queue():
    max_worker = 2
    exe = ThreadPoolExecutor(max_workers=max_worker)
    q = Queue()
    def put_q(i):
        print(f"put {i}")
        q.put(i)
    
    i = 0
    def run():
        print("run")
        while True:
            print(f"poll {i}")
            item = q.get()
            print(f"queue get {item}")
            time.sleep(0.5)


    exe.submit(run)
    exe.submit(run)
    put_q(1)
    time.sleep(3)
    put_q(2)
    time.sleep(1)


    
if __name__ == "__main__":
    test_queue()
