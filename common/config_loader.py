"""提供通用配置文件解析能力。"""

from pathlib import Path
from typing import Dict, Optional

from common.exceptions import ConfigurationError


class LooseIniConfig:
    """解析同时包含根节点键值和分节内容的 ini 风格文件。"""

    def __init__(self, path: Path):
        """加载并解析目标 ini 文件。"""
        self.path = path
        self.root: Dict[str, str] = {}
        self.sections: Dict[str, Dict[str, str]] = {}
        self._parse()

    def _parse(self) -> None:
        """读取 ini 文件，并将键值拆分到根节点和分节中。"""
        if not self.path.exists():
            raise ConfigurationError("配置文件不存在: {}".format(self.path))

        current_section: Optional[str] = None
        for line_no, raw_line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                self.sections.setdefault(current_section, {})
                continue
            if "=" not in line:
                raise ConfigurationError("{} 第 {} 行格式错误: {}".format(self.path, line_no, raw_line))
            key, value = [item.strip() for item in line.split("=", 1)]
            if current_section is None:
                self.root[key] = value
            else:
                self.sections.setdefault(current_section, {})[key] = value

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """返回根节点中的配置值。"""
        return self.root.get(key, default)

    def require(self, key: str) -> str:
        """返回必填根节点配置，缺失时抛出明确异常。"""
        value = self.get(key)
        if value in (None, ""):
            raise ConfigurationError("{} 缺少根节点配置: {}".format(self.path, key))
        return value

    def get_section(self, section: str) -> Dict[str, str]:
        """返回指定分节，不存在时抛出异常。"""
        if section not in self.sections:
            raise ConfigurationError("{} 缺少节点: [{}]".format(self.path, section))
        return self.sections[section]
