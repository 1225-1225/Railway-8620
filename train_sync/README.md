# train_sync/ —— 中国铁路车次数据同步器（独立子项目）

> ⚠️ **独立于 Railway-8620 主项目**：本目录是许可隔离的独立模块。
> - 主项目（CC BY-NC 4.0）通过**数据文件**消费本模块的输出（`data/train_details.json` 等）
> - 本模块运行时与主项目**无代码链接**，仅通过 JSON 文件交互
> - 本模块代码为**原创实现**，仅参考了公开的 12306 HTTP 接口
>   （接口行为与 GPL-3.0 项目 RailRhythm 的描述一致，但未复制其代码）

## 功能

1. 从 12306 公开接口拉取当日全部车次时刻表（多线程）
2. 转换为 Railway-8620 主项目使用的 JSON 格式
3. 支持一键更新 + 失败保留旧数据

## 使用

```bash
# 一键更新（爬取 → 转换 → 输出到 ../data/）
python run_daily.py

# 只爬取不转换（原始格式输出到 ./raw/）
python scraper.py

# 只转换（用 ./raw/ 里已有的原始数据）
python transform.py
```

## 每日自动更新

### Windows（任务计划程序）
```powershell
# 打开任务计划程序 → 创建基本任务 → 每天凌晨 3:00 运行：
# 程序: python
# 参数: run_daily.py
# 起始于: D:\PyCharm\Railway-8620\train_sync
```

### Linux / macOS（cron）
```bash
# crontab -e
0 3 * * * cd /path/to/train_sync && python run_daily.py >> sync.log 2>&1
```

### GitHub Actions（云端每日更新）
见 `.github/workflows/train-sync.yml`（可选启用）。

## 数据流

```
12306 公开接口
   │  scraper.py（多线程爬取，重试 + 反爬降级）
   ▼
raw/train_list{YYYYMMDD}.json   （12306 原始格式）
   │  transform.py（格式转换）
   ▼
../data/train_details.json      （主项目工具读取）
../data/train_stations.json
```

## 失败保护

- 爬取被反爬/失败 → 不覆盖 `../data/` 已有文件（旧数据继续可用）
- 转换成功才写入 → 避免写入半截 JSON
- 每次运行写入 `sync.log`
