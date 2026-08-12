# M7：FastAPI 接口

## 这一阶段解决什么

M1～M6 已经能在 Python 内部完成“上传前的文件路径 → 抽取 → 保存 → 导出”，M7 把这些能力包装成 HTTP 接口。浏览器、Streamlit 或其他程序不必直接导入 Python 函数，只要发送请求即可。

```text
浏览器 / Swagger / Streamlit
       ↓ HTTP 请求
app/api.py
       ├─ POST 上传 → run_batch() → save_batch() → task_id
       ├─ GET 查询  → db.py
       └─ GET 导出  → exporter.py → Excel / JSON
```

## 接口

| 方法与路径 | 作用 |
|---|---|
| `GET /health` | 检查服务是否启动，不调用 LLM |
| `POST /api/tasks` | 一次上传多个 PDF / DOCX，运行 M1～M5 |
| `GET /api/tasks` | 分页查看历史任务 |
| `GET /api/tasks/{task_id}` | 查看任务总览与成功论文结果 |
| `GET /api/tasks/{task_id}/failures` | 查看失败文件与失败阶段 |
| `GET /api/tasks/{task_id}/export?format=xlsx` | 复用 M6 下载 Excel |
| `GET /api/tasks/{task_id}/export?format=json` | 复用 M6 下载 JSON |

## 为什么 `/docs` 能自动生成

FastAPI 会读取路径、参数类型、Pydantic 响应模型和字段描述，生成 OpenAPI 规格，再渲染为 Swagger 页面。代码既是实现，也是接口说明。`PaperResultResponse` 继承 M3 的 `PaperRecord`，因此 11 个业务字段只维护一份定义。

## 上传后发生什么

1. API 去掉上传文件名中的目录，防止路径穿越。
2. 文件只暂存在系统临时目录；同一请求中的同名文件会自动编号。
3. `run_batch()` 执行 M1～M4，成功与失败都放进 `BatchResult`。
4. `save_batch()` 执行 M5，返回唯一 `task_id`。
5. 临时文件自动清理；结果已经在 SQLite，可以继续查询或导出。

## 错误为什么统一成 JSON

所有参数错误、文件类型错误、任务不存在和服务器内部错误都使用：

```json
{
  "error": {
    "type": "TaskNotFoundError",
    "message": "任务不存在：999",
    "details": null
  }
}
```

前端不需要针对不同错误猜测文本格式；服务器内部异常也不会把堆栈或密钥暴露给调用方。

## 运行

在 VS Code“运行和调试”中选择 `M7：启动 FastAPI（打开 /docs）`，启动后访问：

- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

命令行等价写法：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api:app --reload
```

## 模块边界

- M7 负责 HTTP 输入输出、上传文件、状态码和响应格式。
- M7 不负责判断抽取准确性；字段校验仍由 M3 负责，人工准确率在 M9 评测。
- 导出接口不调用 LLM，只读取已经保存的任务。

## 验收

- 接口测试不连接 DeepSeek，使用本地假批次验证完整交接，避免测试产生费用。
- `/docs`、OpenAPI、上传、分页、详情、失败记录、Excel / JSON 下载和统一错误结构均有测试。
- 还需要用真实 Uvicorn 进程验证 `/health` 与 `/docs` 可访问。
