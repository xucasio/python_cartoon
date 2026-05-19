import importlib
import sys
import types
import unittest
from unittest import mock


def install_fake_modules():
    """安装轻量假模块，避免测试依赖真实浏览器、数据库和网络库。"""
    selenium = types.ModuleType('selenium')
    webdriver = types.ModuleType('selenium.webdriver')

    class FakeChromeOptions(object):
        def add_argument(self, _argument):
            pass

    webdriver.ChromeOptions = FakeChromeOptions
    webdriver.Chrome = lambda *args, **kwargs: None
    selenium.webdriver = webdriver
    sys.modules.setdefault('selenium', selenium)
    sys.modules.setdefault('selenium.webdriver', webdriver)

    pil = types.ModuleType('PIL')
    image_module = types.ModuleType('PIL.Image')
    image_module.open = lambda _stream: None
    pil.Image = image_module
    sys.modules.setdefault('PIL', pil)
    sys.modules.setdefault('PIL.Image', image_module)

    pymongo = types.ModuleType('pymongo')

    class FakeMongoClient(object):
        def __init__(self, *args, **kwargs):
            pass

        def __getitem__(self, _name):
            return self

        def insert_one(self, _item):
            pass

    pymongo.MongoClient = FakeMongoClient
    sys.modules.setdefault('pymongo', pymongo)

    bs4 = types.ModuleType('bs4')

    class FakeBeautifulSoup(object):
        def __init__(self, *args, **kwargs):
            pass

        def select(self, _selector):
            return []

    bs4.BeautifulSoup = FakeBeautifulSoup
    sys.modules.setdefault('bs4', bs4)


class SpiderRegressionTest(unittest.TestCase):
    """覆盖近期失败恢复路径中的高危回归。"""

    def setUp(self):
        install_fake_modules()

    def test_html_outputer_retry_uses_failed_dict_items(self):
        html_outputer = importlib.reload(importlib.import_module('html_outputer'))
        outputer = html_outputer.HtmlOutputer()
        outputer.exList = [{'index': 2, 'url': 'https://example/chapter', 'folder': './book'}]
        calls = []

        class FakeBrowser(object):
            def __init__(self):
                self.quit_called = False

            def quit(self):
                self.quit_called = True

        def fake_browser(url, page_index, folder):
            calls.append((url, page_index, folder))
            return FakeBrowser()

        def fake_save(_browser, _index, folder, page_index, main_url=None):
            outputer._remove_failed(page_index, folder, main_url)

        outputer.brower_data = fake_browser
        outputer.save_img = fake_save

        outputer._retry_failed(index=0)

        self.assertEqual([('https://example/chapter', 2, './book')], calls)
        self.assertEqual([], outputer.exList)

    def test_html_outputer_thread_releases_semaphore_on_failure(self):
        html_outputer = importlib.reload(importlib.import_module('html_outputer'))
        outputer = html_outputer.HtmlOutputer()

        class FakeBrowser(object):
            def __init__(self):
                self.quit_called = False

            def quit(self):
                self.quit_called = True

        browser = FakeBrowser()
        outputer.brower_data = lambda *_args: browser

        def raise_save(*_args):
            raise RuntimeError('save failed')

        outputer.save_img = raise_save

        outputer.threadRun(0, './book', 'https://example/chapter', 1)

        acquired = outputer.pool_sema.acquire(blocking=False)
        try:
            self.assertTrue(acquired)
            self.assertTrue(browser.quit_called)
            self.assertEqual(
                [{'index': 1, 'url': 'https://example/chapter', 'folder': './book'}],
                outputer.exList,
            )
        finally:
            if acquired:
                outputer.pool_sema.release()

    def test_main_retry_uses_recorded_url(self):
        main = importlib.reload(importlib.import_module('main'))
        spider = main.SpiderMain()
        spider.exList = [{'index': '1', 'url': 'https://example/page?p=1'}]
        calls = []

        def fake_craw(url, index):
            calls.append((url, index))
            spider._remove_failed(index, url)

        spider.craw = fake_craw

        spider.retry_failed()

        self.assertEqual([('https://example/page?p=1', '1')], calls)
        self.assertEqual([], spider.exList)

    def test_static_spider_uses_portable_book_path(self):
        static_spider = importlib.reload(importlib.import_module('staticSpider'))
        spider = static_spider.SpiderMain()

        with mock.patch.object(static_spider.os, 'getcwd', return_value='/tmp/base'), \
                mock.patch.object(static_spider.os.path, 'exists', return_value=True), \
                mock.patch.object(static_spider.os, 'chdir') as chdir_mock, \
                mock.patch.object(static_spider.requests, 'get') as get_mock:
            get_mock.return_value = types.SimpleNamespace(content=b'<html></html>')
            spider.craw('https://example/comic', 'https://example/', 'book')

        chdir_mock.assert_called_once_with('/tmp/base/book')


if __name__ == '__main__':
    unittest.main()
