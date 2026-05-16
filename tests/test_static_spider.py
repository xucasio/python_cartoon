import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest import mock


class StaticSpiderPathTest(unittest.TestCase):
    """staticSpider 的目录处理回归测试。"""

    def setUp(self):
        self._modules_to_restore = {
            name: sys.modules.get(name)
            for name in ("requests", "bs4", "html_outputer", "db_option", "staticSpider")
        }
        for name in self._modules_to_restore:
            sys.modules.pop(name, None)

        fake_requests = types.ModuleType("requests")
        fake_requests.get = mock.Mock(return_value=types.SimpleNamespace(content=b"<html></html>"))

        fake_bs4 = types.ModuleType("bs4")

        class FakeSoup(object):
            def __init__(self, content, parser):
                self.content = content
                self.parser = parser

            def select(self, selector):
                return []

        fake_bs4.BeautifulSoup = FakeSoup

        fake_html_outputer = types.ModuleType("html_outputer")

        class FakeHtmlOutputer(object):
            def output_img(self, url, title, index):
                raise AssertionError("空章节列表不应触发图片输出")

        fake_html_outputer.HtmlOutputer = FakeHtmlOutputer

        fake_db_option = types.ModuleType("db_option")

        class FakeDbOption(object):
            def insertOne(self, item, ty):
                raise AssertionError("空章节列表不应写入数据库")

        fake_db_option.dbOption = FakeDbOption

        sys.modules.update({
            "requests": fake_requests,
            "bs4": fake_bs4,
            "html_outputer": fake_html_outputer,
            "db_option": fake_db_option,
        })
        self.fake_requests = fake_requests

    def tearDown(self):
        for name, module in self._modules_to_restore.items():
            sys.modules.pop(name, None)
            if module is not None:
                sys.modules[name] = module

    def test_craw_uses_platform_path_and_restores_cwd(self):
        """Linux 下应切入真实漫画目录，结束后恢复调用方工作目录。"""
        static_spider = importlib.import_module("staticSpider")

        with tempfile.TemporaryDirectory() as temp_dir:
            original_dir = os.getcwd()
            try:
                os.chdir(temp_dir)
                static_spider.SpiderMain().craw(
                    "https://example.test/comic/1/",
                    "https://example.test/",
                    "book",
                )
                self.assertTrue(os.path.isdir(os.path.join(temp_dir, "book")))
                self.assertEqual(temp_dir, os.getcwd())
                self.fake_requests.get.assert_called_once()
            finally:
                os.chdir(original_dir)


if __name__ == "__main__":
    unittest.main()
