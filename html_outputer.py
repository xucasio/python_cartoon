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
    def __init__(self):
        self.datas = []
        self.exList = []  # 单次线程里的异常爬取
        self.max_connections = 5  # 定义最大线程数
        self.pool_sema = threading.BoundedSemaphore(self.max_connections)

    def collect_data(self, data):
        if data is None:
            return 0
        self.datas.append(data)

    def output_html(self):
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
        folder_path = './' + title
        counts = 1
        if os.path.exists(folder_path) is False:
            os.makedirs(folder_path)
        browser = self.brower_data(mainUrl, counts, folder_path)
        pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
        r = re.search('\((.*)/(.*)\)', pagestr)
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
            while len(self.exList) > 0:
                for item in enumerate(list(self.exList)):
                    browser = self.brower_data(item['url'], item['index'], item['folder'])
                    self.save_img(browser, index, item['folder'], item['index'])
        
        print(title, '完成',sep='/n------------------------------/n')

    def save_img(self, browser, index, folder_path, counts):
        elem = browser.find_element_by_id("images").find_element_by_tag_name("img")
        pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
        r = re.search('\((.*)/(.*)\)', pagestr)
        curp = int(r.group(1))
        url = elem.get_attribute('src')
        html = requests.get(url)
        img_name = str(index + 1) + '-' + str(curp) + '.png'
        image = Image.open(BytesIO(html.content))
        for item in self.exList:
            if item['url'] == url:
                self.exList.remove({'index': counts, 'url': url, 'folder': folder_path})
        image.save(folder_path + '/' + img_name)
        time.sleep(1)

    def brower_data(self, mainUrl, counts, folder):
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
            self.exList.append({'index': counts, 'url': mainUrl, 'folder': folder})
        return browser

    def threadRun(self, index, folder_path, mainUrl, counts):
        self.pool_sema.acquire() # 加锁
        browser = self.brower_data(mainUrl, counts, folder_path)
        self.save_img(browser, index, folder_path, counts)
        self.pool_sema.release() # 释放
        browser.quit()

    def list_split(self, items, n):
      return [items[i:i+n] for i in range(0, len(items), n)]