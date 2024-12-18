from jable import Jmanager
import logging
logger = logging.getLogger('jlog')
logger.setLevel(logging.DEBUG)
DownloadPath = "./downloads" 

def test_jable_laod_history():
    print(f"test jable in {DownloadPath}")
    manager = Jmanager(logger,downloadDir=DownloadPath)
    manager.init()

if __name__ == "__main__":
    test_jable_laod_history()
