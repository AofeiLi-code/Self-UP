"""
conftest.py — 将 backend/ 加入 sys.path，使测试可直接导入 services、models 等模块。
"""

import sys
from pathlib import Path

# 将 backend/ 目录加入模块搜索路径
sys.path.insert(0, str(Path(__file__).parent.parent))
