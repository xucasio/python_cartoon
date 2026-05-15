import requests
from bs4 import BeautifulSoup
import html_outputer
import db_option
import os
import logging


logger = logging.getLogger(__name__)

class SpiderMain(object):
    """漫画目录爬虫，负责解析章节列表并委托图片输出器下载章节图片。"""

    def __init__(self):
        """初始化章节输出器和数据库访问对象。"""
        self.outputer = html_outputer.HtmlOutputer()
        self.dboption = db_option.dbOption()

    def craw(self, root_url, web_path, bookname):
        """爬取指定漫画目录，并将章节图片保存到漫画名称对应的目录中。"""
        headers = {
            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"
        }
        retval = os.getcwd()
        book_path = os.path.abspath(bookname)
        os.makedirs(book_path, exist_ok=True)
        logger.info('开始爬取漫画目录：%s，保存目录：%s', root_url, book_path)
        try:
            os.chdir(book_path)
            r = requests.get(root_url, headers=headers)
            soup = BeautifulSoup(r.content, 'html5lib')
            items = soup.select("#chapter-list-1 li a")
            for index, item in enumerate(items):
                if item:
                    obj = {}
                    obj['url'] = web_path + item.get('href')
                    obj['title'] = item.get_text().strip()
                    self.dboption.insertOne(obj, 'chapter')
                    print('------------------执行了话的循环--------------')
                    self.outputer.output_img(obj['url'], obj['title'], index)
        finally:
            # 目录切换只服务本次漫画下载，异常时也必须恢复，避免后续相对路径写错位置。
            os.chdir(retval)


if __name__ == "__main__":
    web_path = 'https://www.manhuafen.com/'
    # root_url = "https://m.manhuafen.com/comic/39/"
    root_url = str(input('请输入漫画粉要爬取的目录地址'))
    bookname = str(input('请输入漫画名称'))
    obj_spider = SpiderMain()
    obj_spider.craw(root_url, web_path, bookname)
