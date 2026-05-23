"""定义公共异常类型。"""


class ConfigurationError(Exception):
    """配置内容缺失或格式错误时抛出。"""


class DependencyError(Exception):
    """数据库依赖未安装时抛出。"""
