import requests
from bs4 import BeautifulSoup
import html_outputer
import db_option
import os

class SpiderMain(object):
    def __init__(self):
        self.outputer = html_outputer.HtmlOutputer()
        self.dboption = db_option.dbOption()

    def craw(self, root_url, web_path, bookname):
        headers = {
            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"
        }
        if os.path.exists(bookname) is False:
            os.makedirs(bookname)
        retval = os.getcwd()
        os.chdir(retval + '\\' + bookname)
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


if __name__ == "__main__":
    web_path = 'https://www.manhuafen.com/'
    # root_url = "https://m.manhuafen.com/comic/39/"
    root_url = str(input('请输入漫画粉要爬取的目录地址'))
    bookname = str(input('请输入漫画名称'))
    obj_spider = SpiderMain()
    obj_spider.craw(root_url, web_path, bookname)
