# devtools/ — 开发期调试与维护脚本

> 这些脚本是开发 RAGFlow v0.26.4 集成时的**一次性调试/补丁工具**，大部分已废弃，
> 仅保留作历史参考。它们大多通过 `docker exec` 直接操作 RAGFlow 容器，
> **不要在业务代码中引用，也不要随意运行**（会修改容器内源码）。

## 脚本分类

### 容器热补丁（修改 RAGFlow 容器内 Python 源码）
| 脚本 | 作用 |
|------|------|
| `_patch_batch_size.py` | 将 `OpenAI_APIEmbed.encode` 的 batch_size 从 16 改为 10（DashScope text-embedding-v4 限制） |
| `_patch_context.py` | 兼容 `parser_config` / `kb_parser_config` 是 JSON 字符串而非 dict 的情况 |
| `_patch_task_service.py` | 在 `task_service.py` 中解析 DB 返回的 JSON 字符串配置 |

> 这些补丁的**最终整合版**在 `agent/ragflow_init.py` 的 `RAGFLOW_PATCHES` 中，
> 首次部署时会自动检查并打入，无需手动运行本目录脚本。

### 容器内数据库操作
| 脚本 | 作用 |
|------|------|
| `_init_llm_factories.py` | 从 `llm_factories.json` 初始化 `LLMFactories` / `LLM` 表 |
| `_populate_llm_db.py` | 同上（早期版本） |
| `_check_factories.py` | 检查 RAGFlow 的 LLM factory 配置 |
| `_list_factories.py` | 列出 `llm_factories.json` 中的 factory 与模型 |
| `_find_factories.py` | 在源码中搜索 OpenAI 兼容 factory 名称 |

### 调试验证
| 脚本 | 作用 |
|------|------|
| `_check_parse.py` | 检查知识库文档的解析进度（run 状态统计） |
| `_trigger_parse.py` | 触发 RAGFlow 文档解析 |
| `_test_upload_internal.py` | 容器内测试文档上传流程 |
| `_verify_fix.py` | 验证 Tenant 修复后 `get_chunking_config` 是否正常 |
| `_encrypt_pw.py` | 调用容器内 `api.utils.crypt.crypt` 加密密码（RAGFlow RSA 加密） |
| `_check_keys.py` | 检查本地 `.env` API Key 解析是否正确 |
