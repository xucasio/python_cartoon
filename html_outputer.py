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
from io import BytesIO


class HtmlOutputer(object):
    """章节图片输出器，负责多线程下载图片并重试失败页。"""

    def __init__(self):
        self.datas = []
        self.exList = []  # 单次线程里的异常爬取
        self.ex_lock = threading.Lock()  # 多线程访问重试队列时保护一致性
        self.max_connections = 5  # 定义最大线程数
        self.pool_sema = threading.BoundedSemaphore(self.max_connections)

    def collect_data(self, data):
        """收集待输出的章节链接数据。"""
        if data is None:
            return 0
        self.datas.append(data)

    def output_html(self):
        """将已收集的数据写入简单 HTML 页面。"""
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
        """下载单个章节下的全部图片。"""
        folder_path = './' + title
        counts = 1
        if os.path.exists(folder_path) is False:
            os.makedirs(folder_path)
        browser = self.brower_data(mainUrl, counts, folder_path)
        try:
            pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
        finally:
            browser.quit()
        r = re.search(r'\((.*)/(.*)\)', pagestr)
        surp = int(r.group(2))
        
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
            self._retry_failed_items(index)
        
        print(title, '完成',sep='/n------------------------------/n')

    def save_img(self, browser, index, folder_path, counts):
        """保存当前浏览器页面中的漫画图片。"""
        elem = browser.find_element_by_id("images").find_element_by_tag_name("img")
        pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
        r = re.search(r'\((.*)/(.*)\)', pagestr)
        curp = int(r.group(1))
        url = elem.get_attribute('src')
        html = requests.get(url)
        img_name = str(index + 1) + '-' + str(curp) + '.png'
        image = Image.open(BytesIO(html.content))
        self._remove_retry_item(counts, folder_path)
        image.save(folder_path + '/' + img_name)
        time.sleep(1)

    def brower_data(self, mainUrl, counts, folder):
        """打开指定页码，失败时记录到重试队列。"""
        chrome_options = webdriver.ChromeOptions()
        # 使用headless无界面浏览器模式
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        # 启动浏览器，获取网页源代码
        browser = webdriver.Chrome(chrome_options=chrome_options)
        try:
            browser.get(mainUrl + '?p=' + str(counts))
        except Exception as e:
            print('当前进程异常啦', e)
            self._add_retry_item(counts, mainUrl, folder)
        return browser

    def threadRun(self, index, folder_path, mainUrl, counts):
        """线程入口，确保异常时也释放并发槽位和浏览器。"""
        self.pool_sema.acquire() # 加锁
        browser = None
        try:
            browser = self.brower_data(mainUrl, counts, folder_path)
            self.save_img(browser, index, folder_path, counts)
        finally:
            self.pool_sema.release() # 释放
            if browser is not None:
                browser.quit()

    def list_split(self, items, n):
        """按固定大小拆分页码列表。"""
        return [items[i:i+n] for i in range(0, len(items), n)]

    def _add_retry_item(self, counts, mainUrl, folder):
        """记录失败页，避免同一页重复进入重试队列。"""
        retry_item = {'index': counts, 'url': mainUrl, 'folder': folder}
        with self.ex_lock:
            if retry_item not in self.exList:
                self.exList.append(retry_item)

    def _remove_retry_item(self, counts, folder_path):
        """图片成功保存后移除对应失败记录。"""
        with self.ex_lock:
            self.exList = [
                item for item in self.exList
                if item.get('index') != counts or item.get('folder') != folder_path
            ]

    def _retry_items(self):
        """返回重试队列快照，避免遍历时被其他线程修改。"""
        with self.ex_lock:
            return list(self.exList)

    def _has_retry_items(self):
        """判断当前是否还有待重试页面。"""
        with self.ex_lock:
            return len(self.exList) > 0

    def _retry_failed_items(self, index):
        """重试失败队列中的页面。"""
        while self._has_retry_items():
            for item in self._retry_items():
                browser = self.brower_data(item['url'], item['index'], item['folder'])
                try:
                    self.save_img(browser, index, item['folder'], item['index'])
                finally:
                    browser.quit()