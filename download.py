
import requests
import time
import os
import re
from urllib.parse import urlparse,ParseResult
import m3u8
import json
import sys
from Crypto.Cipher import AES
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import logging
from bs4 import BeautifulSoup
from functools import partial
import concurrent.futures
from threading import Thread
from collections import OrderedDict



jlogger = logging.getLogger('jlog')
jlogger.setLevel(logging.DEBUG)

class JableApp():
    def __init__(self,logger = jlogger,downloadDir = "./downloads"):
        self.downloadDir = downloadDir

    async def run_task(self,url:ParseResult):
        purl = urlparse(url)


class Jtask():
    def __init__(self,url:ParseResult,logger=jlogger,downloadDir=''):
        self._url = url
        self.logger = jlogger
        self._downloadDir = downloadDir
        self._initDriver()

    def _initDriver(self):
        #配置Selenium參數
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        options.add_argument('--headless')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.125 Safari/537.36")
        options.add_experimental_option("prefs", {
            "download.default_directory": self.dirName(),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
            })
        dr = webdriver.Chrome(options=options)
        self._driver = dr
    
    def name(self):
        name = self._url.split('/')[-2]
        return name

    def destDir(self):
        return os.path.join(self._downloadDir,self.name())

    async def run(self):
        destdir = self.destDir()
        if not os.path.exists(destdir):
            os.mkdir(destdir)
        

        
class Jtask():
    def __init__(self,logger,url,encode,destDir,executor):
        self._url = url
        self._startTime = None
        self._endTime = None
        self._encode = encode
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
