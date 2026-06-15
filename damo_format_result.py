#!/usr/bin/env python3
from collections import Counter
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("DAMO_WORKSPACE", Path.cwd())).expanduser().resolve()
OPENCLI_EXTENSION_PATH = Path(os.environ.get("OPENCLI_EXT_DIR", ROOT / "opencli-extension")).expanduser()


TEXT_FIXES = {
    "港并元": "港元",
    "港币元": "港元",
    "港并": "港币",
    "新IP依处就暴": "新IP爆发",
    "依处就暴": "爆发",
    "就暴": "爆发",
    "大模": "大摩",
}


FAILURE_LABELS = {
    "opencli_bridge": "OpenCLI Browser Bridge 未连接，完整字幕/登录态媒体不可用",
    "bili_preview": "B站只返回疑似试看媒体，无法完整转写长视频",
    "bili_412": "B站/yt-dlp 返回 412 或反爬限制",
    "no_subtitle": "视频没有可用公开字幕",
    "llm_extract": "默认模型提取异常",
    "other": "其他内容获取异常",
}


def clean_text(value):
    text = str(value or "")
    for src, dst in TEXT_FIXES.items():
        text = text.replace(src, dst)
    return text


def failure_tags(reason):
    reason = str(reason or "")
    tags = []
    if (
        "BROWSER_CONNECT" in reason
        or "Browser Bridge extension not connected" in reason
        or "exitCode: 69" in reason
        or "not connected" in reason
    ):
        tags.append("opencli_bridge")
    if "试看媒体" in reason:
        tags.append("bili_preview")
    if "HTTP Error 412" in reason or " 412" in reason:
        tags.append("bili_412")
    if "No subtitles found" in reason or "无字幕列表" in reason or "未生成有效字幕" in reason:
        tags.append("no_subtitle")
    if "OpenClaw model gateway" in reason or "NO_LLM_EXTRACTOR" in reason:
        tags.append("llm_extract")
    return tags or ["other"]


def compact_reason(reason):
    tags = failure_tags(reason)
    primary = tags[0]
    details = []
    if "bili_preview" in tags and primary != "bili_preview":
        details.append("伴随 B站试看媒体")
    if "bili_412" in tags and primary != "bili_412":
        details.append("伴随 412 限制")
    if "no_subtitle" in tags and primary != "no_subtitle":
        details.append("伴随无公开字幕")
    label = FAILURE_LABELS.get(primary, FAILURE_LABELS["other"])
    if details:
        return label + "（" + "、".join(details) + "）"
    reason = str(reason or "").replace("\n", " ")
    if primary == "other" and reason:
        return clean_text(reason[:220])
    return label


def failure_digest(failed):
    primary = Counter()
    all_tags = Counter()
    for item in failed:
        tags = failure_tags(item.get("reason", ""))
        primary[tags[0]] += 1
        all_tags.update(tags)
    return primary, all_tags


def pct(count, total):
    if not total:
        return "0%"
    value = count * 100 / total
    return ("{:.1f}%".format(value)).replace(".0%", "%")


def brief_text(value, limit=72):
    text = clean_text(str(value or "")).replace("\n", " ")
    text = re_sub_spaces(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("，。；、 ") + "..."


def re_sub_spaces(text):
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def normalize_target(value):
    target = clean_text(value or "原文未提及").strip() or "原文未提及"
    if target != "原文未提及" and not any(unit in target for unit in ("元", "港元", "港币", "人民币", "PB", "倍")):
        target += "元"
    return target


def stock_name_with_code(item):
    name = clean_text(item.get("股票名称", "")).strip() or "未命名标的"
    code = clean_text(item.get("股票代码", "")).strip()
    if code and code not in ("原文未提及", "无", "未知", "-"):
        return "{} {}".format(name, code)
    return name


def stock_overview_line(index, item):
    quality = "｜截断" if item.get("_content_quality") == "partial" else ""
    target = normalize_target(item.get("目标价"))
    target_part = "" if target == "原文未提及" else "｜目标价 {}".format(target)
    return "{}. {}｜{}{}{}｜{}".format(
        index,
        stock_name_with_code(item),
        clean_text(item.get("评级") or "评级未提及"),
        target_part,
        quality,
        brief_text(item.get("推荐理由"), 54),
    )


def stock_detail_block(index, item):
    lines = []
    title = "{}. {}".format(index, stock_name_with_code(item))
    rating = clean_text(item.get("评级") or "原文未提及")
    target = normalize_target(item.get("目标价"))
    lines.append(title)
    lines.append("- 评级：{}；目标价：{}".format(rating, target))
    if item.get("_content_quality") == "partial":
        lines.append("- 内容状态：仅基于截断片段，非完整视频")
    lines.append("- 逻辑：{}".format(brief_text(item.get("推荐理由"), 150) or "原文未提及"))
    source_title = brief_text(item.get("来源视频"), 46)
    source_url = clean_text(item.get("来源链接") or "")
    source_date = clean_text(item.get("发布日期") or "")
    source = "{}｜{}".format(source_date, source_title).strip("｜")
    if source_url:
        source += "｜{}".format(source_url)
    lines.append("- 来源：{}".format(source or "原文未提及"))
    return lines


def main():
    result_path = ROOT / "damo_result.json"
    if not result_path.exists():
        raise SystemExit("damo_result.json not found")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    date_range = result.get("date_range") or []
    videos = result.get("videos") or []
    failed = result.get("failed") or []
    partial = result.get("partial") or []
    stocks = result.get("stocks") or []
    messages = result.get("messages") or []

    total = len(videos)
    failed_count = len(failed)
    partial_count = len(partial)
    analyzed_count = total - failed_count
    complete_count = analyzed_count - partial_count
    partial_stock_count = sum(1 for item in stocks if item.get("_content_quality") == "partial")

    lines = []
    lines.append("大摩闭门会追踪")
    if len(date_range) == 2:
        lines.append("范围：{} ~ {}".format(date_range[0], date_range[1]))
    lines.append("")
    lines.append("覆盖概览")
    lines.append("- 扫描：{} 个视频".format(total))
    lines.append("- 已分析：{} 个，占 {}（完整 {} 个，截断 {} 个）".format(analyzed_count, pct(analyzed_count, total), complete_count, partial_count))
    lines.append("- 完全失败：{} 个，占 {}".format(failed_count, pct(failed_count, total)))
    lines.append("- 提取标的：{} 支{}".format(len(stocks), "，其中 {} 支来自截断片段".format(partial_stock_count) if partial_stock_count else ""))
    if partial_count:
        lines.append("- 口径：截断/试看片段也纳入分析，但所有相关标的单独标注“截断”")
    lines.append("")

    if stocks:
        lines.append("标的速览")
        for index, item in enumerate(stocks, 1):
            lines.append(stock_overview_line(index, item))
        lines.append("")
    else:
        lines.append("本次未提取到可发布的A股/港股推荐。")
        lines.append("")

    if stocks:
        lines.append("标的详情")
        for index, item in enumerate(stocks, 1):
            lines.extend(stock_detail_block(index, item))
        lines.append("")

    if partial:
        lines.append("截断片段已分析")
        for item in partial[:5]:
            lines.append("- {}：{}".format(brief_text(item.get("title") or item.get("bvid"), 44), clean_text(item.get("reason", ""))))
        if len(partial) > 5:
            lines.append("- 另有{}个截断视频已基于可用片段分析，完整明细见 damo_result.json。".format(len(partial) - 5))
        lines.append("")

    if failed:
        primary, all_tags = failure_digest(failed)
        lines.append("失败诊断")
        for tag, count in primary.most_common():
            lines.append("- {} 个，占完全失败 {}：{}".format(count, pct(count, failed_count), FAILURE_LABELS.get(tag, FAILURE_LABELS["other"])))
        secondary = [
            "{}个{}".format(count, FAILURE_LABELS[tag])
            for tag, count in all_tags.most_common()
            if tag not in primary and tag in FAILURE_LABELS
        ]
        if secondary:
            lines.append("- 伴随信号：" + "；".join(secondary))
        if all_tags.get("opencli_bridge"):
            lines.append("")
            lines.append("处理动作：OpenCLI daemon 正常，但 Chrome 扩展未连接；请在 Chrome 的 chrome://extensions/ 启用 Developer Mode 后 Load unpacked：")
            lines.append(str(OPENCLI_EXTENSION_PATH))
            lines.append("连好后可手动重跑：./damo_run.sh")
        lines.append("")
        lines.append("失败样例（最多5条）")
        for item in failed[:5]:
            lines.append("- {}：{}".format(brief_text(item.get("title") or item.get("bvid"), 44), compact_reason(item.get("reason", ""))))
        if len(failed) > 5:
            lines.append("- 另有{}个同类内容获取异常，完整明细见 damo_result.json。".format(len(failed) - 5))

    report_path = ROOT / "damo_report_current.md"
    report_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
