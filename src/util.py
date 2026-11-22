import re

def contains_korean(text):
    """문장이 한국어인지 확인"""
    return bool(re.search("[\uac00-\ud7a3]", text))