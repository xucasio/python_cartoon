# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import requests
import re
from PIL import Image
import time
import os
from io import BytesIO
class HtmlOutputer(object):

    def __init__(self):
        self.datas = []

    def collect_data(self,data):
        if data is None:
            return
        self.datas.append(data)

    def output_html(self):
        fout= open('output.html','w',encoding='utf-8')
        fout.write("<html>")
        fout.write("<body>")
        fout.write("<div id='content'>")
        fout.write("<ul>")
        for data in self.datas:
          fout.write("<li class='item'>")
          fout.write("<a href='%s'>%s</a>"% (data['url'], data['title']))
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
        browser = self.brower_data(mainUrl)
        contin = self.save_img(browser, index, folder_path) # 是否继续
        while contin:
          counts += 1
          browser = self.brower_data(mainUrl + '?p=' + str(counts))
          contin = self.save_img(browser, index, folder_path)
        browser.quit()
    def save_img(self, browser,index, folder_path):
        elem = browser.find_element_by_id("images").find_element_by_tag_name("img")
        pagestr = browser.find_element_by_id("images").find_element_by_class_name("img_info").text
        r = re.search('\((.*)/(.*)\)', pagestr)
        curp = int(r.group(1))
        surp = int(r.group(2))
        url = elem.get_attribute('src')
        html = requests.get(url)
        img_name = str(index+1) +'-'+str(curp) + '.png'
        image = Image.open(BytesIO(html.content))
        image.save(folder_path +'/'+ img_name)
        time.sleep(1)
        return curp <= surp

    def brower_data(self, mainUrl):
        chrome_options = webdriver.ChromeOptions()
        # 使用headless无界面浏览器模式
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        # 启动浏览器，获取网页源代码
        browser = webdriver.Chrome(chrome_options=chrome_options)
        browser.get(mainUrl)
        return browser