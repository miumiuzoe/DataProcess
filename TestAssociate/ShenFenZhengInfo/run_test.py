"""ShenFenZhengInfo 关联功能测试入口。"""

import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
TEST_ROOT = CURRENT_DIR.parent
PROJECT_ROOT = TEST_ROOT.parent

if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from runner import AssociateTestRunner  # noqa: E402


def main() -> int:
    """仅执行 ShenFenZhengInfo 关联功能测试。"""
    runner = AssociateTestRunner(PROJECT_ROOT)
    runner.run_feature(CURRENT_DIR.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
