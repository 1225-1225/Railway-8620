# Railway-8620

基于 LangChain + LangGraph 的中文铁路问答与路线可视化示例，包含：
- RAG：向量检索问答（`data/cleaned_txts` -> `data/vector_database`）。
- Agent：支持工具调用（检索、画铁路线路图）。
- 前后端：FastAPI 提供流式聊天接口，Vite 前端展示对话与地图。

## 目录结构（简版）
```
railway-8620/
├── backend/              # FastAPI 服务入口 api.py
├── agent/                # LLM、RAG、绘图、工具封装
├── frontend/             # Vite 前端（地图静态文件输出到 public/maps）
├── data/                 # 数据与模型输出（包含铁路图 pkl、stations.json 等）
├── mytools/              # 数据清洗/构建脚本
├── requirements.txt      # 后端/脚本依赖
└── config_data.py        # 路径与模型配置（注意为绝对路径）
```

## 准备环境
- Python 3.10+（建议与 `requirements.txt` 保持一致）
- Node 18+/npm 用于前端
- 将 `config_data.py` 中的绝对路径修改为你的本地路径

安装 Python 依赖：
```bash
pip install -r requirements.txt
```
前端依赖：
```bash
cd frontend
npm install
```

## 运行后端
在 `backend` 目录下启动 FastAPI（默认监听 `127.0.0.1:8000`）：
```bash
uvicorn api:app --reload
```
主要接口：
- `POST /chat/stream`：流式对话，支持工具调用。返回内容中 `[MAP]/maps/xxx.html[/MAP]` 可在前端解析跳转。

## 运行前端
```bash
cd frontend
npm run dev
```
在浏览器打开控制台输出的本地地址。静态地图文件会写入 `frontend/public/maps`，前端可直接通过 `/maps/文件名.html` 访问。

## 关键数据与文件
- `data/china_railway.pkl`：全国铁路 NetworkX 图（使用 OSM/Geo 数据生成）。
- `data/city_to_node.pkl`：站点到铁路图节点的映射。
- `data/train_data.json`：列车与经停站数据。
- `data/stations.json`：城市到车站映射，用于模糊兜底。
- `frontend/public/maps/`：生成的交互式地图 HTML。

## 工具与核心逻辑
- `agent/railway_drawing.py`：按真实铁路网络（非直线）绘制路径，支持城市兜底匹配站点。
- `agent/tools.py`：定义 `railway_drawing_tool`、`retriever_tool`，带调用日志。
- `agent/vector_store.py` & `agent/build_vector_store.py`：向量库检索与构建。
- `backend/api.py`：对话流式接口，代理 LLM/工具调用。

## 常见配置/调整
- 更换 LLM：修改 `config_data.py` 中 `chat_model_name`，确保凭据已配置环境变量。
- 数据路径：所有路径为绝对路径，迁移机器后需同步更新。
- 地图输出位置：`config_data.maps_output_dir`，默认 `frontend/public/maps`。

## 简单自测
命令行测试绘图（会在输出目录生成 HTML）：
```bash
python agent/railway_drawing.py
# 输入：北京 上海
```

## 许可证
此仓库未附带开源许可证，使用前请先确认版权与数据合规性。

