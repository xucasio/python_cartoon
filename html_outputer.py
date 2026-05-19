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
import logging
from PIL import Image
import time
import os
from io import BytesIO

logger = logging.getLogger(__name__)


class HtmlOutputer(object):
    """负责收集章节信息并把漫画图片输出到本地目录。"""

    def __init__(self):
        self.datas = []
        self.exList = []  # 单次线程里的异常爬取
        self.max_connections = 5  # 定义最大线程数
        self.pool_sema = threading.BoundedSemaphore(self.max_connections)

    def collect_data(self, data):
        """收集待输出到 HTML 的章节数据。"""
        if data is None:
            return 0
        self.datas.append(data)

    def output_html(self):
        """把已收集的章节数据写入本地 HTML 文件。"""
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
        """下载单个章节的全部图片页。"""
        folder_path = './' + title
        counts = 1
        if os.path.exists(folder_path) is False:
            os.makedirs(folder_path)
        browser = self.brower_data(mainUrl, counts, folder_path)
        if browser is None:
            raise RuntimeError('章节首页加载失败: %s?p=%s' % (mainUrl, counts))
        try:
            pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
            r = re.search(r'\((.*)/(.*)\)', pagestr)
            if r is None:
                raise RuntimeError('无法解析章节总页数: %s' % pagestr)
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
            self._retry_failed(index)
        
        print(title, '完成',sep='/n------------------------------/n')

    def save_img(self, browser, index, folder_path, counts, main_url=None):
        """保存当前浏览器页面中的漫画图片。"""
        elem = browser.find_element_by_id("images").find_element_by_tag_name("img")
        pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
        r = re.search(r'\((.*)/(.*)\)', pagestr)
        if r is None:
            raise RuntimeError('无法解析当前页码: %s' % pagestr)
        curp = int(r.group(1))
        url = elem.get_attribute('src')
        html = requests.get(url)
        img_name = str(index + 1) + '-' + str(curp) + '.png'
        image = Image.open(BytesIO(html.content))
        image.save(folder_path + '/' + img_name)
        self._remove_failed(counts, folder_path, main_url)
        time.sleep(1)

    def brower_data(self, mainUrl, counts, folder):
        """打开指定章节页；失败时记录待重试任务并关闭浏览器。"""
        chrome_options = webdriver.ChromeOptions()
        # 使用headless无界面浏览器模式
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        # 启动浏览器，获取网页源代码
        browser = webdriver.Chrome(chrome_options=chrome_options)
        try:
            browser.get(mainUrl + '?p=' + str(counts))
        except Exception:
            logger.exception('当前进程异常啦: %s?p=%s', mainUrl, counts)
            failed_item = {'index': counts, 'url': mainUrl, 'folder': folder}
            if failed_item not in self.exList:
                self.exList.append(failed_item)
            browser.quit()
            return None
        return browser

    def threadRun(self, index, folder_path, mainUrl, counts):
        """线程入口：下载一页图片，并保证信号量和浏览器资源被释放。"""
        browser = None
        self.pool_sema.acquire() # 加锁
        try:
            browser = self.brower_data(mainUrl, counts, folder_path)
            if browser is None:
                return
            self.save_img(browser, index, folder_path, counts, mainUrl)
        except Exception:
            logger.exception('图片页保存失败: %s?p=%s', mainUrl, counts)
            failed_item = {'index': counts, 'url': mainUrl, 'folder': folder_path}
            if failed_item not in self.exList:
                self.exList.append(failed_item)
        finally:
            self.pool_sema.release() # 释放
            if browser is not None:
                browser.quit()

    def list_split(self, items, n):
        """按固定长度拆分列表，供分批启动线程使用。"""
        return [items[i:i+n] for i in range(0, len(items), n)]

    def _retry_failed(self, index):
        """重试本批次失败任务；若没有任何进展则终止，避免无限循环。"""
        while len(self.exList) > 0:
            retry_items = list(self.exList)
            before_count = len(self.exList)
            for item in retry_items:
                browser = self.brower_data(item['url'], item['index'], item['folder'])
                if browser is None:
                    continue
                try:
                    self.save_img(browser, index, item['folder'], item['index'], item['url'])
                finally:
                    browser.quit()
            if len(self.exList) >= before_count:
                raise RuntimeError('图片重试失败，剩余 %s 个任务' % len(self.exList))

    def _remove_failed(self, counts, folder_path, main_url=None):
        """图片保存成功后清理对应失败记录。"""
        self.exList = [
            item for item in self.exList
            if not (
                item.get('index') == counts and
                item.get('folder') == folder_path and
                (main_url is None or item.get('url') == main_url)
            )
        ]