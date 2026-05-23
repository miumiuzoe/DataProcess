"""提供通用命令执行能力。"""

import subprocess


def run_command(command: str, check: bool = True) -> str:
    """执行 shell 命令，并返回合并后的标准输出和错误输出。"""
    completed = subprocess.run(
        command,
        shell=True,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
    )
    if check and completed.returncode != 0:
        raise RuntimeError("命令执行失败: {}\n{}".format(command, completed.stdout))
    return completed.stdout or ""
