import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest import mock


def import_html_outputer():
    """使用轻量假模块导入图片输出器，避免测试依赖真实浏览器。"""
    sys.modules.pop('html_outputer', None)

    selenium = types.ModuleType('selenium')
    webdriver = types.ModuleType('selenium.webdriver')

    class FakeChromeOptions(object):
        def add_argument(self, value):
            pass

    class FakeChrome(object):
        def get(self, url):
            pass

        def quit(self):
            pass

    webdriver.ChromeOptions = FakeChromeOptions
    webdriver.Chrome = lambda chrome_options=None: FakeChrome()
    selenium.webdriver = webdriver

    pil = types.ModuleType('PIL')
    pil_image = types.SimpleNamespace(open=lambda content: None)
    pil.Image = pil_image

    requests = types.ModuleType('requests')
    requests.get = lambda *args, **kwargs: types.SimpleNamespace(content=b'')

    with mock.patch.dict(sys.modules, {
        'selenium': selenium,
        'selenium.webdriver': webdriver,
        'PIL': pil,
        'PIL.Image': pil_image,
        'requests': requests,
    }):
        return importlib.import_module('html_outputer')


class HtmlOutputerRetryTest(unittest.TestCase):
    """图片下载失败队列的回归测试。"""

    def test_retry_uses_failure_dict_and_clears_successful_page(self):
        html_outputer = import_html_outputer()
        outputer = html_outputer.HtmlOutputer()
        browsers = []

        class FakeBrowser(object):
            def __init__(self):
                self.closed = False

            def quit(self):
                self.closed = True

        def fake_browser(main_url, counts, folder):
            browser = FakeBrowser()
            browsers.append(browser)
            return browser

        def fake_save(browser, chapter_index, folder, counts, main_url=None):
            outputer._clear_failure(counts, main_url, folder)

        outputer.brower_data = fake_browser
        outputer.save_img = fake_save
        outputer.exList = [{'index': 2, 'url': 'http://comic/chapter', 'folder': './chapter'}]

        outputer._retry_failures(chapter_index=0, max_retries=1)

        self.assertEqual([], outputer.exList)
        self.assertTrue(all(browser.closed for browser in browsers))

    def test_thread_run_releases_semaphore_when_download_raises(self):
        html_outputer = import_html_outputer()
        outputer = html_outputer.HtmlOutputer()
        outputer.pool_sema = html_outputer.threading.BoundedSemaphore(1)

        class FakeBrowser(object):
            def quit(self):
                pass

        outputer.brower_data = lambda main_url, counts, folder: FakeBrowser()

        def fail_save(*args, **kwargs):
            raise RuntimeError('download failed')

        outputer.save_img = fail_save

        outputer.threadRun(0, './chapter', 'http://comic/chapter', 1)

        self.assertTrue(outputer.pool_sema.acquire(blocking=False))
        outputer.pool_sema.release()
        self.assertEqual(
            [{'index': 1, 'url': 'http://comic/chapter', 'folder': './chapter'}],
            outputer.exList,
        )


class StaticSpiderPathTest(unittest.TestCase):
    """漫画目录切换的跨平台回归测试。"""

    def test_craw_uses_platform_path_and_restores_working_directory(self):
        sys.modules.pop('staticSpider', None)

        html_outputer = types.ModuleType('html_outputer')
        html_outputer.HtmlOutputer = lambda: types.SimpleNamespace(output_img=lambda *args: None)

        db_option = types.ModuleType('db_option')
        db_option.dbOption = lambda: types.SimpleNamespace(insertOne=lambda *args: None)

        requests = types.ModuleType('requests')
        requests.get = lambda *args, **kwargs: types.SimpleNamespace(content=b'<html></html>')

        bs4 = types.ModuleType('bs4')
        bs4.BeautifulSoup = lambda content, parser: types.SimpleNamespace(select=lambda selector: [])

        with mock.patch.dict(sys.modules, {
            'html_outputer': html_outputer,
            'db_option': db_option,
            'requests': requests,
            'bs4': bs4,
        }):
            static_spider = importlib.import_module('staticSpider')

        origin_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                spider = static_spider.SpiderMain()
                spider.craw('http://comic/list', 'http://comic/', 'book')

                self.assertEqual(tmpdir, os.getcwd())
                self.assertTrue(os.path.isdir(os.path.join(tmpdir, 'book')))
            finally:
                os.chdir(origin_cwd)


if __name__ == '__main__':
    unittest.main()
