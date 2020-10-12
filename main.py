# 多线程 +selenium
from selenium import webdriver
import threading
import requests
import os
from PIL import Image
from io import BytesIO
import time
chrome_options = webdriver.ChromeOptions()
# 使用headless无界面浏览器模式
chrome_options.add_argument('--headless')  # 增加无界面选项
chrome_options.add_argument('--disable-gpu')  # 如果不加这个选项，有时定位会出现问题

headers = {
    "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"
}


class SpiderMain(object):
    def __init__(self):
        self.exList = []  # 异常列表

    def craw(self, root_url, index):
        # 启动浏览器，获取网页源代码
        browser = webdriver.Chrome(chrome_options=chrome_options)
        try:
            browser.get(root_url)
        except Exception as e:
            print('当前进程异常啦', index, e)
            self.exList.append({'index': index, 'url': root_url})
        url = browser.find_element_by_id("images").find_element_by_tag_name(
            "img").get_attribute('src')

        folder_path = './photo'
        if os.path.exists(folder_path) is False:
            os.makedirs(folder_path)
        html = requests.get(url)
        if html is not None:
            img_name = 'jjjr_' + index + '.png'
            image = Image.open(BytesIO(html.content))
            for item in self.exList:
                if item['url'] == root_url:
                    self.exList.remove({'index': index, 'url': root_url})
            image.save(folder_path + '/' + img_name)
            time.sleep(1)  # 自定义延时

        browser.quit()


if __name__ == "__main__":
    obj_spider = SpiderMain()
    threads = {}
    for p in range(1, 5):
        root_url = "https://m.manhuafen.com/comic/39/372855.html?p=" + str(p)
        # obj_spider.craw(root_url)
        threads['t' + str(p)] = threading.Thread(target=obj_spider.craw,
                                                 args=(root_url, str(p)))
        threads['t' + str(p)].start()
    for p in range(1, 5):
        threads['t' + str(p)].join()
    print('异常列表', obj_spider.exList)
    while len(obj_spider.exList) > 0:
        for item in enumerate(obj_spider.exList):
            obj_spider.craw(root_url, item['index'])
    print('完成捕捉')
