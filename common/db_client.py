"""提供通用数据库连接与查询能力。"""

import re
from typing import Dict, List, Optional, Tuple

from common.config_loader import LooseIniConfig
from common.exceptions import ConfigurationError, DependencyError


class DatabaseClient:
    """提供 Oracle、MySQL、PostgreSQL 的统一查询接口。"""

    def __init__(self, config: LooseIniConfig):
        """根据 database.ini 构建数据库连接参数。"""
        self.config = config
        self.db_type = config.require("db_type").strip().lower()
        self.host = config.require("host")
        self.port = config.require("port")
        self.database = config.require("database")
        self.username = config.require("username")
        self.password = config.require("password")

    def _connect(self):
        """创建并返回数据库连接。"""
        if self.db_type == "oracle":
            return self._connect_oracle()
        if self.db_type == "mysql":
            return self._connect_mysql()
        if self.db_type in ("postgre", "postgres", "postgresql"):
            return self._connect_postgresql()
        raise ConfigurationError("暂不支持的数据库类型: {}".format(self.db_type))

    def _connect_oracle(self):
        """使用 oracledb 或 cx_Oracle 创建 Oracle 连接。"""
        try:
            import oracledb  # type: ignore

            dsn = oracledb.makedsn(self.host, int(self.port), service_name=self.database)
            return oracledb.connect(user=self.username, password=self.password, dsn=dsn)
        except ImportError:
            try:
                import cx_Oracle  # type: ignore

                dsn = cx_Oracle.makedsn(self.host, int(self.port), service_name=self.database)
                return cx_Oracle.connect(user=self.username, password=self.password, dsn=dsn)
            except ImportError as exc:
                raise DependencyError("Oracle 需要安装 oracledb 或 cx_Oracle") from exc

    def _connect_mysql(self):
        """使用 mysql-connector-python 创建 MySQL 连接。"""
        try:
            import mysql.connector  # type: ignore
        except ImportError as exc:
            raise DependencyError("MySQL 需要安装 mysql-connector-python") from exc
        return mysql.connector.connect(
            host=self.host,
            port=int(self.port),
            database=self.database,
            user=self.username,
            password=self.password,
        )

    def _connect_postgresql(self):
        """使用 psycopg2 创建 PostgreSQL 连接。"""
        try:
            import psycopg2  # type: ignore
        except ImportError as exc:
            raise DependencyError("PostgreSQL 需要安装 psycopg2-binary") from exc
        return psycopg2.connect(
            host=self.host,
            port=int(self.port),
            dbname=self.database,
            user=self.username,
            password=self.password,
        )

    def _normalize_sql(self, sql: str) -> str:
        """在非 Oracle 驱动下，将 Oracle 风格命名参数转换为对应语法。"""
        if self.db_type == "oracle":
            return sql
        return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", sql)

    def fetch_all(self, sql: str, params: Optional[Dict[str, str]] = None) -> List[Tuple]:
        """执行查询并返回全部结果行。"""
        query = self._normalize_sql(sql)
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(query, params or {})
            rows = cursor.fetchall()
            return [tuple(row) for row in rows]
        finally:
            connection.close()

    def fetch_one_value(self, sql: str, params: Optional[Dict[str, str]] = None) -> str:
        """执行查询并返回首行首列的值。"""
        rows = self.fetch_all(sql, params)
        if not rows:
            raise ConfigurationError("SQL 未查询到结果: {}".format(sql))
        return str(rows[0][0]).strip()
