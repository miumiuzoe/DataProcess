"""关联功能自动化测试的核心执行器。"""

import argparse
import configparser
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.command_helper import run_command
from common.config_loader import LooseIniConfig
from common.db_client import DatabaseClient
from common.exceptions import ConfigurationError


@dataclass
class TestExpectation:
    """表示一条测试用例及其全部期望字段值。"""

    case_id: str
    case_name: str
    expected_by_guid: Dict[str, str]


class AssociateTestRunner:
    """端到端执行一个或多个 TestAssociate 关联功能测试。"""

    CASE_NAME_PATTERN = re.compile(r"【([^】]+)】")
    EXPECTED_KEY_PATTERN = re.compile(r"^(?P<field_name>.+?)\((?P<guid>.+?)\)$")

    def __init__(self, project_root: Path):
        """加载项目级配置并准备复用路径。"""
        self.project_root = project_root
        self.test_root = project_root / "TestAssociate"
        self.config_root = project_root / "config"
        self.associate_config = LooseIniConfig(self.test_root / "associate.ini")
        self.database_config = LooseIniConfig(self.config_root / "database.ini")
        self.std_config = LooseIniConfig(self.config_root / "std_conf.ini")
        self.db_client = DatabaseClient(self.database_config)

    def run_features(self, feature_names: Sequence[str]) -> int:
        """执行多个关联功能测试，并返回类似进程退出码的结果。"""
        exit_code = 0
        for feature_name in feature_names:
            try:
                self.run_feature(feature_name)
                print("[PASS] {} 测试完成".format(feature_name))
            except Exception as exc:
                exit_code = 1
                print("[FAIL] {} 测试失败: {}".format(feature_name, exc))
        return exit_code

    def run_feature(self, feature_name: str) -> None:
        """执行单个关联功能目录下的完整测试流程。"""
        feature_dir = self.test_root / feature_name
        if not feature_dir.exists():
            raise ConfigurationError("关联功能目录不存在: {}".format(feature_dir))

        testcase_path = feature_dir / "testcase.ini"
        testdata_dir = feature_dir / "testdata"
        expectations = self.load_test_expectations(testcase_path, testdata_dir)
        guid_to_position = self.query_guid_positions(feature_name, testcase_path, expectations)
        rule_input_dir = Path(self.query_rule_input_dir())
        output_dir = Path(self.query_output_dir())
        self.prepare_runtime_environment(rule_input_dir, testdata_dir)
        self.ensure_lib_configuration("TestAssociate")
        start_timestamp = time.time()
        self.start_process()
        self.wait_for_startup()
        nb_file = self.wait_for_nb_file(output_dir, start_timestamp)
        results = self.verify_nb_file(nb_file, expectations, guid_to_position)
        self.write_test_results(feature_dir / "test_result.txt", results)

    def load_test_expectations(self, testcase_path: Path, testdata_dir: Path) -> List[TestExpectation]:
        """解析 testcase.ini，并将各 section 绑定到 bcp 中提取的 casename。"""
        parser = configparser.ConfigParser()
        parser.optionxform = str
        ini_content = testcase_path.read_text(encoding="utf-8")
        parser.read_string("[DEFAULT]\n" + ini_content, source=str(testcase_path))

        case_names = self.extract_case_names(testdata_dir)
        if not parser.sections():
            raise ConfigurationError("{} 中未找到任何测试用例".format(testcase_path))

        expectations: List[TestExpectation] = []
        for index, section in enumerate(parser.sections()):
            section_items = dict(parser.items(section))
            case_name = section_items.pop("casename", "").strip()
            if not case_name:
                if index >= len(case_names):
                    raise ConfigurationError(
                        "{} 缺少 casename，且 testdata 中没有足够的【用例标题】按顺序匹配".format(section)
                    )
                case_name = case_names[index]
            expected_by_guid: Dict[str, str] = {}
            for key, value in section_items.items():
                match = self.EXPECTED_KEY_PATTERN.match(key.strip())
                if not match:
                    raise ConfigurationError(
                        "{} 中键 {} 格式错误，应为 字段名(guid) = 期望值".format(testcase_path, key)
                    )
                expected_by_guid[match.group("guid").strip()] = value.strip()
            expectations.append(TestExpectation(case_id=section, case_name=case_name, expected_by_guid=expected_by_guid))
        return expectations

    def extract_case_names(self, testdata_dir: Path) -> List[str]:
        """提取 testdata 下所有 bcp 文件中【】包裹的用例标题。"""
        case_names: List[str] = []
        for bcp_file in sorted(testdata_dir.glob("*.bcp")):
            content = bcp_file.read_text(encoding="utf-8")
            case_names.extend([match.strip() for match in self.CASE_NAME_PATTERN.findall(content)])
        return case_names

    def query_guid_positions(
        self,
        feature_name: str,
        testcase_path: Path,
        expectations: Iterable[TestExpectation],
    ) -> Dict[str, int]:
        """通过配置的 SQL 查询链路，解析每个期望 guid 对应的输出序号。"""
        testcase_config = LooseIniConfig(testcase_path)
        oobj_engname = testcase_config.get("oobj_engname", "").strip()
        if not oobj_engname:
            raise ConfigurationError("{} 缺少 oobj_engname".format(testcase_path))

        oobj_guid_sql = self.associate_config.require("oobj_guid")
        dst_field_sql = self.associate_config.require("dst_field")
        dst_field_id_sql = self.associate_config.require("dst_field_id")
        as_rule = self.associate_config.get_section("as_rule").get(feature_name)
        if not as_rule:
            raise ConfigurationError("associate.ini 的 [as_rule] 中缺少 {}".format(feature_name))

        oobj_guid = self.db_client.fetch_one_value(oobj_guid_sql, {"oobj_engname": oobj_engname})
        dst_fields = self.db_client.fetch_all(dst_field_sql, {"as_rule": as_rule, "oobj_guid": oobj_guid})
        if not dst_fields:
            raise ConfigurationError("未查询到关联配置字段")

        expected_guids = set()
        for expectation in expectations:
            expected_guids.update(expectation.expected_by_guid.keys())

        guid_to_position: Dict[str, int] = {}
        for dst_row in dst_fields:
            field_guid = str(dst_row[0]).strip()
            if not field_guid:
                continue
            rows = self.db_client.fetch_all(dst_field_id_sql, {"dst_field": field_guid})
            guid_to_position.update(self.infer_guid_positions(rows, expected_guids))

        missing_guids = expected_guids.difference(guid_to_position.keys())
        if missing_guids:
            raise ConfigurationError("以下 guid 未查询到输出序号: {}".format(",".join(sorted(missing_guids))))
        return guid_to_position

    def infer_guid_positions(self, rows: Sequence[Tuple], expected_guids: Iterable[str]) -> Dict[str, int]:
        """推断查询结果中哪一列是 guid，哪一列是从 1 开始的输出序号。"""
        expected_guid_set = set(expected_guids)
        guid_to_position: Dict[str, int] = {}
        for row in rows:
            if len(row) < 2:
                continue
            first_value = str(row[0]).strip()
            second_value = str(row[1]).strip()
            if first_value in expected_guid_set and second_value.isdigit():
                guid_to_position[first_value] = int(second_value)
            elif second_value in expected_guid_set and first_value.isdigit():
                guid_to_position[second_value] = int(first_value)
        return guid_to_position

    def query_rule_input_dir(self) -> str:
        """查询并返回 bcp 测试文件输入目录。"""
        sql = self.database_config.require("rule_input")
        return self.db_client.fetch_one_value(sql)

    def query_output_dir(self) -> str:
        """查询并返回 nb 文件输出目录。"""
        rule_output_sql = self.database_config.require("rule_output")
        rule_output_dir = self.db_client.fetch_one_value(rule_output_sql)
        odps_dir_template = self.database_config.require("odps_dir")
        return odps_dir_template.replace(":rule_output", rule_output_dir)

    def prepare_runtime_environment(self, rule_input_dir: Path, testdata_dir: Path) -> None:
        """必要时先停止被测程序，再将全部 bcp 文件复制到输入目录。"""
        status_output = run_command(self.std_config.get_section("cmd")["status_cmd"], check=False)
        if "Active: inactive" not in status_output:
            run_command(self.std_config.get_section("cmd")["stop_cmd"], check=False)
            self.wait_for_inactive()

        rule_input_dir.mkdir(parents=True, exist_ok=True)
        for bcp_file in sorted(testdata_dir.glob("*.bcp")):
            shutil.copy2(str(bcp_file), str(rule_input_dir / bcp_file.name))

    def wait_for_inactive(self, timeout_seconds: int = 60, interval_seconds: int = 3) -> None:
        """轮询进程状态命令，直到服务变为未运行。"""
        deadline = time.time() + timeout_seconds
        status_cmd = self.std_config.get_section("cmd")["status_cmd"]
        while time.time() < deadline:
            status_output = run_command(status_cmd, check=False)
            if "Active: inactive" in status_output:
                return
            time.sleep(interval_seconds)
        raise TimeoutError("等待服务停止超时")

    def ensure_lib_configuration(self, module_name: str) -> None:
        """更新 std_dir/lib.ini，确保 libs 值与目标模块一致。"""
        libs_section = self.std_config.get_section("libs")
        expected_libs = libs_section.get(module_name)
        if not expected_libs:
            raise ConfigurationError("std_conf.ini 的 [libs] 中缺少 {}".format(module_name))

        std_dir = Path(self.get_std_option("std_dir"))
        lib_ini_path = std_dir / "lib.ini"
        if not lib_ini_path.exists():
            raise ConfigurationError("未找到程序配置文件: {}".format(lib_ini_path))

        lines = lib_ini_path.read_text(encoding="utf-8").splitlines()
        updated_lines: List[str] = []
        replaced = False
        for line in lines:
            if line.strip().startswith("libs="):
                updated_lines.append("libs={}".format(expected_libs))
                replaced = True
            else:
                updated_lines.append(line)
        if not replaced:
            updated_lines.append("libs={}".format(expected_libs))
        lib_ini_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    def start_process(self) -> None:
        """使用配置中的启动命令启动被测程序。"""
        run_command(self.std_config.get_section("cmd")["start_cmd"], check=False)

    def wait_for_startup(self, timeout_seconds: int = 300, interval_seconds: int = 5) -> None:
        """等待 std_log 目录下任意 .mylog 文件出现启动完成标识。"""
        std_log_dir = Path(self.get_std_option("std_log"))
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            for log_file in sorted(std_log_dir.glob("*.mylog")):
                try:
                    content = log_file.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if "系统完成启动" in content:
                    return
            time.sleep(interval_seconds)
        raise TimeoutError("等待系统完成启动超时")

    def wait_for_nb_file(
        self,
        output_dir: Path,
        start_timestamp: float,
        timeout_seconds: int = 300,
        interval_seconds: int = 5,
    ) -> Path:
        """等待输出目录中生成新的 .nb 文件。"""
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            candidates = [
                path
                for path in output_dir.glob("*.nb")
                if path.is_file() and path.stat().st_mtime >= start_timestamp
            ]
            if candidates:
                return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0]
            time.sleep(interval_seconds)
        raise TimeoutError("5 分钟内未检测到 .nb 输出文件")

    def verify_nb_file(
        self,
        nb_file: Path,
        expectations: Sequence[TestExpectation],
        guid_to_position: Dict[str, int],
    ) -> List[Tuple[str, str]]:
        """将 nb 文件实际值与期望值比较，并返回每条用例的校验结果。"""
        records = self.load_nb_records(nb_file)
        record_by_case_name = {record[0]: record for record in records if record}
        results: List[Tuple[str, str]] = []

        for expectation in expectations:
            record = record_by_case_name.get(expectation.case_name)
            if not record:
                results.append((expectation.case_name, "不通过"))
                continue

            passed = True
            for guid, expected_value in expectation.expected_by_guid.items():
                position = guid_to_position[guid]
                if position > len(record):
                    passed = False
                    break
                actual_value = record[position - 1].strip()
                if actual_value != expected_value:
                    passed = False
                    break
            results.append((expectation.case_name, "通过" if passed else "不通过"))
        return results

    def load_nb_records(self, nb_file: Path) -> List[List[str]]:
        """读取以 tab 分隔的 nb 文件，并转换为记录列表。"""
        records: List[List[str]] = []
        for raw_line in nb_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if raw_line.strip():
                records.append(raw_line.rstrip("\n").split("\t"))
        return records

    def write_test_results(self, output_path: Path, results: Sequence[Tuple[str, str]]) -> None:
        """将最终测试结果写入 test_result.txt。"""
        lines = ["{},{}".format(case_name, result) for case_name, result in results]
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def get_std_option(self, key: str) -> str:
        """从根节点或 libs 分节中读取 std_conf 配置值。"""
        value = self.std_config.get(key)
        if value:
            return value
        libs_section = self.std_config.get_section("libs")
        value = libs_section.get(key)
        if value:
            return value
        raise ConfigurationError("std_conf.ini 缺少配置: {}".format(key))


def discover_features(test_root: Path) -> List[str]:
    """返回 TestAssociate 下的全部关联功能目录。"""
    features: List[str] = []
    for child in sorted(test_root.iterdir()):
        if child.is_dir() and child.name != "__pycache__":
            features.append(child.name)
    return features


def build_argument_parser() -> argparse.ArgumentParser:
    """创建总入口脚本使用的命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="Run TestAssociate automated tests.")
    parser.add_argument(
        "--features",
        nargs="+",
        help="One or more feature directory names under TestAssociate. If omitted, run all features.",
    )
    return parser


def main() -> int:
    """解析命令行参数并启动指定测试。"""
    parser = build_argument_parser()
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    runner = AssociateTestRunner(project_root)
    features = args.features or discover_features(project_root / "TestAssociate")
    return runner.run_features(features)


if __name__ == "__main__":
    raise SystemExit(main())
