# 多线程 +selenium
from selenium import webdriver
import threading
import requests
import os
import logging
from PIL import Image
from io import BytesIO
import time

logger = logging.getLogger(__name__)

chrome_options = webdriver.ChromeOptions()
# 使用headless无界面浏览器模式
chrome_options.add_argument('--headless')  # 增加无界面选项
chrome_options.add_argument('--disable-gpu')  # 如果不加这个选项，有时定位会出现问题

headers = {
    "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"
}


class SpiderMain(object):
    """固定章节页面的多线程图片爬虫。"""

    def __init__(self):
        self.exList = []  # 异常列表

    def craw(self, root_url, index):
        """抓取并保存单个图片页，失败时记录待重试任务。"""
        # 启动浏览器，获取网页源代码
        browser = webdriver.Chrome(chrome_options=chrome_options)
        try:
            browser.get(root_url)
            url = browser.find_element_by_id("images").find_element_by_tag_name(
                "img").get_attribute('src')

            folder_path = './photo'
            if os.path.exists(folder_path) is False:
                os.makedirs(folder_path)
            html = requests.get(url)
            if html is not None:
                img_name = 'jjjr_' + index + '.png'
                image = Image.open(BytesIO(html.content))
                image.save(folder_path + '/' + img_name)
                self._remove_failed(index, root_url)
                time.sleep(1)  # 自定义延时
        except Exception as e:
            print('当前进程异常啦', index, e)
            logger.exception('图片页爬取失败: %s', root_url)
            self._record_failed(index, root_url)
        finally:
            browser.quit()

    def retry_failed(self, max_retry=3):
        """重试失败图片页；连续无进展时终止，避免无限循环。"""
        retry_count = 0
        while len(self.exList) > 0 and retry_count < max_retry:
            retry_items = list(self.exList)
            before_count = len(self.exList)
            for item in retry_items:
                self.craw(item['url'], item['index'])
            if len(self.exList) >= before_count:
                break
            retry_count += 1
        if len(self.exList) > 0:
            raise RuntimeError('图片重试失败，剩余 %s 个任务' % len(self.exList))

    def _record_failed(self, index, root_url):
        """记录失败任务，并避免重试列表出现重复条目。"""
        failed_item = {'index': index, 'url': root_url}
        if failed_item not in self.exList:
            self.exList.append(failed_item)

    def _remove_failed(self, index, root_url):
        """图片保存成功后清理对应失败记录。"""
        self.exList = [
            item for item in self.exList
            if not (item.get('index') == index and item.get('url') == root_url)
        ]


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
    obj_spider.retry_failed()
    print('完成捕捉')
