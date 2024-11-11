
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
from bs4 import BeautifulSoup
from functools import partial

import asyncio

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
    logger = None
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
        # options.add_argument('--headless')
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
        # https://ap-drop-monst.mushroomtrack.com/bcdn_token=5WemB68GLWB06KD7m7PWGyfIcYwoSqg6rCMbR9frcf4&expires=1731245965&token_path=%2Fvod%2F/vod/16000/16752/16752.m3u8
        # https://ap-drop-monst.mushroomtrack.com/bcdn_token=5WemB68GLWB06KD7m7PWGyfIcYwoSqg6rCMbR9frcf4&expires=1731245965&token_path=%2Fvod%2F/vod/16000/16752/167520.ts
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
        self.metainfo['cover_url'] = dest
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
            return 
        except Exception as e :
            self.status = TaskStatus.Failed
            traceback.print_exc()
            self.logger.error(f"task fialed {e}")

    def check_cancel(self):
        if self.status == TaskStatus.Canceled :
            raise TaskCanceled

    def stop(self):
        self.status = TaskStatus.Canceled
        self.save_metainfo()

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
        d['metainfo'] = self.metainfo
        if detail :
            d['downloadinfo'] = self.downloadinfo
        return d
        
# ==================================== * =========================================
        
class Jtaskd():
    def __init__(self,logger,url,driver,destDir,executor):
        self._url = url
        self._startTime = None
        self._endTime = None
        self._driver = driver # headless browser
        self._destDir = destDir
        self._tsList = []
        self._m3u8url = ""
        self._done = {}
        self.title = ""
        self._ci = ""
        self._state = []
        self._stop = False
        self._executor = executor
        self.logger = logger
        self._initDriver()
        self._state.append("inited")
        

    def dirName(self):
        dirName = os.path.join(self._destDir,self.Name())
        return dirName

    def coverPath(self):
        cover = os.path.join(self.dirName(),f"{self.Name()}.jpg")
        if cover.startswith('.'):
            cover = cover[1:]
        return cover
    
    def mp4Path(self):
        path = os.path.join(self.dirName(),f"{self.Name()}.mp4")
        if path.startswith("."):
            path = path[1:]
        return path

    def _create_dir(self):
        dirName = self.dirName()
        if os.path.exists(f'{dirName}/{self.Name()}.mp4'):
            return
        if not os.path.exists(dirName):
            os.makedirs(dirName)

    def _parseTask(self):
        self._state.append("parsing")
        folderPath = self.dirName()
        m3u8file = os.path.join(folderPath, self.Name() + '.m3u8')

        
        cover_name = f"{os.path.basename(folderPath)}.jpg"
        cover_path = os.path.join(folderPath, cover_name)

      
        self._driver.get(self.url())

        soup = BeautifulSoup(self._driver.page_source, "html.parser")
        cover_url = ""
        for meta in soup.find_all("meta"):
            # self.logger.info(f"{meta.get('property')},{meta.get('content')}")
            if "og:title" == meta.get('property'):
                self.title = meta.get("content") 
                # print(self.title)
            if "og:image" == meta.get('property'):
                cover_url = meta.get("content") 
                # print(cover_url)

        # get cover
        if cover_url and not os.path.exists(cover_path):
            try:
                self.logger.info(f"downloading cover: {cover_url}")
                r = requests.get(cover_url)
                with open(cover_path, "wb") as cover_fh:
                    r.raw.decode_content = True
                    for chunk in r.iter_content(chunk_size=10240):
                        if chunk:
                            cover_fh.write(chunk)
            except Exception as e:
                    self.logger.warn(f"unable to download cover: {e}")
                    self._state.append(f"unable to download cover: {e}")

        result = re.search("https://.+m3u8", self._driver.page_source)
        if not result :
            self._state.append("m3u8 file not found")
        
        self.logger.info(f'result: {result}')
        m3u8url = result[0]
        self._m3u8url = m3u8url
        self.logger.info(f'm3u8url: {m3u8url}')

        # 儲存 m3u8 file 至資料夾
        urllib.request.urlretrieve(m3u8url, m3u8file)


        # 得到 m3u8 file裡的 URI和 IV
        m3u8obj = m3u8.load(m3u8file)
        m3u8uri = ''
        m3u8iv = ''

        for key in m3u8obj.keys:
            if key:
                m3u8uri = key.uri
                m3u8iv = key.iv
        # 得到 m3u8 網址
        m3u8list = m3u8url.split('/')
        m3u8list.pop(-1)
        downloadurl = '/'.join(m3u8list)
        # 儲存 ts網址 in tsList
        for seg in m3u8obj.segments:
            tsUrl = downloadurl + '/' + seg.uri
            self._tsList.append(tsUrl)

        # 有加密
        if m3u8uri:
            m3u8keyurl = downloadurl + '/' + m3u8uri  # 得到 key 的網址
            # 得到 key的內容
            response = requests.get(m3u8keyurl, headers=headers, timeout=10)
            contentKey = response.content

            vt = m3u8iv.replace("0x", "")[:16].encode()  # IV取前16位

            self._ci = AES.new(contentKey, AES.MODE_CBC, vt)  # 建構解碼器
        else:
            self._ci = ''
        self._save()
        self._state.append("task parse done")

    def state(self):
        if not self._state :
            return "waiting"
        return self._state[-1]

    def _scrape(self,url):
        if self._stop :
            return 
        if self._done.get(url,0):
            return 
        fileName = url.split('/')[-1][0:-3]
        saveName = os.path.join(self.dirName(), fileName + ".mp4")
        if os.path.exists(saveName) :
            # 跳過已下載
            self._done[saveName] = 1
            return 
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                content_ts = response.content
                if self._ci:
                    content_ts = self._ci.decrypt(content_ts)  # 解碼
                with open(saveName, 'ab') as f:
                    f.write(content_ts)
                self._done[url] = 1
            else :
                self.logger.warn(f"{fileName} download failed, status {response.status_code}")
        except Exception as e :
            self.logger.error(f"download {url} ,err:{e}")
        # print(f"download {url} to {saveName} {response.status_code}")


    def _crawl(self):
        # 開始時間
        start_time = time.time()
        while len(self._done) < len(self._tsList):
            for url in self._tsList :
                if url not in self._done:
                    # 開始爬取
                    future = self._executor.submit(self._scrape,url)
                    future.result()
            
        end_time = time.time()
        self.logger.info('\n花費 {0:.2f} 分鐘 爬取完成 !'.format((end_time - start_time) / 60))
        
    def _save(self):
        desc = self.Desc()
        desc['url'] = self._url
        desc["m3u8url"] = self._m3u8url
        dirpath = self.dirName()
        file = os.path.join(dirpath,f"{self.Name()}.json")
        with open(file,"w+") as f :
            json.dump(desc,f,indent=2,ensure_ascii=False)
    def _load(self):
        dirpath = self.dirName()
        file = os.path.join(dirpath,f"{self.Name()}.json")
        if os.path.exists(file):
            with open(file) as f :
               t = json.load(f)


    def _download(self):
        self.logger.info(f"start to download {self.Name()}")
        self._create_dir() 
        self._parseTask()
        self._state.append("downloading")
        self._crawl()
        folderPath = self.dirName()
         # 刪除m3u8 file
        # deleteM3u8(folderPath)
          # 合成mp4
        self._state.append("merging")
        mergeMp4(folderPath, self._tsList)
         # 刪除子mp4
        deleteMp4(folderPath)
        self._endTime = time.time()

    def Start(self):
        if self._stop:
            self._stop = False
        self._startTime = time.time()
        self._download()
        self.logger.info(f"task {self.Name()} started")

    def Stop(self):
        self._stop = True
        self._state.append("stopped")
        self._driver.quit()
    def Close(self):
        if self._driver :
            self._driver.close()
    def Name(self):
        name = self._url.split('/')[-2]
        return name
    def Progress(self):
        if len(self._tsList) == 0 :
            return 0
        return len(self._done)/len(self._tsList)

    def Done(self):
        return len(self._tsList) == len(self._done)

    def startTime(self):
        if not self._startTime:
            return 0
        return int(self._startTime)
    def endTime(self):
        if not self._endTime:
            return 0
        return int(self._endTime)
    def Desc(self):
        return {"name":self.Name(),"url":self.url(),
        "state":self.state(),"progress":self.Progress(),
        "start_time":self.startTime(),"finish_time":self.endTime(),
        "cover":self.coverPath(),"file":self.mp4Path(),
        "title":self.title}
