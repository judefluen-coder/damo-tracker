# Damo Tracker

大摩闭门会追踪器：每天检索前一天的“大摩/摩根士丹利”相关 B 站视频，获取字幕或转写音频，从内容中提取明确看好的 A 股/港股标的，并生成适合飞书群投递的报告。

这个仓库是从 OpenClaw 里的日常量化任务整理出来的独立版本。它保留了最新口径：

- 截断/试看内容也会分析，但相关标的必须标注“仅基于截断片段，非完整视频”
- 不写死任何分析模型，通过当前运行环境的 OpenClaw gateway 选择模型
- 定时任务不再按视频时长直接跳过转写
- OpenCLI 是优先的数据获取能力，但不是硬依赖
- 报告按“覆盖概览 -> 标的速览 -> 标的详情 -> 截断片段 -> 失败诊断”呈现
- A 股周报可以自动聚合本周 `damo_runs/` 里的追踪信号

## 项目界面

打开 `index.html` 可以看到项目介绍页。仓库开启 GitHub Pages 后，也可以直接作为介绍页展示。

## 运行依赖

基础工具：

- Python 3.10+
- Node.js 18+（只在生成 A 股周报聚合时需要）
- `openclaw` CLI，并支持 `openclaw infer model run --gateway`
- `yt-dlp`
- `ffmpeg` / `ffprobe`
- `whisper`
- 可选：`opencli`，用于 B 站搜索、字幕和浏览器兜底

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

## 快速运行

默认追踪前一天：

```bash
./damo_run.sh
```

指定日期范围：

```bash
DAMO_START_DATE=2026-06-06 DAMO_END_DATE=2026-06-15 ./damo_run.sh
```

运行完成后会生成：

- `damo_result.json`：结构化结果
- `damo_report_current.md`：群聊可读报告
- `damo_runs/`：按时间归档的结果和报告

## 核心文件

- `damo_tracker.py`：检索、字幕/音频获取、模型提取、去重和防幻觉校验
- `damo_format_result.py`：把结构化结果格式化成群聊报告
- `damo_run.sh`：每日任务入口，默认跑前一天并归档
- `scripts/ensure_opencli_bridge.sh`：OpenCLI Browser Bridge 检查与兜底
- `scripts/a_stock_periodic_report.js`：A 股周报聚合，可读入本周大摩追踪结果
- `cron-prompts/`：OpenClaw cron 可复用提示词
- `examples/`：最近一次 10 天试跑样例

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `DAMO_WORKSPACE` | 工作目录，默认当前项目目录 |
| `DAMO_START_DATE` | 追踪开始日期，格式 `YYYY-MM-DD` |
| `DAMO_END_DATE` | 追踪结束日期，格式 `YYYY-MM-DD` |
| `DAMO_WHISPER_MODEL` | Whisper 模型，默认 `tiny` |
| `DAMO_LLM_TIMEOUT_SECONDS` | OpenClaw gateway 超时秒数，默认 `240` |
| `OPENCLI_PROFILE` | 指定 OpenCLI profile |
| `OPENCLI_EXT_DIR` | OpenCLI 扩展目录 |
| `A_STOCK_REPORT_DIR` | A 股日报/复盘目录，用于周报聚合 |

## 定时任务建议

每日追踪前一天，适合放在早晨：

```bash
openclaw cron add \
  --name "大摩闭门会每日追踪" \
  --cron "5 7 * * *" \
  --session isolated \
  --message "cd /path/to/damo-tracker && ./damo_run.sh，然后把 damo_report_current.md 发到量化群。"
```

周六 A 股周报可以读取 `damo_runs/`，生成“大摩追踪信号”区块；周日知识沉淀再把 A 股周报和大摩追踪合并复盘。

## 输出示例

见：

- `examples/sample_damo_report.md`
- `examples/sample_damo_result.json`

## 注意

本项目只做研究观察和信息整理，不构成投资建议。视频字幕、ASR 和模型提取都可能出错，报告会保留覆盖率、失败数、截断数和来源链接，方便复核。
