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
    """图片输出器，负责按章节页面抓取并保存漫画图片。"""

    def __init__(self):
        self.datas = []
        self.exList = []  # 单次线程里的异常爬取
        self.max_connections = 5  # 定义最大线程数
        self.max_retry_attempts = 3  # 单页失败后的最大重试次数，避免永久失败导致死循环
        self.pool_sema = threading.BoundedSemaphore(self.max_connections)

    def collect_data(self, data):
        """收集待输出的 HTML 链接数据。"""
        if data is None:
            return 0
        self.datas.append(data)

    def output_html(self):
        """把已收集的数据输出为一个简单的 HTML 索引文件。"""
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
        """下载单个章节的全部图片。"""
        folder_path = './' + title
        counts = 1
        if os.path.exists(folder_path) is False:
            os.makedirs(folder_path)
        browser = self.brower_data(mainUrl, counts, folder_path)
        if browser is None:
            raise RuntimeError('章节首页加载失败，无法获取总页数: %s' % mainUrl)
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
            self.retry_failed_pages(index)
        
        print(title, '完成',sep='/n------------------------------/n')

    def save_img(self, browser, index, folder_path, counts):
        """从已打开的页面中提取图片并保存到本地。"""
        elem = browser.find_element_by_id("images").find_element_by_tag_name("img")
        pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
        r = re.search(r'\((.*)/(.*)\)', pagestr)
        curp = int(r.group(1))
        url = elem.get_attribute('src')
        html = requests.get(url)
        img_name = str(index + 1) + '-' + str(curp) + '.png'
        image = Image.open(BytesIO(html.content))
        image.save(folder_path + '/' + img_name)
        time.sleep(1)

    def brower_data(self, mainUrl, counts, folder, record_failure=True):
        """打开指定章节页，失败时记录可重试的页码信息。"""
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
            if record_failure:
                self.mark_failed_page(mainUrl, counts, folder)
            browser.quit()
            return None
        return browser

    def threadRun(self, index, folder_path, mainUrl, counts):
        """线程入口，下载单页图片并确保信号量和浏览器资源被释放。"""
        self.pool_sema.acquire() # 加锁
        browser = None
        try:
            browser = self.brower_data(mainUrl, counts, folder_path)
            if browser is not None:
                try:
                    self.save_img(browser, index, folder_path, counts)
                except Exception as e:
                    print('当前图片保存异常啦', e)
                    self.mark_failed_page(mainUrl, counts, folder_path)
        finally:
            self.pool_sema.release() # 释放
            if browser is not None:
                browser.quit()

    def list_split(self, items, n):
        """按照固定步长切分页码列表。"""
        return [items[i:i+n] for i in range(0, len(items), n)]

    def mark_failed_page(self, mainUrl, counts, folder):
        """记录失败页，避免同一页重复入队导致重试列表无限增长。"""
        failed_item = {'index': counts, 'url': mainUrl, 'folder': folder}
        if failed_item not in self.exList:
            self.exList.append(failed_item)

    def clear_failed_page(self, failed_item):
        """在失败页重试成功后，从重试列表中清除对应记录。"""
        if failed_item in self.exList:
            self.exList.remove(failed_item)

    def retry_failed_pages(self, index):
        """重试失败页并在达到上限后显式失败，避免永久循环。"""
        for attempt in range(1, self.max_retry_attempts + 1):
            if len(self.exList) == 0:
                return
            for failed_item in list(self.exList):
                browser = self.brower_data(
                    failed_item['url'],
                    failed_item['index'],
                    failed_item['folder'],
                    record_failure=False
                )
                if browser is None:
                    continue
                try:
                    self.save_img(browser, index, failed_item['folder'], failed_item['index'])
                    self.clear_failed_page(failed_item)
                except Exception as e:
                    print('重试图片保存异常啦', e)
                finally:
                    browser.quit()
            if len(self.exList) > 0:
                print('第%s次重试后仍有失败页: %s' % (attempt, self.exList))
        if len(self.exList) > 0:
            raise RuntimeError('页面重试达到上限仍失败: %s' % self.exList)