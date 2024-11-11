
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
 
ua = UserAgent().random

header = {"User-Agent":ua}

# inherit from str to help json encode
class TaskStatus(str,Enum):
    Pending = 'Pending'
    Running = 'Running'
    Finished = 'Finished'
    Failed = 'Failed'
    Canceled = 'Canceled'

    

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

jlogger = logging.getLogger('jlog')
jlogger.setLevel(logging.DEBUG)

class Jmanager():
    def __init__(self,logger = jlogger,downloadDir = "./downloads",workers = 2):
        self.logger = logger
        self.downloadDir = downloadDir
        self.tasks = OrderedDict()
        self.taskq = Queue()
        self.max_worker = workers
        self.executer = ThreadPoolExecutor(max_workers=workers)
        self.stop = threading.Event()
        self._exit = threading.Event()

    def init(self):
        self.logger.debug(f"jmanager thread {threading.get_ident()}")
        for i in range(self.max_worker):
            self.executer.submit(self.run_task)

    def dirName(self):
        return self.downloadDir

    def load_history(self):
        folder = self.downloadDir

    def task_list(self):
        ts = [] 
        for k,v in self.tasks.items():
            ts.append(v.desc())
        ts.reverse()
        return ts

    def add_task(self,url):
        purl = urlparse(url)
        if not purl.hostname == "jable.tv":
             raise InvalidHost(purl.hostname)
        
        t = Jtask(logger=self.logger,url=purl,downloadDir=self.downloadDir)
        if not t.name() in self.tasks :
            self.tasks[t.name()] = t
        if t.status != TaskStatus.Running:
            self.taskq.put(t)
        
        
        self.logger.info(f"add task {self.taskq.qsize()}/{len(self.tasks)} {t.name()}")
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
        return r.remove()

    def run_task(self):
        self.logger.debug(f"jtask thread ready in thread {threading.get_ident()}")
        while not self.stop.is_set():
            try:
                task = self.taskq.get(timeout=1)
                if task :
                    self.logger.info(f"new task in: {task.name()}")
                    task.run()
                    self.taskq.task_done()
            except Empty as e :
                continue
            time.sleep(0.2)
        self._exit.set()
        self.logger.info("Download thread exiting")

    def close(self):
        self.stop.set()
        self.logger.info("jtask thread exiting")
        self._exit.wait(timeout=2)
        self.logger.info("jtask thread exited")

        self.executer.shutdown(wait=False)
        self.executer = None

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

class Jtask():
    def __init__(self,url:ParseResult,logger=jlogger,downloadDir=''):
        self._url = url
        self.logger = logger
        self._downloadDir = downloadDir

        self.status = TaskStatus.Pending
        self.metainfo = {}
        self.downloadinfo = {}
        self.session = requests.sessions.Session()
    
    def _initDriver(self):
        #配置Selenium參數
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--ignore-certificate-errors')  # 忽略证书错误
        options.add_experimental_option('excludeSwitches', ['enable-automation']) # 禁用浏览器正在被自动化程序控制的提示
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        options.add_argument('--headless')
        options.add_argument('blink-settings=imagesEnabled=false') # 禁止加载图片
        options.add_argument('user-agent=' + ua)
        options.add_experimental_option("prefs", {
            "download.default_directory": self.destDir(),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
            })
        dr = webdriver.Chrome(options = options)
        return dr

    def _meta_file(self):
        return os.path.join(self.destDir(),'meta.json')
    
    def _try_load(self):
        try:
            metafile = self._meta_file()
            if not os.path.exists(metafile):        
                return 
            with open(metafile) as f:
                d = json.load(f)
                self._url = urlparse(d.get("url",''))
                self.metainfo = d.get("metainfo",{})
                self.downloadinfo = d.get("downloadinfo",{})
        except Exception as e :
            traceback.print_exc()
            self.logger.info("try load metainfo failed")
        

    def url(self):
        l = self._url.geturl()
        return l

    def name(self):
        items = self._url.path.split('/')
        if len(items) > 1:
            return items[-2]
        raise InvalidUrlPath

    def destDir(self):
        return os.path.join(self._downloadDir,self.name())
    
    @retry(max_attempts=5,exceptions=(ConnectionResetError,requests.exceptions.ConnectionError))
    def download(self,url,dest='',force = False):
        if not force and dest and os.path.exists(dest):
            self.logger.info(f"download {dest} exists,skip.")
            return 
        content = self.session.get(url,headers = header).content
        if dest :
            with open(dest,"wb+") as f :
                f.write(content)
        return content

    @retry(max_attempts=5,exceptions=(ConnectionResetError,requests.exceptions.ConnectionError))
    def download_ts(self,url,dest,ci,force=False):
        if not force and os.path.exists(dest):
            return 1
        content = self.session.get(url,headers = header).content
        if ci :
            content = ci.decrypt(content)
            content = unpad(content,AES.block_size)
        with open(dest,'wb+') as f :
            f.write(content)

    def _get_m3u8(self,m3u8_url:str):
        # find m3u8 in javascript 
        self.downloadinfo['m3u8_url'] = m3u8_url
        
        self.check_cancel()

        m3u8file = os.path.join(self.destDir(),f"{self.name()}.m3u8")
        self.download(m3u8_url,m3u8file,force=True)
        self.downloadinfo['m3u8_file'] = m3u8file
        self.check_cancel()
        m3obj = m3u8.load(m3u8_url)
        if not m3obj.segments :
            raise M3u8NotFound
        
        self.check_cancel()
        tslist =[seg.absolute_uri for seg in m3obj.segments]
        self.downloadinfo['progress'] = 0
        self.downloadinfo['total'] = len(tslist)

        self.logger.info(f"tslis {len(tslist)},{tslist[:1]}")
        tsuri,iv = m3obj.keys[-1].uri[:16] ,m3obj.keys[-1].iv

        ci = None
        
        if tsuri:
            m3kurl = m3obj.segments[0].base_uri + tsuri + ".ts"  # 得到 key 的網址
            self.logger.info(f"m3u8 key url {m3kurl}")
            # 得到 key的內容
            m3key = self.download(m3kurl)
            vt = iv.replace("0x", "")[:16].encode()  # IV取前16位
            ci = AES.new(m3key, AES.MODE_CBC, vt)  # 建構解碼器
        
        self.save_metainfo()
        self.check_cancel()
        
        tsdir= os.path.join(self.destDir(),"ts")
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
            self.downloadinfo['progress'] += 1

        videopath = os.path.join(self.destDir(),f"{self.name()}.mp4")
        with open(videopath,"wb") as v:
            for ts in tsfiles:
                self.check_cancel()
                with open(ts,'rb') as f :
                    v.write(f.read())
                os.remove(ts)
            os.rmdir(tsdir)
        self.logger.info("mp4 file created")
        self.metainfo['video_url'] = videopath
         

    def _run(self):
        destdir = self.destDir()
        if not os.path.exists(destdir):
            self.logger.debug(f"mkdir {destdir}")
            os.mkdir(destdir)
        self.check_cancel()
        dr = self._initDriver()
        dr.get(self.url())
        
        self.check_cancel()

        # get title and cover
        title = dr.find_element(By.XPATH,"//meta[@property='og:title']").get_attribute("content")
        cover_url = dr.find_element(By.XPATH,"//meta[@property='og:image']").get_attribute("content")
        self.metainfo['title'] = title
        self.downloadinfo['cover_url'] = cover_url
        # download cover
        dest = os.path.join(destdir,f"{self.name()}.jpg")
        self.metainfo['cover'] = dest
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

        self._get_m3u8(m3u8_url)
       

    def run(self):
        self.logger.info(f"task {self.name()} running")
        self.metainfo['start_time'] = int(time.time())
        self.status = TaskStatus.Running
        try:
            self._try_load()
            self._run()
            self.metainfo["finish_time"] = int(time.time())
            self.status = TaskStatus.Finished
        except TaskCanceled as e :
            self.logger.warning(f"task {self.name()} canceled")
            self.save_metainfo()
            return 
        except Exception as e :
            self.status = TaskStatus.Failed
            traceback.print_exc()
            self.logger.error(f"task fialed {e}")
        self.save_metainfo()

    def check_cancel(self):
        if self.status == TaskStatus.Canceled :
            raise TaskCanceled

    def stop(self):
        self.status = TaskStatus.Canceled
        self.save_metainfo()
    
    # clean temprary files created during download
    def clean(self):
        d = self.destDir()
        os.rmdir(os.path.join(d,"ts"))
        return 1

    # remove all files downloaded
    def remove(self):
        d = self.destDir()
        os.rmdir(d)
        return 1

    def save_metainfo(self):
        try:
            destdir = self.destDir()
            file = os.path.join(destdir,"meta.json")
            
            data = self.desc(detail=True)
            datastr = json.dumps(data,indent=2,ensure_ascii=False)
            with open(file,"w+",encoding='utf-8') as f :
                f.write(datastr)
                f.flush()
        except Exception as e :
            self.logger.error(f"save metainfo failed: {e}")


    def desc(self,detail = False):
        d = {"name":self.name(),"url":self.url(),"status":self.status}
        if 'total' in self.downloadinfo :
            d['total'] = self.downloadinfo['total']
            d['progress'] = self.downloadinfo['progress']
        for k,v in self.metainfo.items():
            d[k] = v
        if detail :
            d['downloadinfo'] = self.downloadinfo
        for k,v in d.items():
            if isinstance(v,str):
                d[k] = v.lstrip('.')
        return d
