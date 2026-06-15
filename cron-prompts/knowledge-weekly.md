请执行周末知识沉淀周报，并发成飞书原生 interactive 卡片。不要走 OpenClaw message/presentation 路径；只使用已验证的 `feishu-send-report-card.js` helper 发送卡片。

固定结构：
1. 周末知识沉淀
2. AI Builders 本周精选
3. GitHub 一周热点
4. A股周度与大摩追踪
5. 下周可迁移实验

内容要求：
- 读取工作空间 `memory/` 下最近7天日记，也检查 `memory/dreaming/light/` 中本周与用户明确要求沉淀相关的候选记忆。
- 对婚姻/情感/家庭等私密咨询，只写“已沉淀/核心方法论摘要”，不要展开隐私细节。
- 读取或搜索最近7天 AI Builders Digest；如果飞书消息 API 权限不足，用本地 follow-builders digest 文件交叉验证，并明确标注。
- 抓取 GitHub weekly trending（https://github.com/trending?since=weekly），必要时补抓 Python/TypeScript/Go/Rust 语言榜；用 GitHub API 复核重点仓库描述、总星数、license、最近 pushed_at。
- 读取最近一份 A股周度报告：优先 `$A_STOCK_REPORT_DIR/periodic_weekly_*.md`，其次当前工作目录 `tmp/cron-a-stock-weekly-*.md`。
- 读取本周 `damo_runs/damo_result_*.json` 和 `damo_report_*.md`，把“大摩追踪信号”合并进 A股周度内容：提炼本周新增标的、截断/失败口径、需要下周继续观察的方向。
- 所有热点/数据必须有原始来源链接或本地文件路径；不确定的不写。
- 卡片内容不能只做目录摘要，要写“发生了什么、为什么重要、已沉淀规则、下周动作”。

步骤：
1. 将完整周报正文写入 `/path/to/workspace/tmp/cron-knowledge-weekly-$(date +%Y%m%d).md`。正文按卡片可读性写：**本周主线**、**关键变化**、**AI Builders 可迁移信号**、**GitHub 热点分类**、**A股周度与大摩追踪**、**内容沉淀**、**下周动作**。
2. 运行：
   `node /path/to/feishu-send-report-card.js --to <knowledge-chat-id> --title "周末知识沉淀｜$(date +%Y-%m-%d)" --subtitle "本周沉淀、AI Builders、GitHub、A股周报和大摩追踪" --body-file /path/to/workspace/tmp/cron-knowledge-weekly-$(date +%Y%m%d).md --template blue --button "GitHub Weekly=https://github.com/trending?since=weekly" --button "学习记录表=<your-learning-base-url>" --footer "发送方式：飞书原生 interactive card；已核对 messageId/msgType。"`
3. 最终只回复 helper 返回的 JSON；不要调用 message/openclaw_message 工具，不要让 cron announce 文本。
