# Damo Tracker

大摩闭门会追踪器：从公开 B 站视频里提取可复核的 A/H 股强信号。

Damo Tracker 每天检索“大摩 / 摩根士丹利 / Morgan Stanley”相关公开视频，优先使用字幕，必要时尝试音频转写，再把明确看好、评级、目标价、首选、超配等强信号整理成结构化结果和群聊可读报告。

默认搜索会覆盖完整关键词矩阵，避免只搜“大摩闭门会”漏掉全称或英文标题：

- `大摩闭门会`、`大摩`、`大摩研报`、`大摩策略会`、`大摩电话会`
- `摩根士丹利`、`摩根士丹利闭门会`、`摩根士丹利研报`
- `Morgan Stanley`、`Morgan Stanley China`、`Morgan Stanley conference`、`Morgan Stanley research`、`MS research`

> 本项目只做研究观察和信息整理，不构成投资建议。视频字幕、ASR 和模型提取都可能出错，报告会保留来源链接、覆盖率和失败原因，方便二次复核。

## Highlights

- 自动扫描前一天的新公开视频，按日期归档结果。
- 能拿字幕就用字幕，没有字幕时尝试下载音频并转写。
- 只提取“明确推荐/看好/评级/目标价/首选”等高置信信号，降低标题党噪音。
- 保留来源视频、发布日期、截断状态、覆盖率和失败诊断，方便复核。
- 输出 `damo_result.json` 和 `damo_report_current.md`，可接入个人复盘或飞书群。

## Quick Start

```bash
git clone https://github.com/judefluen-coder/damo-tracker.git
cd damo-tracker
pip install -r requirements.txt
./damo_run.sh
```

指定日期范围：

```bash
DAMO_START_DATE=2026-06-06 DAMO_END_DATE=2026-06-15 ./damo_run.sh
```

## Why

机构观点常常散落在搬运视频、会议录音、字幕片段和二次解读里。人工每天刷内容耗时且容易遗漏；只看标题又容易把“提到了某股票”和“明确推荐某股票”混在一起。

Damo Tracker 把流程拆成“搜索 -> 获取内容 -> 提取股票 -> 防幻觉校验 -> 去重 -> 报告 -> 归档”。每次报告不只给股票，也给覆盖概览和失败诊断，让读者知道哪些是完整分析、哪些只是截断片段、哪些视频完全失败。

## 当前口径

- 截断 / 试看内容也会分析，但相关标的必须标注“仅基于截断片段，非完整视频”。
- 不写死任何分析模型，通过当前运行环境的 OpenClaw gateway 选择模型。
- 默认运行入口追踪前一天，定时运行方式由使用者自行配置。
- OpenCLI 是优先的数据获取能力，但不是硬依赖。
- 搜索层必须覆盖“大摩 / 摩根士丹利 / Morgan Stanley / MS research”等别名和中英文变体；内容抓取默认仍以 B 站为主，不自动纳入 YouTube。
- 报告按“覆盖概览 -> 标的速览 -> 标的详情 -> 截断片段 -> 失败诊断”呈现。

说明：本仓库的项目本体是“大摩视频追踪 -> 股票信号提取 -> 报告归档”。README 里出现的每日 cron、A 股周报、周末知识沉淀，是个人 OpenClaw 编排示例，不是项目默认必须包含的功能。

## 项目界面

打开 `index.html` 可以看到项目介绍页。仓库开启 GitHub Pages 后，也可以直接作为项目主页展示：

https://judefluen-coder.github.io/damo-tracker/

## 输出大概长什么样

报告会先给覆盖质量，再给标的速览，最后展开来源和失败原因。下面是 2026-06-06 到 2026-06-15 试跑的节选：

```text
大摩闭门会追踪
范围：2026-06-06 ~ 2026-06-15

覆盖概览
- 扫描：47 个视频
- 已分析：40 个，占 85.1%（完整 30 个，截断 10 个）
- 完全失败：7 个，占 14.9%
- 提取标的：10 支
- 口径：截断/试看片段也纳入分析，但所有相关标的单独标注“截断”

标的速览
1. 阳光电源 300274.SZ｜首次覆盖，看好｜目标价 230元｜AI 数据中心电力架构升级，储能、SST、一体化电力解决方案。
2. 大金重工 002487.SZ / 01081.HK｜看好｜海上风电基础装备订单、造船订单、欧洲本土化布局。
3. 先导智能 300450.SZ｜比较喜欢｜电池厂 CAPEX 扩张、技术迭代，新签订单和利润率回升。
4. 大族激光 002008.SZ｜比较喜欢｜PCB、苹果产业链、AI 服务器 PCB、光模块 PCB、先进封装 TGV。
5. 思源电气 002028.SZ｜非常喜欢，回调是买入机会｜订单趋势强，海外业务和产品结构改善。
6. 腾讯控股 00700.HK｜买入｜目标价 763港元｜微信小程序接入 AI 生态测试，微信 AI Agent 接近关键阶段。

标的详情
1. 阳光电源 300274.SZ
- 评级：首次覆盖，看好；目标价：230元
- 逻辑：公司正在从全球领先的光伏逆变器和储能企业转型为一体化 AI 电力解决方案提供商，有望受益于 AI 数据中心电力架构升级。
- 来源：2026-06-10｜大摩周期论剑闭门会｜https://www.bilibili.com/video/BV1o6Jw6HEHz

截断片段已分析
- 6-15号大摩最新闭门会：股票首席 Laura 发言：已使用日常 Chrome 登录 cookie 下载，但 B 站只返回疑似试看媒体（180秒 / 原视频965秒）；以下分析仅基于该截断片段

失败诊断
- 7 个，占完全失败 100%：B站 / yt-dlp 返回 412 或反爬限制
- 伴随信号：7 个视频没有可用公开字幕
```

## 可选：个人工作流集成示例

下面这部分是我的个人 OpenClaw 量化工作流，不是 Damo Tracker 的项目本体。它展示了如何把本项目产出的 `damo_runs/` 接到更大的复盘系统里：

- 每天早晨运行一次 Damo Tracker，默认追踪前一天
- 周六 A 股周报读取本周所有 `damo_runs/`，压成“大摩追踪信号”区块
- 周日知识沉淀再读取 A 股周报和本周大摩结果，提炼成“本周机构线索 -> 可跟踪标的 -> 需要复核的问题”

周报里的集成效果大概长这样：

```text
大摩追踪信号
- 本周扫描：47 个视频；已分析 40 个；完全失败 7 个；截断分析 10 个
- Raw 股票候选：12 个；去重后最终标的：10 支
- 值得跟踪：阳光电源、思源电气、腾讯控股、小鹏汽车、大金重工
- 风险提示：部分信号来自会议片段或视频转写，需结合原视频与行情二次复核
```

## 运行依赖

基础工具：

- Python 3.10+
- Node.js 18+（只在使用个人周报聚合示例时需要）
- `openclaw` CLI，并支持 `openclaw infer model run --gateway`
- `yt-dlp`
- `ffmpeg` / `ffprobe`
- `whisper`
- 可选：`opencli`，用于 B 站搜索、字幕和浏览器兜底

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

## 运行方式

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
- `scripts/a_stock_periodic_report.js`：个人 A 股周报聚合示例，可读入本周大摩追踪结果
- `cron-prompts/`：个人 OpenClaw cron 编排示例
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

## 可选：个人定时任务示例

这不是项目默认行为，只是我的个人配置方式。其他人可以用 cron、GitHub Actions、系统服务或自己的 agent runtime 来调度。

每日追踪前一天，适合放在早晨：

```bash
openclaw cron add \
  --name "大摩闭门会每日追踪" \
  --cron "5 7 * * *" \
  --session isolated \
  --message "cd /path/to/damo-tracker && ./damo_run.sh，然后把 damo_report_current.md 发到量化群。"
```

在我的个人配置里，周六 A 股周报会读取 `damo_runs/` 生成“大摩追踪信号”区块；周日知识沉淀再把 A 股周报和大摩追踪合并复盘。它们依赖我的 OpenClaw 工作区、飞书群和周报脚本，不属于 Damo Tracker 的通用安装步骤。

完整样例见：

- `examples/sample_damo_report.md`
- `examples/sample_damo_result.json`

## 注意

本项目只做研究观察和信息整理，不构成投资建议。视频字幕、ASR 和模型提取都可能出错，报告会保留覆盖率、失败数、截断数和来源链接，方便复核。
