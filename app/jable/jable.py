import requests
import time
import os
import re
from urllib.parse import urlparse,ParseResult
import m3u8
import json
import functools
from typing import Type, Union, Tuple, Optional
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad,unpad

from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import logging

import threading
from collections import OrderedDict
from queue import Queue,Empty
from concurrent.futures import ThreadPoolExecutor

from enum import Enum

from fake_useragent import UserAgent
import traceback
from dataclasses import dataclass
from typing import OrderedDict as TOrderedDict
import base64

jlogger = logging.getLogger('jlog')
jlogger.setLevel(logging.DEBUG)
 
ua = UserAgent().random

header = {"User-Agent":ua}

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

# inherit from str to help json encode
class TaskStatus(str,Enum):
    Pending = 'Pending'
    Running = 'Running'
    Finished = 'Finished'
    Failed = 'Failed'
    Canceled = 'Canceled'

@dataclass
class TaskInfo:
    name: str = ''                    # 任务名称（从URL中提取）
    url: str = ''                     # 完整的URL
    title: str = ''                   # 视频标题
    status: TaskStatus = TaskStatus.Pending  # 任务状态
    total: Optional[int] = None       # 总分片数
    progress: Optional[int] = None    # 当前下载进度
    start_time: Optional[int] = None  # 开始时间戳
    finish_time: Optional[int] = None # 完成时间戳
    cover_url: Optional[str] = None   # 封面图片原始url
    cover: Optional[str] = None       # 封面图片本地路径
    video_url: Optional[str] = None   # 视频文件路径
    video_size: Optional[int] = None  # 视频文件大小

    def to_dict(self) -> dict:
        """转换为字典,用于JSON序列化"""
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建实例,用于从JSON反序列化"""
        # 动态获取TaskInfo类的字段
        valid_fields = set(cls.__init__.__code__.co_varnames[1:])  # 排除self参数
        
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        if 'status' in filtered_data:
            filtered_data['status'] = TaskStatus(filtered_data['status'])

        return cls(**filtered_data)

@dataclass
class DownloadInfo:
    m3u8_url: str = ''
    m3u8_file: str = ''
    m3u8_key_url: str = ''
    m3u8_key:str = '' # base64
    m3u8_iv: str = ''


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
        self.tasks : TOrderedDict[str,Jtask] = OrderedDict()
        self.taskq = Queue(maxsize=10) # 任务队列
        self.max_worker = workers
        self.executer = ThreadPoolExecutor(max_workers=self.max_worker)
        self.init()

    def init(self):
        self.logger.info(f"jmanager thread {threading.get_ident()},max worker {self.max_worker}")
        for i in range(self.max_worker):
            self.executer.submit(self.run_task)
        self.load_history()

    def run_task(self):
        self.logger.info(f"jtask thread ready in thread {threading.get_ident()}")
        while True:
            self.logger.info(f"Current queue size: {self.taskq.qsize()}")
            task = self.taskq.get()
            self.logger.info(f"get new task {task.name}")
            if task:
                self.logger.info(f"new task in: {task.url}")
                task.run()
                self.taskq.task_done()
            else :
                self.logger.info("empty task,exit")
                break

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
        for t in tasks :
            self.tasks[t.name] = t
            
    def load_task(self,path):
        metapath = os.path.join(path,"meta.json")
        if not os.path.exists(metapath):
            return None
        with open(metapath) as f :
            metainfo = json.load(f)
            t = Jtask(None,downloadDir=self.downloadDir)
            t.undesc(metainfo)
            return t

    def dirName(self):
        return self.downloadDir

    def task_list(self):
        ts = [] 
        for k,v in self.tasks.items():
            ts.append(v.desc())
        ts.reverse()
        return ts
    
    def start_task(self,name):
        if name not in self.tasks :
            return 0
        t = self.tasks[name]
        t.run()
        return 1

    def add_task(self,url):
        purl = urlparse(url)
        if not purl.hostname == "jable.tv":
             raise InvalidHost(purl.hostname)
        
        t = Jtask(url=url,logger=self.logger,downloadDir=self.downloadDir)
        if t.name in self.tasks:
            t = self.tasks[t.name]
        else :
            self.tasks[t.name] = t
        if t.status != TaskStatus.Running:
            self.taskq.put(t)
            self.logger.info(f"add task {self.taskq.qsize()}/{len(self.tasks)} {t.url}")
        return t.desc()
    
    def stop_task(self,name):
        if name not in self.tasks :
            return 0
        t = self.tasks[name]
        t.stop()
        return 1

    # clean temprary files created during download
    def clean_task(self,name):
        if name not in self.tasks:
            return 0
        t = self.tasks[name]
        t.clean()
        return 1

    def remove_task(self,name):
        if name not in self.tasks:
            return 0
        t = self.tasks[name]
        return t.remove()



    def close(self):
        self.logger.info("jtask thread exiting")
        for i in range(self.max_worker):
            self.taskq.put(None)


class Jtask():
    def __init__(self,url:str,logger=jlogger,downloadDir=''):
        self._url = url
        self.logger = logger
        self._downloadDir = downloadDir
        self.info = TaskInfo()
        self.downloadinfo = DownloadInfo()
        self._session = requests.sessions.Session()
    
    def _initDriver(self):
        service = Service(executable_path=ChromeDriverManager().install())
        #配置Selenium參數
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--ignore-certificate-errors')  # 忽略证书错误
        options.add_experimental_option('excludeSwitches', ['enable-automation']) # 禁用浏览器正在被自动化程序控制的提示
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        options.add_argument('--headless')
        options.add_argument("--disable-gpu") 
        options.add_argument('blink-settings=imagesEnabled=false') # 禁止加载图片
        options.add_argument('user-agent=' + ua)
        # options.add_experimental_option("prefs", {
        #     "download.default_directory": self.destDir,
        #     "download.prompt_for_download": False,
        #     "download.directory_upgrade": True,
        #     "safebrowsing.enabled": True
        #     })
        dr = webdriver.Chrome(service=service, options = options)
        return dr

    @property
    def destDir(self):
        return os.path.join(self._downloadDir,self.name)
    @property
    def metafile(self):
        return os.path.join(self.destDir,'meta.json')
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
    
    @retry(max_attempts=5,exceptions=(ConnectionResetError,requests.exceptions.ConnectionError))
    def download(self,url,dest='',force = False):
        if not force and dest and os.path.exists(dest):
            return 
        content = self._session.get(url,headers = header).content
        if dest :
            with open(dest,"wb+") as f :
                f.write(content)
        return content

    @retry(max_attempts=5,exceptions=(ConnectionResetError,requests.exceptions.ConnectionError,ValueError))
    def download_ts(self,url,dest,ci,force=False):
        if not force and os.path.exists(dest):
            return 
        content = self._session.get(url,headers = header).content
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
        tsuri,iv = m3obj.keys[-1].uri[:16] ,m3obj.keys[-1].iv
        self.downloadinfo.m3u8_iv = iv

        ci = None
        
        if tsuri:
            m3kurl = m3obj.segments[0].base_uri + tsuri + ".ts"  # 得到 key 的網址
            self.downloadinfo.m3u8_key_url = m3kurl
            self.logger.debug(f"m3u8 key url {m3kurl}")
            # 得到 key的內容
            m3key = self.download(m3kurl)
            self.downloadinfo.m3u8_key = base64.encodebytes(m3key).hex()
            vt = iv.replace("0x", "")[:16].encode()  # IV取前16位
            ci = AES.new(m3key, AES.MODE_CBC, vt)  # 建構解碼器
        
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
        if not os.path.exists(destdir):
            self.logger.debug(f"mkdir {destdir}")
            os.mkdir(destdir)
        self.check_cancel()

        print("task url",self.url)
        dr = self._initDriver()
        dr.get(self.url)
        self.check_cancel()
        # wait page fully loaded
     
        # get title and cover
        title = dr.find_element(By.XPATH,"//meta[@property='og:title']").get_attribute("content")
        cover_url = dr.find_element(By.XPATH,"//meta[@property='og:image']").get_attribute("content")
        self.info.title = title
        self.info.cover_url = cover_url
        # download cover
        dest = os.path.join(destdir,f"{self.name}.jpg")
        self.info.cover = dest
        self.download(cover_url,dest)
        self.save_metainfo()
        # get m3u8 file
        m3u8_url = re.search("https://.+m3u8", dr.page_source)
        dr.quit() # browser is not needed any more at this point

        if not m3u8_url :
            self.logger.error(f"m3u8 not found")
            self.status = TaskStatus.Failed
            raise M3u8NotFound
        m3u8_url = m3u8_url[0]
        self.logger.info(f"m3u8: {m3u8_url}")

        self._get_m3u8(m3u8_url) # timeout: 410 Gone
       

    def run(self):
        self.logger.info(f"task {self.name} running")
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
        if self.status == TaskStatus.Running :
            self.set_status(TaskStatus.Canceled)
            self.save_metainfo()
    
    # clean temprary files created during download
    def clean(self):
        d = self.destDir
        os.rmdir(os.path.join(d,"ts"))
        return 1

    # remove all files downloaded
    def remove(self):
        d = self.destDir
        os.rmdir(d)
        return 1

    def save_metainfo(self):
        try:
            data = self.desc(detail=True)
            datastr = json.dumps(data,indent=2,ensure_ascii=False)
            with open(self.metafile,"w+",encoding='utf-8') as f :
                f.write(datastr)
                f.flush()
        except Exception as e :
            self.logger.error(f"save metainfo failed: {e}")

    # convert task to description obj
    def desc(self,detail = False):
        d = self.info.to_dict()
        d['url'] = self.url
        return d

    # fill task with description obj
    def undesc(self,data):
        self._url = data.get("url",'')
        self.info = TaskInfo.from_dict(data)
        if not self.info.video_url :
            self.info.video_size = os.path.getsize('.'+self.info.video_url) if self.info.video_url else None
        

    def load_from_file(self,dirname):
        try:
            metafile = os.path.join(dirname,"meta.json")
            if not os.path.exists(dirname) or not os.path.exists(metafile):        
                return 0
            with open(metafile) as f:
                d = json.load(f)
                return self.undesc(d)
        except Exception as e :
            traceback.print_exc()
            self.logger.info("try load metainfo failed")
            return 0
    
