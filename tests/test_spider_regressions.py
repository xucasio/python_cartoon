import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest import mock


class FakeChromeOptions(object):
    def __init__(self):
        self.arguments = []

    def add_argument(self, argument):
        self.arguments.append(argument)


class FakeBrowser(object):
    def __init__(self):
        self.quit_called = False

    def quit(self):
        self.quit_called = True


class FakeCollection(object):
    def insert_one(self, item):
        return item


class FakeDatabase(object):
    def __getitem__(self, name):
        return FakeCollection()


class FakeMongoClient(object):
    def __init__(self, *args, **kwargs):
        pass

    def __getitem__(self, name):
        return FakeDatabase()


def install_fake_dependencies():
    selenium_module = types.ModuleType('selenium')
    webdriver_module = types.ModuleType('selenium.webdriver')
    webdriver_module.ChromeOptions = FakeChromeOptions
    webdriver_module.Chrome = lambda chrome_options=None: FakeBrowser()
    selenium_module.webdriver = webdriver_module
    sys.modules['selenium'] = selenium_module
    sys.modules['selenium.webdriver'] = webdriver_module

    pil_module = types.ModuleType('PIL')
    image_module = types.ModuleType('PIL.Image')
    image_module.open = lambda stream: mock.Mock()
    pil_module.Image = image_module
    sys.modules['PIL'] = pil_module
    sys.modules['PIL.Image'] = image_module

    pymongo_module = types.ModuleType('pymongo')
    pymongo_module.MongoClient = FakeMongoClient
    sys.modules['pymongo'] = pymongo_module

    bs4_module = types.ModuleType('bs4')
    bs4_module.BeautifulSoup = lambda content, parser: mock.Mock(select=lambda selector: [])
    sys.modules['bs4'] = bs4_module


class HtmlOutputerRetryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_fake_dependencies()
        cls.html_outputer = importlib.import_module('html_outputer')

    def test_retry_failed_items_uses_retry_dict_and_clears_success(self):
        outputer = self.html_outputer.HtmlOutputer()
        browser = FakeBrowser()
        outputer._add_retry_item(2, 'https://example.test/chapter', './chapter')

        def save_success(_browser, _index, folder, counts):
            outputer._remove_retry_item(counts, folder)

        with mock.patch.object(outputer, 'brower_data', return_value=browser) as brower_data:
            with mock.patch.object(outputer, 'save_img', side_effect=save_success) as save_img:
                outputer._retry_failed_items(7)

        brower_data.assert_called_once_with('https://example.test/chapter', 2, './chapter')
        save_img.assert_called_once_with(browser, 7, './chapter', 2)
        self.assertTrue(browser.quit_called)
        self.assertEqual([], outputer.exList)

    def test_thread_run_releases_semaphore_and_browser_on_save_error(self):
        outputer = self.html_outputer.HtmlOutputer()
        browser = FakeBrowser()

        with mock.patch.object(outputer, 'brower_data', return_value=browser):
            with mock.patch.object(outputer, 'save_img', side_effect=RuntimeError('boom')):
                with self.assertRaises(RuntimeError):
                    outputer.threadRun(0, './chapter', 'https://example.test/chapter', 1)

        acquired = 0
        for _ in range(outputer.max_connections):
            if outputer.pool_sema.acquire(blocking=False):
                acquired += 1
        for _ in range(acquired):
            outputer.pool_sema.release()

        self.assertEqual(outputer.max_connections, acquired)
        self.assertTrue(browser.quit_called)


class MainRetryQueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_fake_dependencies()
        cls.main = importlib.import_module('main')

    def test_retry_items_returns_dict_entries(self):
        spider = self.main.SpiderMain()
        spider.add_exception('1', 'https://example.test/page?p=1')

        retry_item = spider.retry_items()[0]

        self.assertEqual('1', retry_item['index'])
        self.assertEqual('https://example.test/page?p=1', retry_item['url'])


class StaticSpiderPathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_fake_dependencies()
        cls.static_spider = importlib.import_module('staticSpider')

    def test_craw_changes_into_created_book_directory_on_linux(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                spider = self.static_spider.SpiderMain()
                with mock.patch.object(self.static_spider.requests, 'get', return_value=mock.Mock(content=b'')):
                    spider.craw('https://example.test/root', 'https://example.test/', 'book')

                self.assertEqual(os.path.join(tmpdir, 'book'), os.getcwd())
            finally:
                os.chdir(old_cwd)


if __name__ == '__main__':
    unittest.main()
