import importlib
import os
import sys
import tempfile
import types
import unittest


class FakeResponse(object):
    """requests.get 返回值的最小替身。"""

    content = b"image-content"


class FakeImage(object):
    """PIL Image 替身，记录保存路径以验证保存流程。"""

    saved_paths = []

    def save(self, path):
        self.saved_paths.append(path)


class FakeImageModule(object):
    """提供 Image.open 的最小实现，避免测试依赖真实图片解析。"""

    @staticmethod
    def open(_content):
        return FakeImage()


def import_fresh(module_name):
    """重新导入模块，确保每个测试使用当前注入的假依赖。"""
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


class StaticSpiderPathTest(unittest.TestCase):
    def test_craw_changes_into_created_book_directory_with_os_separator(self):
        """Linux 下应进入 bookname 子目录，而不是反斜杠拼出的不存在路径。"""
        fake_requests = types.ModuleType("requests")
        fake_requests.get = lambda *_args, **_kwargs: FakeResponse()

        fake_bs4 = types.ModuleType("bs4")
        fake_bs4.BeautifulSoup = lambda *_args, **_kwargs: types.SimpleNamespace(select=lambda _selector: [])

        fake_html_outputer = types.ModuleType("html_outputer")
        fake_html_outputer.HtmlOutputer = lambda: types.SimpleNamespace()

        fake_db_option = types.ModuleType("db_option")
        fake_db_option.dbOption = lambda: types.SimpleNamespace(insertOne=lambda *_args, **_kwargs: None)

        original_modules = {
            "requests": sys.modules.get("requests"),
            "bs4": sys.modules.get("bs4"),
            "html_outputer": sys.modules.get("html_outputer"),
            "db_option": sys.modules.get("db_option"),
            "staticSpider": sys.modules.get("staticSpider"),
        }
        original_cwd = os.getcwd()

        try:
            sys.modules["requests"] = fake_requests
            sys.modules["bs4"] = fake_bs4
            sys.modules["html_outputer"] = fake_html_outputer
            sys.modules["db_option"] = fake_db_option

            static_spider = import_fresh("staticSpider")

            with tempfile.TemporaryDirectory() as temp_dir:
                os.chdir(temp_dir)
                static_spider.SpiderMain().craw("http://example.test/book", "http://example.test/", "Book")

                self.assertEqual(os.getcwd(), os.path.join(temp_dir, "Book"))
                self.assertTrue(os.path.isdir(os.path.join(temp_dir, "Book")))
        finally:
            os.chdir(original_cwd)
            for name, module in original_modules.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module


class FakeElement(object):
    """Selenium 元素替身，返回图片地址和页码文本。"""

    text = "(1/1)"

    def get_attribute(self, name):
        if name == "src":
            return "http://example.test/image.png"
        return None

    def find_element_by_tag_name(self, _name):
        return self

    def find_element_by_class_name(self, _name):
        return self


class FakeBrowser(object):
    """Selenium 浏览器替身，支持输出器读取页面信息和释放资源。"""

    def __init__(self):
        self.quit_called = False

    def find_element_by_id(self, _name):
        return FakeElement()

    def quit(self):
        self.quit_called = True


class HtmlOutputerRetryTest(unittest.TestCase):
    def setUp(self):
        self.original_modules = {
            "selenium": sys.modules.get("selenium"),
            "requests": sys.modules.get("requests"),
            "PIL": sys.modules.get("PIL"),
            "html_outputer": sys.modules.get("html_outputer"),
        }

        fake_webdriver = types.SimpleNamespace(ChromeOptions=lambda: types.SimpleNamespace(add_argument=lambda *_: None))
        fake_selenium = types.ModuleType("selenium")
        fake_selenium.webdriver = fake_webdriver

        fake_requests = types.ModuleType("requests")
        fake_requests.get = lambda *_args, **_kwargs: FakeResponse()

        fake_pil = types.ModuleType("PIL")
        fake_pil.Image = FakeImageModule

        sys.modules["selenium"] = fake_selenium
        sys.modules["requests"] = fake_requests
        sys.modules["PIL"] = fake_pil

        self.html_outputer = import_fresh("html_outputer")
        self.html_outputer.time.sleep = lambda _seconds: None

    def tearDown(self):
        for name, module in self.original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_save_img_clears_failed_page_after_successful_retry(self):
        """保存成功后按页码和目录移除异常项，避免同一页被无限重试。"""
        outputer = self.html_outputer.HtmlOutputer()
        outputer.exList = [{"index": 1, "url": "http://example.test/chapter", "folder": "./chapter"}]

        outputer.save_img(FakeBrowser(), 0, "./chapter", 1)

        self.assertEqual([], outputer.exList)

    def test_output_img_retries_failed_item_from_snapshot(self):
        """异常重试应遍历字典快照，不能把 enumerate 结果当作异常项。"""

        class RetryOutputer(self.html_outputer.HtmlOutputer):
            def __init__(self):
                super(RetryOutputer, self).__init__()
                self.retried_items = []

            def brower_data(self, mainUrl, counts, folder):
                self.retried_items.append((mainUrl, counts, folder))
                return FakeBrowser()

            def threadRun(self, _index, folder_path, mainUrl, counts):
                self.exList.append({"index": counts, "url": mainUrl, "folder": folder_path})

            def save_img(self, _browser, _index, folder_path, counts):
                self.exList = [
                    item for item in self.exList
                    if not (item["index"] == counts and item["folder"] == folder_path)
                ]

        outputer = RetryOutputer()
        original_cwd = os.getcwd()

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                os.chdir(temp_dir)
                outputer.output_img("http://example.test/chapter", "chapter", 0)

            self.assertEqual(
                [
                    ("http://example.test/chapter", 1, "./chapter"),
                    ("http://example.test/chapter", 1, "./chapter"),
                ],
                outputer.retried_items,
            )
        finally:
            os.chdir(original_cwd)


class MainRetryTest(unittest.TestCase):
    def test_retry_exceptions_uses_recorded_failed_url_and_index(self):
        """主入口失败重试必须使用异常项自己的 URL，避免重复下载错误页。"""
        fake_webdriver = types.SimpleNamespace(
            ChromeOptions=lambda: types.SimpleNamespace(add_argument=lambda *_: None)
        )
        fake_selenium = types.ModuleType("selenium")
        fake_selenium.webdriver = fake_webdriver

        original_modules = {
            "selenium": sys.modules.get("selenium"),
            "requests": sys.modules.get("requests"),
            "PIL": sys.modules.get("PIL"),
            "main": sys.modules.get("main"),
        }

        try:
            fake_requests = types.ModuleType("requests")
            fake_requests.get = lambda *_args, **_kwargs: FakeResponse()
            fake_pil = types.ModuleType("PIL")
            fake_pil.Image = FakeImageModule

            sys.modules["selenium"] = fake_selenium
            sys.modules["requests"] = fake_requests
            sys.modules["PIL"] = fake_pil
            main = import_fresh("main")

            class RetrySpider(main.SpiderMain):
                def __init__(self):
                    self.exList = [{"index": "2", "url": "http://example.test/page?p=2"}]
                    self.calls = []

                def craw(self, root_url, index):
                    self.calls.append((root_url, index))
                    self.exList = []

            spider = RetrySpider()

            spider.retry_exceptions()

            self.assertEqual([("http://example.test/page?p=2", "2")], spider.calls)
        finally:
            for name, module in original_modules.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module


if __name__ == "__main__":
    unittest.main()
