#!/usr/bin/env python3
"""
utils.py — 项目公共工具箱

集中存放多个脚本中反复出现的工具函数，避免重复实现。

当前包含：
  - similarity()        两个字符串相似度比较（SequenceMatcher）
  - clean_source_tag()  去掉 [来源:xxx] 标签
  - clean_all_brackets()去掉所有 [...] 标签（范围更广）
  - extract_source_tags() 提取 [来源:xxx] 标签

用法：
    from utils import similarity, clean_source_tag
"""

import re
from difflib import SequenceMatcher


def similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度（0~1）。"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def clean_source_tag(text: str) -> str:
    """去掉 [来源:xxx] 标签，保留正文。"""
    return re.sub(r"\s*\[来源:.+?\]", "", text).strip()


def clean_all_brackets(text: str) -> str:
    """
    去掉所有 [...] 标签。
    比 clean_source_tag 范围更广——用于 ADR 去重等需要完全清除标记的场景。
    """
    return re.sub(r"\s*\[[^\]]*\]", "", text).strip()


def extract_source_tags(line: str) -> list:
    """从文本中提取所有 [来源:xxx] 标签。"""
    return re.findall(r"\[来源:[^\]]+\]", line)
