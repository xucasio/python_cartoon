import importlib
import os
import sys
import tempfile
import types
import unittest


class FakeChapterSoup(object):
    """测试用章节列表解析器，避免真实网络和 HTML 解析依赖。"""

    def select(self, selector):
        return []


class FakeChromeOptions(object):
    """测试用浏览器配置对象。"""

    def add_argument(self, argument):
        pass


class FakeBrowser(object):
    """测试用浏览器对象，记录资源是否被释放。"""

    def __init__(self):
        self.quit_called = False

    def get(self, url):
        pass

    def quit(self):
        self.quit_called = True


class FakeImage(object):
    """测试用图片对象。"""

    def save(self, path):
        pass


def install_static_spider_fakes():
    """安装 staticSpider 导入所需的假依赖。"""
    requests_module = types.ModuleType('requests')
    requests_module.get = lambda *args, **kwargs: types.SimpleNamespace(content=b'<html></html>')
    sys.modules['requests'] = requests_module

    bs4_module = types.ModuleType('bs4')
    bs4_module.BeautifulSoup = lambda content, parser: FakeChapterSoup()
    sys.modules['bs4'] = bs4_module

    outputer_module = types.ModuleType('html_outputer')
    outputer_module.HtmlOutputer = lambda: types.SimpleNamespace(output_img=lambda *args, **kwargs: None)
    sys.modules['html_outputer'] = outputer_module

    db_module = types.ModuleType('db_option')
    db_module.dbOption = lambda: types.SimpleNamespace(insertOne=lambda *args, **kwargs: None)
    sys.modules['db_option'] = db_module


def install_html_outputer_fakes():
    """安装 html_outputer 导入所需的假依赖。"""
    selenium_module = types.ModuleType('selenium')
    webdriver_module = types.SimpleNamespace(
        ChromeOptions=FakeChromeOptions,
        Chrome=lambda chrome_options=None: FakeBrowser()
    )
    selenium_module.webdriver = webdriver_module
    sys.modules['selenium'] = selenium_module

    requests_module = types.ModuleType('requests')
    requests_module.get = lambda *args, **kwargs: types.SimpleNamespace(content=b'img')
    sys.modules['requests'] = requests_module

    pil_module = types.ModuleType('PIL')
    image_module = types.ModuleType('PIL.Image')
    image_module.open = lambda image_bytes: FakeImage()
    pil_module.Image = image_module
    sys.modules['PIL'] = pil_module
    sys.modules['PIL.Image'] = image_module


class StaticSpiderPathTest(unittest.TestCase):
    def test_craw_changes_to_created_book_directory_on_linux(self):
        install_static_spider_fakes()
        sys.modules.pop('staticSpider', None)
        static_spider = importlib.import_module('staticSpider')

        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                static_spider.SpiderMain().craw(
                    'https://example.com/catalog',
                    'https://example.com/',
                    'book'
                )

                self.assertEqual(os.path.join(tmpdir, 'book'), os.getcwd())
            finally:
                os.chdir(original_cwd)


class HtmlOutputerRetryTest(unittest.TestCase):
    def setUp(self):
        install_html_outputer_fakes()
        sys.modules.pop('html_outputer', None)
        self.html_outputer = importlib.import_module('html_outputer')

    def test_retry_failed_pages_retries_failed_dict_and_clears_success(self):
        outputer = self.html_outputer.HtmlOutputer()
        outputer.max_retry_attempts = 1
        outputer.exList = [{'index': 2, 'url': 'chapter-url', 'folder': './chapter'}]
        browser = FakeBrowser()
        calls = []
        saves = []

        def fake_browser_data(main_url, counts, folder, record_failure=True):
            calls.append((main_url, counts, folder, record_failure))
            return browser

        def fake_save_img(browser_obj, index, folder_path, counts):
            saves.append((browser_obj, index, folder_path, counts))

        outputer.brower_data = fake_browser_data
        outputer.save_img = fake_save_img

        outputer.retry_failed_pages(7)

        self.assertEqual([], outputer.exList)
        self.assertEqual([('chapter-url', 2, './chapter', False)], calls)
        self.assertEqual([(browser, 7, './chapter', 2)], saves)
        self.assertTrue(browser.quit_called)

    def test_thread_run_records_save_failure_for_retry(self):
        outputer = self.html_outputer.HtmlOutputer()
        browser = FakeBrowser()

        outputer.brower_data = lambda *args, **kwargs: browser

        def fail_save(*args, **kwargs):
            raise RuntimeError('image decode failed')

        outputer.save_img = fail_save

        outputer.threadRun(0, './chapter', 'chapter-url', 3)

        self.assertEqual([{'index': 3, 'url': 'chapter-url', 'folder': './chapter'}], outputer.exList)
        self.assertTrue(browser.quit_called)

        acquired = 0
        for _ in range(outputer.max_connections):
            self.assertTrue(outputer.pool_sema.acquire(False))
            acquired += 1
        self.assertFalse(outputer.pool_sema.acquire(False))
        for _ in range(acquired):
            outputer.pool_sema.release()


if __name__ == '__main__':
    unittest.main()
