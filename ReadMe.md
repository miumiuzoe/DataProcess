## 1. 项目目标

本项目用于实现关联模块的自动化测试。当前优先实现 `TestAssociate` 模块，支持在 CentOS 7 环境中与被测程序部署在同一台机器，通过复制测试数据、启动被测程序、等待输出 `.nb` 文件并校验结果的方式完成测试。

当前代码使用 `Python 3.8.8` 编写。

## 2. 目录结构

```text
DataProcess
├── common
│   ├── __init__.py           # 公共模块包
│   ├── command_helper.py     # 公共命令执行方法
│   ├── config_loader.py      # 公共配置解析方法
│   ├── db_client.py          # 公共数据库连接与查询方法
│   └── exceptions.py         # 公共异常定义
├── config
│   ├── database.ini          # 数据库连接与输入/输出目录查询配置
│   └── std_conf.ini          # 被测程序命令、lib 配置与日志目录配置
├── ReadMe.md
├── TestAssociate
│   ├── associate.ini         # 关联模块通用 SQL 与 as_rule 配置
│   ├── run_tests.py          # TestAssociate 总入口，可执行一个或多个关联功能
│   ├── runner.py             # TestAssociate 模块测试编排逻辑
│   └── ShenFenZhengInfo
│       ├── run_test.py       # 单个关联功能入口
│       ├── testcase.ini      # 测试用例定义
│       ├── test_result.txt   # 测试结果输出文件，程序运行后自动生成
│       └── testdata
│           └── xxx.bcp       # 测试数据文件
└── TestEntityFileOutput
```

说明：

- `common` 用于存放可跨测试模块复用的公共能力。
- 除以 `Test` 开头的测试模块目录外，其他模块目录统一使用小写命名。
- `TestAssociate` 下每个子目录代表一个具体关联功能。
- `testdata` 中可放置一个或多个 `.bcp` 文件。
- `.bcp` 文件只作为测试输入文件，不参与用例匹配。

## 3. 模块分层说明

当前代码按“公共模块”和“测试模块”两层组织：

### 3.1 common 公共模块

- `config_loader.py`：负责解析当前项目中“根节点 + section”混合格式的配置文件。
- `db_client.py`：负责统一封装 Oracle、MySQL、PostgreSQL 的连接和查询逻辑。
- `command_helper.py`：负责统一执行 shell 命令。
- `exceptions.py`：负责定义公共异常类型。

这些内容与具体测试模块无关，后续 `TestEntityFileOutput` 等其他测试模块也可以直接复用。

### 3.2 TestAssociate 测试模块

- `runner.py`：负责 `TestAssociate` 的测试编排，包括读取测试用例、查询字段序号、准备运行环境、等待日志和输出文件、校验结果。
- `run_tests.py`：负责执行一个或多个关联功能测试。
- 各功能目录下的 `run_test.py`：负责执行单个关联功能测试。

这样拆分后，测试模块只关注“测什么、怎么编排”，公共模块只关注“通用能力怎么实现”。

## 4. 已实现能力

当前已实现以下功能：

1. 支持执行单个或多个 `TestAssociate` 关联功能测试。
2. 支持在每个关联功能目录下单独执行当前功能测试。
3. 支持数据库类型：
   - Oracle
   - MySQL
   - PostgreSQL
4. 支持通过 SQL 查询关联输出字段的 `guid` 与输出序号。
5. 支持检查被测程序运行状态，并在必要时停止程序后复制 `.bcp` 测试文件。
6. 支持检查并修正 `lib.ini` 中的 `libs=` 配置。
7. 支持启动被测程序并轮询 `.mylog` 日志中的“系统完成启动”标识。
8. 支持等待输出目录中生成新的 `.nb` 文件。
9. 支持按 `.nb` 文本文件中的真实 `tab` 分隔字段进行校验，并保留空列。
10. 支持将每条用例结果输出到 `test_result.txt`。

## 5. 配置文件说明

### 5.1 config/database.ini

根节点配置示例：

```ini
db_type = oracle
host = 127.0.0.1
port = 1521
database = orcl
username = test
password = test

rule_input = select val from basecf where id = 234
rule_output = select val from basecf where id = 237

odps_dir = :rule_output/shuchu
```

字段说明：

- `db_type`：支持 `oracle`、`mysql`、`postgre`、`postgres`、`postgresql`
- `rule_input`：查询测试数据输入目录的 SQL
- `rule_output`：查询输出目录根路径的 SQL
- `odps_dir`：输出目录模板，支持使用 `:rule_output` 占位

### 5.2 config/std_conf.ini

示例：

```ini
[cmd]
status_cmd = systemctl status Process
start_cmd = systemctl start Process
stop_cmd = systemctl stop Process

[libs]
TestAssociate = Associate,Output
TestEntityFileOutput = app,Output

std_dir = /home/Process
std_log = /home/Process/log
```

字段说明：

- `[cmd]`：
  - `status_cmd`：检查被测程序状态
  - `start_cmd`：启动被测程序
  - `stop_cmd`：停止被测程序
- `[libs]`：
  - `TestAssociate`：运行关联模块时 `lib.ini` 中 `libs=` 应设置的值
- `std_dir`：被测程序目录，程序会检查并修改其中的 `lib.ini`
- `std_log`：被测程序日志目录，程序会扫描该目录下的 `.mylog` 文件

### 5.3 TestAssociate/associate.ini

示例：

```ini
oobj_guid = select oobj_guid from oobtable where obj_id = (SELECT OBJ_ID FROM OBJ WHERE OBJ_ENGNAME = :oobj_engname)

dst_field = select dst from as_table where as_rule = :as_rule and oobj_id = :oobj_guid

dst_field_id = select oof_id,oof_guid from pltfield where guid = :dst_field

[as_rule]
ShenFenZhengInfo = _身份证信息回填
```

字段说明：

- `oobj_guid`：根据 `testcase.ini` 中的 `oobj_engname` 查询 `oobj_guid`
- `dst_field`：根据 `as_rule` 与 `oobj_guid` 查询关联配置中的目标字段集合
- `dst_field_id`：根据上一步结果查询输出字段标识与输出序号
- `[as_rule]`：将目录名映射为数据库中的关联规则名称

注意：

- `dst_field` 查询结果按 XML 解析，程序会递归提取任意层级 `RULE` 标签中的非空 `guid`。
- 如果 `dst_field` 返回值不是 XML 或 XML 片段格式，程序会直接报错。
- 代码已兼容 `dst_field_id` 的返回顺序差异。
- 只要两列中一列可识别为 `guid`，另一列可识别为数字序号，就能自动推断映射关系。

## 6. testcase.ini 与 .bcp 约定

### 6.1 testcase.ini

示例：

```ini
oobj_engname = TEST_132

[result_01]
CSD(6GD672HSDW) = 796785
CSRQ(HU2384395) = 3495945
XB(FHIJSHDF) = 男
```

规则如下：

- 根节点 `oobj_engname` 为数据库查询入参。
- 每个 section 代表一条测试用例。
- section 中每一项格式必须为：

```ini
字段名(guid) = 期望值
```

- 程序实际校验时只使用括号中的 `guid` 和等号右侧的期望值。
- `casename` 为必填项，用于匹配 `.nb` 记录中的 `【用例名称】`。
- 如果缺少 `casename`，程序会直接报错。

### 6.2 .bcp 文件

规则如下：

- `.bcp` 文件仅作为测试输入数据。
- 程序会将当前功能目录下 `testdata` 中所有 `.bcp` 文件复制到输入目录。

示例：

```text
8628492 923euwq weew            【第一个测试】
```

上例表示一条测试输入数据。

## 7. .nb 文件校验规则

`.nb` 文件约定如下：

1. 文本格式文件。
2. 每条记录使用换行分隔。
3. 每条记录中的字段使用真实 `tab` 分隔。
4. 连续空列会保留，字段序号从 `1` 开始计数。
5. 程序会从每条记录中提取 `【】` 包裹的内容，并将其作为 `casename` 匹配测试用例。

校验流程：

1. 从 `testcase.ini` 中得到期望用例与 `casename`。
2. 通过数据库查询得到每个 `guid` 对应的输出序号。
3. 读取 `.nb` 文件，从记录中提取 `【casename】` 后匹配目标记录。
4. 使用“输出序号 - 1”作为列表下标取值并和期望值比较。
5. 全部字段匹配则该用例为“通过”，否则为“不通过”。

## 8. 自动化测试执行流程

程序执行顺序如下：

1. 读取 `testcase.ini`，解析 `oobj_engname`、测试用例和期望值。
2. 读取每条测试用例中的 `casename`，作为与 `.nb` 结果匹配的用例名称。
3. 执行 `associate.ini` 中的 SQL，查询：
   - `oobj_guid`
   - 关联配置字段列表
   - 输出字段 `guid` 与字段序号
4. 执行 `status_cmd` 检查被测程序状态。
5. 如果状态输出中不包含 `Active: inactive`，则执行 `stop_cmd`，并轮询直到程序停止。
6. 将 `testdata` 下所有 `.bcp` 文件复制到 `rule_input` 查询出的目录。
7. 检查 `std_dir/lib.ini` 中的 `libs=` 是否和 `[libs]` 中 `TestAssociate` 的值一致，不一致则自动修改。
8. 执行 `start_cmd` 启动被测程序。
9. 轮询 `std_log` 目录下所有 `.mylog` 文件，直到文件内容中出现“系统完成启动”。
10. 轮询输出目录，等待生成新的 `.nb` 文件，最长等待 5 分钟。
11. 校验 `.nb` 文件内容。
12. 输出 `test_result.txt`，格式为：

```text
casename,测试结果
```

示例：

```text
第一个测试,通过
第二个测试,不通过
```

## 9. 运行方式

### 9.1 执行全部关联功能

在项目根目录执行：

```bash
python3.8 TestAssociate/run_tests.py
```

### 9.2 执行一个或多个指定关联功能

```bash
python3.8 TestAssociate/run_tests.py --features ShenFenZhengInfo
```

```bash
python3.8 TestAssociate/run_tests.py --features ShenFenZhengInfo AnotherFeature
```

### 9.3 在单个关联功能目录下执行

```bash
python3.8 TestAssociate/ShenFenZhengInfo/run_test.py
```

## 10. Python 依赖

按数据库类型安装对应驱动：

### 10.1 Oracle

优先支持以下任一驱动：

```bash
pip install oracledb
```

或：

```bash
pip install cx_Oracle
```

### 10.2 MySQL

```bash
pip install mysql-connector-python
```

### 10.3 PostgreSQL

```bash
pip install psycopg2-binary
```

## 11. 当前实现假设

为便于落地，当前代码使用了以下约定：

1. `.nb` 文件中必须存在 `【casename】` 形式的内容，程序据此匹配测试用例。
2. `.mylog` 文件名不做固定格式限制，只要位于 `std_log` 目录下且扩展名为 `.mylog` 即会被扫描。
3. 等待 `.nb` 文件时，只认启动之后新生成或被修改的 `.nb` 文件。
4. `testcase.ini` 中每个测试用例都必须显式配置 `casename`。

如果后续现场环境规则与上述约定不同，需要同步修改代码与本文档。
