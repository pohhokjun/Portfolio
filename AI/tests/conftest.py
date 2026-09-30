"""离线测试：不调模型、不花钱。工作区/记忆指到临时目录，不碰正式数据。"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

家 = tempfile.mkdtemp(prefix="ai12_")
os.environ.update(AI_HOME=家, BIZ="示例")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from 核心 import 业务, 审批  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _环境():
    业务.模块()
    yield
    shutil.rmtree(家, ignore_errors=True)


@pytest.fixture
def 自动批(request):
    审批.自动 = {"批": True, "答": "按月汇总"}
    yield 审批.自动
    审批.自动 = None


def 单(**kw):
    return {"编号": "T9999", "需求": "测试", "来源": "测试", "会话": None, "交付": [], "工具": [], "开工": 0, **kw}
