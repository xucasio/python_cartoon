# -*- coding: utf-8 -*-
from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.webdriver.common.action_chains import ActionChains
# from selenium.webdriver.common.keys import Keys
import threading
import requests
import re
from PIL import Image
import time
import os
import logging
from io import BytesIO


logger = logging.getLogger(__name__)


class HtmlOutputer(object):
    """章节图片输出器，负责并发下载单个章节内的所有图片。"""

    def __init__(self):
        """初始化图片缓存、异常队列和并发控制器。"""
        self.datas = []
        self.exList = []  # 单次线程里的异常爬取
        self.max_connections = 5  # 定义最大线程数
        self.pool_sema = threading.BoundedSemaphore(self.max_connections)
        self.ex_lock = threading.Lock()

    def collect_data(self, data):
        """收集待输出的章节链接数据。"""
        if data is None:
            return 0
        self.datas.append(data)

    def output_html(self):
        """将已收集的章节链接输出为简单 HTML 文件。"""
        fout = open('output.html', 'w', encoding='utf-8')
        fout.write("<html>")
        fout.write("<body>")
        fout.write("<div id='content'>")
        fout.write("<ul>")
        for data in self.datas:
            fout.write("<li class='item'>")
            fout.write("<a href='%s'>%s</a>" % (data['url'], data['title']))
            fout.write("</li>")
        fout.write("</ul>")
        fout.write("</div>")
        # fout.write("<table>")
        # for data in self.datas:
        #     fout.write("<tr>")
        #     print(data['url'], data['title'])

        #     fout.write("<td>%s</td>" % data['url'])
        #     fout.write("<td>%s</td>" % data['title'])
        #     fout.write("<tr>")
        # fout.write("</table>")
        fout.write("</body>")
        fout.write("</html>")
        fout.close()

    def output_img(self, mainUrl, title, index):
        """下载一个章节的所有图片，并对失败页进行有限重试。"""
        folder_path = './' + title
        counts = 1
        self.exList = []
        if os.path.exists(folder_path) is False:
            os.makedirs(folder_path)
        browser = self.brower_data(mainUrl, counts, folder_path)
        try:
            pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
            r = re.search(r'\((.*)/(.*)\)', pagestr)
            surp = int(r.group(2))
        finally:
            browser.quit()
        
        # 按照20步长切割数组 
        # 在线程控制上锁，限制5个，这步长基本作废了，哭
        # 但是批量线程后的批量串行就该这么调
        itemlists = self.list_split(range(1, surp+1), 40)
        for itemlist in itemlists:
            threads = {}
            while counts >= itemlist[0] and counts <= itemlist[-1]:
                threads['t' + str(counts)] = threading.Thread(target=self.threadRun,args=(index, folder_path, mainUrl, counts))
                threads['t' + str(counts)].start()
                counts += 1
            for t in threads:
                print('/n------------执行守护线程-------------/n')
                threads[t].join()
            # 异常请求再次调用
            self._retry_failures(index)
        
        print(title, '完成',sep='/n------------------------------/n')

    def save_img(self, browser, index, folder_path, counts, mainUrl=None):
        """保存浏览器当前页的图片，成功后从异常队列中清除对应页。"""
        elem = browser.find_element_by_id("images").find_element_by_tag_name("img")
        pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
        r = re.search(r'\((.*)/(.*)\)', pagestr)
        curp = int(r.group(1))
        url = elem.get_attribute('src')
        html = requests.get(url)
        img_name = str(index + 1) + '-' + str(curp) + '.png'
        image = Image.open(BytesIO(html.content))
        image.save(folder_path + '/' + img_name)
        if mainUrl is not None:
            self._clear_failure(counts, mainUrl, folder_path)
        time.sleep(1)

    def brower_data(self, mainUrl, counts, folder):
        """打开指定章节页码，失败时记录到异常队列供后续重试。"""
        chrome_options = webdriver.ChromeOptions()
        # 使用headless无界面浏览器模式
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        # 启动浏览器，获取网页源代码
        browser = webdriver.Chrome(chrome_options=chrome_options)
        try:
            browser.get(mainUrl + '?p=' + str(counts))
        except Exception as e:
            logger.exception('当前进程异常啦：url=%s, page=%s', mainUrl, counts)
            print('当前进程异常啦', e)
            self._append_failure(counts, mainUrl, folder)
        return browser

    def threadRun(self, index, folder_path, mainUrl, counts):
        """线程工作函数，保证异常时也释放并发信号量和浏览器资源。"""
        browser = None
        self.pool_sema.acquire() # 加锁
        try:
            browser = self.brower_data(mainUrl, counts, folder_path)
            self.save_img(browser, index, folder_path, counts, mainUrl)
        except Exception:
            logger.exception('图片下载失败：url=%s, page=%s, folder=%s', mainUrl, counts, folder_path)
            self._append_failure(counts, mainUrl, folder_path)
        finally:
            if browser is not None:
                browser.quit()
            self.pool_sema.release() # 释放

    def list_split(self, items, n):
        """按固定步长拆分页码列表，便于分批创建线程。"""
        return [items[i:i+n] for i in range(0, len(items), n)]

    def _append_failure(self, counts, mainUrl, folder):
        """线程安全地记录失败页，避免重复失败项导致重试队列膨胀。"""
        failure = {'index': counts, 'url': mainUrl, 'folder': folder}
        with self.ex_lock:
            if failure not in self.exList:
                self.exList.append(failure)

    def _clear_failure(self, counts, mainUrl, folder):
        """线程安全地移除已成功保存的失败页。"""
        with self.ex_lock:
            self.exList = [
                item for item in self.exList
                if not (
                    item['index'] == counts
                    and item['url'] == mainUrl
                    and item['folder'] == folder
                )
            ]

    def _retry_failures(self, chapter_index, max_retries=3):
        """对失败页做有限重试，避免持久失败时进入无限循环。"""
        for retry_index in range(max_retries):
            with self.ex_lock:
                failed_items = list(self.exList)
            if not failed_items:
                return
            logger.warning('开始第 %s 次重试，待重试页数：%s', retry_index + 1, len(failed_items))
            for item in failed_items:
                browser = None
                try:
                    browser = self.brower_data(item['url'], item['index'], item['folder'])
                    self.save_img(browser, chapter_index, item['folder'], item['index'], item['url'])
                except Exception:
                    logger.exception('重试图片下载失败：url=%s, page=%s', item['url'], item['index'])
                    self._append_failure(item['index'], item['url'], item['folder'])
                finally:
                    if browser is not None:
                        browser.quit()
        with self.ex_lock:
            failed_items = list(self.exList)
        if failed_items:
            raise RuntimeError('部分图片多次重试后仍下载失败：%s' % failed_items)