# M2：LLM 客户端与 Prompt 讲解稿

## 这个模块解决什么问题

M1 只能从 PDF 或 DOCX 中读出文字，M2 负责把文字发送给 DeepSeek，并要求模型
按照全项目统一的 11 字段格式返回 JSON。

- 输入：OpenAI 兼容消息列表、最大输出 token、temperature。
- 处理：读取本地配置，构造 HTTP 请求，调用 DeepSeek，处理网络错误与重试。
- 输出：`LLMResponse`，包含模型正文、token 用量、耗时和重试次数。

M2 只负责可靠通信和 Prompt。JSON 解析、Pydantic 错误反馈与三级容错属于 M3，
不会提前混入本模块。

## 数据流

```text
.env 配置 ───────────────┐
                         ↓
论文文本 → Prompt 消息 → app/llm.py → DeepSeek API
                                      ↓
                         JSON 正文 + token + 耗时
                                      ↓
                         M3 解析并校验 PaperRecord
```

## 主要文件

### `app/config.py`

使用 `python-dotenv` 读取项目根目录的 `.env`，并把环境变量的字符串转换为程序
真正需要的类型，例如：

- `"60"` 转为浮点数 `60.0`。
- `"2"` 转为整数 `2`。
- `"false"` 转为布尔值 `False`。

`Settings` 是不可变的 `dataclass`。它集中校验必填项、URL、正数和布尔值，避免
每个业务文件自行读取字符串。模块导入时不会自动读取密钥，只有真正调用
`get_settings()` 时才加载 `.env`，因此测试可以注入假配置且不消耗余额。

### `app/llm.py`

使用 `httpx` 直接向下面的接口发送 POST 请求：

```text
https://api.deepseek.com/v1/chat/completions
```

没有使用 DeepSeek 或 OpenAI SDK。这样能在面试中清楚解释 HTTP 请求的四部分：

- URL：请求发送到哪里。
- Headers：`Authorization: Bearer ...` 携带身份凭证。
- JSON Body：模型、消息、输出长度和模式开关。
- Response：状态码、模型正文和 token 用量。

成功响应被转换成 `LLMResponse`，调用方不需要反复访问嵌套字典。

### `app/prompts.py`

Prompt 包含三个关键部分：

1. `PaperRecord.model_json_schema()` 生成的真实 JSON Schema。
2. 明确的缺失值、长度、枚举和“禁止猜测”规则。
3. 一组虚构 TinySort 论文的输入与正确 JSON，作为 few-shot 示例。

Schema 由 Pydantic 模型自动生成，不手工复制字段，所以以后修改模型时 Prompt
不会悄悄变成旧版本。

### `scripts/check_llm.py`

这是 M2 的独立验收入口。它只发送代码内的虚构短文本，不读取私人论文，并打印：

- 服务端模型名；
- 输入、输出和总 token；
- 整体耗时；
- 重试次数；
- 通过 `PaperRecord` 校验的 11 字段结果。

## 为什么关闭 thinking

DeepSeek V4 的 thinking 默认开启。它适合复杂推理，但当前任务主要是依据已有文本
填入固定 Schema。开启后会额外生成推理 token，增加耗时和费用，所以请求体明确
发送：

```json
{
  "thinking": {"type": "disabled"}
}
```

是否关闭不能只写在注释或 Prompt 中，必须成为真实 HTTP 参数；自动测试会检查
请求体中的实际值。

## JSON Output 为什么不能替代 Pydantic

请求体启用：

```json
{
  "response_format": {"type": "json_object"}
}
```

它大幅降低模型在 JSON 外添加解释或 Markdown 代码块的概率，并保证正文是合法
JSON。但是“合法 JSON”仍可能包含空标题、错误年份、缺失字段或错误枚举。

因此两者分工如下：

```text
JSON Output：保证包装格式能被 JSON 解析器读取
Pydantic：保证 11 个字段、类型、枚举和长度符合业务规则
```

DeepSeek 官方还说明 Prompt 中必须出现 JSON 要求和示例，并要合理设置
`max_tokens`，否则可能出现空正文或内容被截断。本项目同时满足这些要求，但仍把
空正文识别为专门的 `LLMResponseError`。

参考资料：

- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode)
- [DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)

## 重试策略

客户端只重试可能短暂恢复的问题：

| 情况 | 是否重试 | 原因 |
|---|:---:|---|
| 网络错误或超时 | 是 | 网络可能短暂抖动 |
| HTTP 429 | 是 | 请求过快，等待后可能恢复 |
| HTTP 5xx | 是 | 服务端可能暂时故障 |
| HTTP 401 / 403 | 否 | Key 或权限错误，重复请求无意义 |
| 其他 HTTP 4xx | 否 | 请求参数错误，需要修改代码或配置 |

指数退避的等待时间是 1 秒、2 秒、4 秒……，避免服务故障时立即连续请求。配置
中的 `LLM_MAX_RETRIES=2` 表示首次请求失败后最多再试两次，总请求次数最多三次。

## 关键 Python 语法

### `@dataclass`

`Settings` 使用 `@dataclass(frozen=True, slots=True)` 自动生成初始化方法。
`frozen=True` 防止运行途中误改配置；`slots=True` 明确对象允许哪些属性。

### 依赖注入

`LLMClient` 可以接收外部 `http_client` 和 `sleep_fn`。生产环境使用真实 `httpx`
和真实等待；测试注入 `MockTransport` 与假等待函数。这样能验证请求体和重试逻辑，
既不访问网络，也不消耗 API 余额。

### `for attempt in range(...)`

循环控制首次请求和重试次数。若 `max_retries=2`，`range(3)` 会产生 0、1、2，
对应最多三次请求；返回结果中的 `retry_count` 就是成功前已经失败的次数。

### `try / except ... from`

底层 `httpx` 错误会转换成项目自己的异常类型，同时用 `from exc` 保留原始原因。
界面可以显示友好信息，开发者仍能通过异常链定位根因。

### 上下文管理器

```python
with LLMClient() as client:
    result = client.chat(messages)
```

`with` 会在结束时关闭网络连接池，类似 Java 的 try-with-resources。

## 测试与真实验收

自动化测试共 31 项全部通过，其中 M2 覆盖：

- 配置类型转换与错误提示；
- Prompt 内的 Schema、JSON 要求和 few-shot；
- thinking 确实关闭、JSON Output 确实开启；
- 正常 token 统计；
- 超时、429 和 5xx 重试；
- 401 与普通 4xx 不重试；
- 空正文友好报错。

真实最小调用结果：

| 指标 | 结果 |
|---|---:|
| 模型 | deepseek-v4-flash |
| 输入 token | 1,196 |
| 输出 token | 191 |
| 总 token | 1,387 |
| 耗时 | 1,286 ms |
| 重试次数 | 0 |
| Pydantic 校验 | 通过 |

## 如何运行

```powershell
uv run python scripts/check_llm.py
uv run pytest
```

使用 VS Code 时也可以打开 `scripts/check_llm.py`，点击右上角运行按钮。

## 安全边界

- `.env` 包含真实 Key，已被 Git 忽略。
- `.env.example` 只有模板值，可以提交。
- 错误信息不会打印 Authorization 请求头。
- 自动测试只使用 `test-key-not-real`，不会读取真实 Key。
- 真实验收只发送虚构短文本；上传私人论文前必须明确知道文本会发往第三方 API。

## M2 验收清单

- [x] 使用 httpx 手写 OpenAI 兼容 POST 请求
- [x] 记录输入、输出、总 token 和耗时
- [x] 网络超时、429 和 5xx 使用指数退避重试
- [x] 关闭 DeepSeek thinking
- [x] 启用 JSON Output，同时保留 Pydantic 校验
- [x] Prompt 包含真实 JSON Schema 和 few-shot 示例
- [x] 最小真实 API 调用成功
- [x] 31 项自动化测试全部通过

## 面试官可能会问的问题

### 1. 为什么不用官方 SDK，而用 httpx？

参考答案：项目需要的是标准 OpenAI 兼容 REST 接口。直接使用 httpx 可以看清 URL、
请求头、请求体、状态码和重试策略，也能通过切换 base URL 与 model 接入不同供应商，
减少厂商绑定。代价是需要自己实现错误分类与响应解析，但本项目正好借此展示工程能力。

### 2. 为什么只对 429、5xx 和网络错误重试？

参考答案：这些错误通常是暂时性的，等待后有机会恢复。401 表示密钥或权限错误，
400 通常表示请求参数错误，重复相同请求只会浪费时间，因此应该立即失败并提示修正。

### 3. JSON Output 已保证 JSON，为什么还要 Pydantic？

参考答案：JSON Output 只保证语法合法，不保证业务正确。模型仍可能缺字段、返回
错误类型或越界年份。Pydantic 负责将响应校验为唯一的 `PaperRecord` 契约，M3
还会把具体校验错误反馈给模型进行修正重试。
