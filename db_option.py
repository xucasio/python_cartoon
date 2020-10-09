import pymongo
class dbOption(object):
    def __init__(self):
        self.collections = []
        self.client = pymongo.MongoClient('localhost', 27017)
        self.cartoon = self.client['cartoon']
        self.themes = self.cartoon['theme']
        self.chapters = self.cartoon['chapter']
        self.contents = self.cartoon['content']
    def insert(self,items,ty):
        for item in items:
            if ty == 'theme':
                self.themes.insert_one(item)
            elif ty == 'chapter':
                self.chapters.insert_one(item)
            elif ty == 'content':
                self.contents.insert_one(item)
    def insertOne(self,item,ty):
        if ty == 'theme':
            self.themes.insert_one(item)
        elif ty == 'chapter':
            self.chapters.insert_one(item)
        elif ty == 'content':
            self.contents.insert_one(item)
          