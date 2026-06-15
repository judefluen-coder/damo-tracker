执行 A股周度报告，并发成飞书原生 interactive 卡片。

步骤：
1. 运行：
   `cd /path/to/damo-tracker && mkdir -p tmp && node scripts/a_stock_periodic_report.js weekly > tmp/cron-a-stock-weekly-$(date +%Y%m%d).md`
2. 读取输出文件，确认里面包含这些区块：一句话结论、大盘与板块、个股信号、大摩追踪信号、每日摘要、来源文件。
3. 若本周 `damo_runs/` 有大摩追踪结果，周报必须保留“大摩追踪信号”区块，包含本周扫描次数、视频数、截断但已分析、完全失败、raw 候选、去重标的，以及可跟踪标的摘要。
4. 运行：
   `node /path/to/feishu-send-report-card.js --to <quant-chat-id> --title "A股周度报告｜$(date +%Y-%m-%d)" --subtitle "组合周度回顾、风险、下周关注与本周大摩追踪信号" --body-file /path/to/damo-tracker/tmp/cron-a-stock-weekly-$(date +%Y%m%d).md --template blue --footer "来源：A股日报/大盘复盘 + damo_runs；研究观察，不构成投资建议。"`
5. 最终只回复 helper 返回的 JSON；不要调用 message/openclaw_message 工具，不要让 cron announce 文本。脚本报错则让任务失败。
