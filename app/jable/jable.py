import requests
import time
import os
import shutil
from urllib.parse import urlparse
import m3u8
import functools
from typing import Type, Union, Tuple
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad,unpad
import logging

import threading
from collections import OrderedDict
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

from fake_useragent import UserAgent
import traceback
from typing import OrderedDict as TOrderedDict
import base64

from app.domain.models import DownloadInfo, TaskInfo, TaskStatus
from app.providers.jable import JableProvider
from app.storage.task_store import TaskStore

jlogger = logging.getLogger('jlog')
jlogger.setLevel(logging.DEBUG)
 
ua = UserAgent().random

header = {"User-Agent":ua}
REQUEST_TIMEOUT = 30

def retry(
    max_attempts: int = 3,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    delay: float = 1.0,
    logger = jlogger
):
    """
    重试装饰器
    Args:
        max_attempts: 最大重试次数
        exceptions: 需要重试的异常类型
        delay: 初始延迟时间（秒）
        logger: 日志记录器
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _delay = delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    if logger:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {str(e)}"
                        )
                    
                    if attempt < max_attempts - 1:  # 不是最后一次尝试
                        if logger:
                            logger.info(f"Retrying in {_delay:.1f} seconds...")
                        time.sleep(_delay)
                        
            # 所有重试都失败后
            if logger:
                logger.error(
                    f"All {max_attempts} attempts failed for {func.__name__}"
                )
            raise last_exception
            
        return wrapper
    return decorator

class InvalidHost(Exception):
    def __init__(self,host):
        super().__init__()
        self.host = host
    def __str__(self):
        return f"unsupported host {self.host}"

class InvalidUrlPath(Exception):
    pass
class M3u8NotFound(Exception):
    pass
class TaskCanceled(Exception):
    pass

def AESDecrypt(cipher_text, key, iv):
    cipher_text = pad(data_to_pad=cipher_text, block_size=AES.block_size)
    aes = AES.new(key=key, mode=AES.MODE_CBC, iv=iv)
    cipher_text = aes.decrypt(cipher_text)
    # clear_text = unpad(padded_data=cipher_text, block_size=AES.block_size)
    return cipher_text


class Jmanager():
    def __init__(self,logger = jlogger,downloadDir = "./downloads",workers = 2):
        self.logger = logger
        self.downloadDir = downloadDir
        self.task_store = TaskStore(downloadDir, logger)
        self.provider = JableProvider(user_agent=ua, logger=logger)
        self.tasks : TOrderedDict[str,Jtask] = OrderedDict()
        self.taskq = Queue(maxsize=10) # 任务队列
        self.max_worker = workers
        self.executer = ThreadPoolExecutor(max_workers=self.max_worker)
        self._tasks_lock = threading.RLock()
        self._queued = set()
        self._closed = False
        self.init()

    def init(self):
        self.task_store.ensure_root()
        self.logger.info(f"jmanager thread {threading.get_ident()},max worker {self.max_worker}")
        for i in range(self.max_worker):
            self.executer.submit(self.run_task)
        self.load_history()

    def run_task(self):
        self.logger.info(f"jtask thread ready in thread {threading.get_ident()}")
        while True:
            self.logger.info(f"Current queue size: {self.taskq.qsize()}")
            task = self.taskq.get()
            if task is None:
                self.taskq.task_done()
                self.logger.info("empty task,exit")
                break
            self.logger.info(f"get new task {task.name}")
            try:
                self.logger.info(f"new task in: {task.url}")
                task.run()
            finally:
                with self._tasks_lock:
                    self._queued.discard(task.name)
                self.taskq.task_done()

            time.sleep(0.5)
        self.logger.info("Download thread exit")
    
    def load_history(self):
        tasks = []
        self.logger.debug(f"load history from {self.downloadDir}")
        for item in os.scandir(self.downloadDir):
            if not item.is_dir():
                continue
            task = self.load_task(item.path)
            if task :
                tasks.append(task)
        self.logger.debug(f"load {len(tasks)} tasks")
        tasks.sort(key=lambda x: x.info.start_time if x.info.start_time else 0, reverse=True)
        with self._tasks_lock:
            for t in tasks :
                self.tasks[t.name] = t
            
    def load_task(self,path):
        loaded = self.task_store.load_task_info(path)
        if loaded is None:
            return None
        metainfo, info = loaded
        t = Jtask(
            None,
            logger=self.logger,
            downloadDir=self.downloadDir,
            task_store=self.task_store,
            provider=self.provider,
        )
        t.undesc(metainfo, info)
        return t

    def dirName(self):
        return self.downloadDir

    def task_list(self):
        ts = []
        with self._tasks_lock:
            for _, v in self.tasks.items():
                ts.append(v.desc())
        ts.reverse()
        return ts

    def _enqueue_task(self, task):
        with self._tasks_lock:
            if self._closed:
                raise RuntimeError("task manager is closed")
            if task.status == TaskStatus.Running or task.name in self._queued:
                return 0
            task.set_status(TaskStatus.Pending)
            self._queued.add(task.name)
        task.save_metainfo()
        self.taskq.put(task)
        self.logger.info(f"add task {self.taskq.qsize()}/{len(self.tasks)} {task.url}")
        return 1
    
    def start_task(self,name):
        with self._tasks_lock:
            if name not in self.tasks :
                return 0
            t = self.tasks[name]
        return self._enqueue_task(t)

    def add_task(self,url):
        purl = urlparse(url)
        if not purl.hostname == "jable.tv":
             raise InvalidHost(purl.hostname)
        
        t = Jtask(
            url=url,
            logger=self.logger,
            downloadDir=self.downloadDir,
            task_store=self.task_store,
            provider=self.provider,
        )
        with self._tasks_lock:
            if t.name in self.tasks:
                t = self.tasks[t.name]
            else :
                self.tasks[t.name] = t
        self._enqueue_task(t)
        return t.desc()
    
    def stop_task(self,name):
        with self._tasks_lock:
            if name not in self.tasks :
                return 0
            t = self.tasks[name]
        t.stop()
        return 1

    # clean temprary files created during download
    def clean_task(self,name):
        with self._tasks_lock:
            if name not in self.tasks:
                return 0
            t = self.tasks[name]
        t.clean()
        return 1

    def remove_task(self,name):
        with self._tasks_lock:
            if name not in self.tasks:
                return 0
            t = self.tasks[name]
        ret = t.remove()
        if ret:
            with self._tasks_lock:
                self.tasks.pop(name, None)
                self._queued.discard(name)
        return ret



    def close(self):
        if self._closed:
            return
        self._closed = True
        self.logger.info("jtask thread exiting")
        for i in range(self.max_worker):
            self.taskq.put(None)
        self.executer.shutdown(wait=False)


class Jtask():
    def __init__(self,url:str,logger=jlogger,downloadDir='',task_store=None,provider=None):
        self._url = url
        self.logger = logger
        self._downloadDir = downloadDir
        self.info = TaskInfo()
        self.downloadinfo = DownloadInfo()
        self._session = requests.sessions.Session()
        self.task_store = task_store or TaskStore(downloadDir, logger)
        self.provider = provider or JableProvider(user_agent=ua, logger=logger)

    @property
    def destDir(self):
        return os.path.join(self._downloadDir,self.name)
    @property
    def url(self):
        return self._url
    @property
    def status(self):
        return self.info.status

    def set_status(self,status):
        self.info.status = status
    # get name from url
    @property
    def name(self):
        if not self.info.name:
            items = urlparse(self.url).path.split('/')
            if len(items) > 1:
                self.info.name = items[-2]
            else :
                raise InvalidUrlPath
        return self.info.name
    
    @retry(max_attempts=5,exceptions=(ConnectionResetError, requests.exceptions.RequestException))
    def download(self,url,dest='',force = False):
        if not force and dest and os.path.exists(dest):
            return 
        response = self._session.get(url,headers=header,timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content = response.content
        if dest :
            with open(dest,"wb+") as f :
                f.write(content)
        return content

    @retry(max_attempts=5,exceptions=(ConnectionResetError, requests.exceptions.RequestException, ValueError))
    def download_ts(self,url,dest,ci,force=False):
        if not force and os.path.exists(dest):
            return 
        response = self._session.get(url,headers=header,timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content = response.content
        if ci :
            content = ci.decrypt(content)
            content = unpad(content,AES.block_size)
        with open(dest,'wb+') as f :
            f.write(content)
        return content

    def _get_m3u8(self,m3u8_url:str):
        # find m3u8 in javascript 
        self.downloadinfo.m3u8_url = m3u8_url
        
        self.check_cancel()

        m3u8file = os.path.join(self.destDir,f"{self.name}.m3u8")
        self.download(m3u8_url,m3u8file,force=True)
        self.downloadinfo.m3u8_file = m3u8file
        self.check_cancel()
        m3obj = m3u8.load(m3u8_url)
        if not m3obj.segments :
            raise M3u8NotFound
        
        self.check_cancel()
        tslist =[seg.absolute_uri for seg in m3obj.segments]
        self.info.progress = 0
        self.info.total = len(tslist)

        self.logger.debug(f"tslis {len(tslist)},{tslist[:1]}")
        key = m3obj.keys[-1] if m3obj.keys else None
        tsuri = key.uri if key else None
        iv = key.iv if key else None
        self.downloadinfo.m3u8_iv = iv

        key_bytes = None
        
        if tsuri:
            m3kurl = tsuri if tsuri.startswith("http") else m3obj.segments[0].base_uri + tsuri
            self.downloadinfo.m3u8_key_url = m3kurl
            self.logger.debug(f"m3u8 key url {m3kurl}")
            # 得到 key的內容
            key_bytes = self.download(m3kurl)
            self.downloadinfo.m3u8_key = base64.b64encode(key_bytes).decode()
        
        self.save_metainfo()
        self.check_cancel()
        
        tsdir= os.path.join(self.destDir,"ts")
        if not os.path.exists(tsdir):
            os.mkdir(tsdir)
        tsfiles = []
        for ts in tslist:
            self.check_cancel()
            name = ts.split("?")[0]
            name = name.split("/")[-1]
            dest = os.path.join(tsdir,name)
            ci = None
            if key_bytes:
                iv_bytes = bytes.fromhex(iv.replace("0x", "")) if iv else bytes(AES.block_size)
                ci = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
            self.download_ts(ts,dest,ci)
            tsfiles.append(dest)
            self.info.progress += 1

        videopath = os.path.join(self.destDir,f"{self.name}.mp4")
        with open(videopath,"wb") as v:
            for ts in tsfiles:
                self.check_cancel()
                with open(ts,'rb') as f :
                    v.write(f.read())
                os.remove(ts)
            os.rmdir(tsdir)
        self.logger.info("mp4 file created")
        self.info.video_url = videopath
        self.info.video_size = os.path.getsize(videopath)
         

    def _run(self):
        destdir = self.destDir
        os.makedirs(destdir, exist_ok=True)
        self.check_cancel()

        self.logger.info(f"task url {self.url}")
        try:
            metadata = self.provider.fetch_metadata(self.url)
        except ValueError as exc:
            self.logger.error(str(exc))
            self.set_status(TaskStatus.Failed)
            raise M3u8NotFound from exc

        self.info.title = metadata.title
        self.info.cover_url = metadata.cover_url

        dest = os.path.join(destdir,f"{self.name}.jpg")
        self.info.cover = dest
        self.download(metadata.cover_url,dest)
        self.save_metainfo()

        m3u8_url = metadata.m3u8_url
        self.logger.info(f"m3u8: {m3u8_url}")

        self._get_m3u8(m3u8_url) # timeout: 410 Gone
       

    def run(self):
        if self.status == TaskStatus.Canceled:
            self.logger.info(f"skip canceled task {self.name}")
            self.save_metainfo()
            return
        self.logger.info(f"task {self.name} running")
        if not self.info.start_time:
            self.info.start_time = int(time.time())
        self.set_status(TaskStatus.Running)
        try:
            self._run()
            self.info.finish_time = int(time.time())
            self.set_status(TaskStatus.Finished)
        except TaskCanceled as e :
            self.logger.warning(f"task {self.name} canceled")
            self.save_metainfo()
            return 
        except Exception as e :
            self.set_status(TaskStatus.Failed)
            traceback.print_exc()
            self.logger.error(f"task fialed {e}")
        self.save_metainfo()

    def check_cancel(self):
        if self.status == TaskStatus.Canceled :
            raise TaskCanceled

    def stop(self):
        if self.status in (TaskStatus.Pending, TaskStatus.Running):
            self.set_status(TaskStatus.Canceled)
            self.save_metainfo()
    
    # clean temprary files created during download
    def clean(self):
        tsdir = os.path.join(self.destDir,"ts")
        if os.path.isdir(tsdir):
            shutil.rmtree(tsdir)
        return 1

    # remove all files downloaded
    def remove(self):
        if self.status in (TaskStatus.Pending, TaskStatus.Running):
            self.stop()
        if os.path.isdir(self.destDir):
            shutil.rmtree(self.destDir)
        return 1

    def save_metainfo(self):
        try:
            self.task_store.save(self.name, self.desc(detail=True))
        except Exception as e :
            self.logger.error(f"save metainfo failed: {e}")

    # convert task to description obj
    def desc(self,detail = False):
        d = self.info.to_dict()
        d['url'] = self.url
        return d

    # fill task with description obj
    def undesc(self,data, info=None):
        self._url = data.get("url",'')
        self.info = info if info is not None else TaskInfo.from_dict(data)


    def load_from_file(self,dirname):
        try:
            if not os.path.exists(dirname):
                return 0
            loaded = self.task_store.load_task_info(dirname)
            if loaded is None:
                return 0
            data, info = loaded
            return self.undesc(data, info)
        except Exception as e :
            traceback.print_exc()
            self.logger.info("try load metainfo failed")
            return 0
    
