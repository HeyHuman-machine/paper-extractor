# M5：SQLite 持久化讲解稿

## 先记住一句话

M5 把 M4 只存在内存里的 `BatchResult` 保存到本地 `app.db`。程序关闭后再次启动，
仍然可以通过 `task_id` 找回批次、成功论文和失败诊断。

```text
BatchResult
  ↓ 一个事务
tasks      一行：本批次总览
results    多行：成功论文
failures   多行：失败论文
```

## 数据库、表、行、列

- 数据库：整个 `app.db` 文件。
- 表：同一种数据的集合，例如 `tasks`。
- 行：一条具体记录，例如“第 12 次批处理”。
- 列：记录的固定属性，例如 `status`、`total_files`。

SQLite 是嵌入式数据库，不需要单独启动服务器。Python 标准库自带 `sqlite3`，数据库
就是一个文件，适合当前单机、单用户项目。

## 三张表怎么关联

```text
tasks
id = 12
  │
  ├── results.task_id = 12
  ├── results.task_id = 12
  └── failures.task_id = 12
```

- `tasks.id`：主键，每个批次唯一。
- `results.task_id`：外键，说明成功论文属于哪个批次。
- `failures.task_id`：外键，说明失败论文属于哪个批次。

一次批次对应多篇论文，这是“一对多”关系。

## 保存流程

`save_batch(batch)` 执行：

1. 初始化三张表和两个查询索引。
2. 插入一行 `tasks`，获得自动生成的 `task_id`。
3. 遍历 `batch.files`。
4. 成功项写入 `results`，失败项写入 `failures`。
5. 全部成功后 `commit`，返回 `task_id`。
6. 任意一步异常就 `rollback`。

## 什么是事务

事务保证一组数据库操作是一个整体：

```text
全部插入成功 → COMMIT → 数据永久生效
中途任一步失败 → ROLLBACK → 撤销本次全部插入
```

如果没有事务，可能出现 `tasks` 显示共有 10 篇，但 `results` 只写入 4 篇程序就崩溃，
数据库会留下“半套数据”。事务避免这种不一致。

## 为什么列表保存成 JSON 字符串

SQLite 的一格适合存一个标量：文字、整数、浮点数或二进制；Python 的
`list[str]` 不能直接放进一格。

所以保存时：

```python
["张三", "Alice"]
        ↓ json.dumps
'["张三", "Alice"]'
```

查询时用 `json.loads()` 恢复成列表。JSON 能保留顺序、空列表和中文，比使用逗号拼接
可靠，因为作者名或结果文本本身也可能包含逗号。

## 为什么不用 ORM

ORM 可以把数据库行映射成 Python 对象，但当前只有三张结构清晰的表：

- 手写 SQL 更容易直接学习 `CREATE TABLE`、`INSERT`、`SELECT`。
- 不增加 SQLAlchemy 等依赖和抽象层。
- 发生问题时能明确知道执行了哪条 SQL。
- 当前查询简单，ORM 带来的便利不足以抵消复杂度。

如果未来表和关联大量增加、需要复杂迁移，才重新评估 ORM。

## 外键与索引

连接数据库时显式执行：

```sql
PRAGMA foreign_keys = ON;
```

这样不能插入指向不存在 `task_id` 的孤儿数据。`results.task_id` 和
`failures.task_id` 上建立索引，未来按任务查询明细时不用逐行扫描整张表。

## 为什么时间保存为 TEXT

SQLite 没有独立的日期时间存储类型。项目使用 UTC ISO 8601 字符串，例如：

```text
2026-08-12T07:47:23.123+00:00
```

它可读、可排序，也可以在界面层转换成中国时区显示。

## 关键函数

| 函数 | 作用 |
|---|---|
| `connect()` | 连接数据库、启用外键和按列名读取 |
| `init_db()` | 幂等创建表与索引，不删除旧数据 |
| `save_batch()` | 用一个事务保存完整批次，返回 `task_id` |
| `get_task()` | 查询批次总览 |
| `get_results()` | 查询成功结果并恢复 JSON 列表 |
| `get_failures()` | 查询失败诊断 |

## 如何运行

不调用 DeepSeek 的临时数据库演示：

```powershell
.\.venv\Scripts\python.exe scripts\demo_m5_database.py
```

也可以在 VS Code“运行和调试”中选择 `M5：SQLite 保存与查询演示`。

脚本保存 2 条成功和 1 条失败记录，然后重新连接数据库查询，证明数据已经落盘。

## M5 验收清单

- [x] 创建 `tasks`、`results`、`failures` 三张表
- [x] 主键和外键关联正确
- [x] M4 成功与失败结果分表保存
- [x] 列表字段按 JSON 字符串存储并恢复
- [x] 整批使用事务，插入异常时全部回滚
- [x] 支持重复初始化，不清空旧数据
- [x] 提供任务、成功结果和失败诊断查询

## 面试官可能会问

### SQLite 和 MySQL 有什么区别？

SQLite 是嵌入式单文件数据库，不需要服务器，部署简单；MySQL 是独立数据库服务，
更适合多用户、高并发和复杂权限。当前项目是单机单用户，SQLite 已经足够。

### 为什么必须启用外键？

SQLite 默认可能不强制外键。显式开启后，可以阻止 `results` 或 `failures` 指向一个
不存在的任务，保证批次和明细之间的关系真实存在。

### 如何证明事务真的回滚？

测试在成功结果已经插入后，故意让失败结果插入抛异常；随后查询三张表，断言行数
全部为 0，而不是留下 task 或部分 result。

