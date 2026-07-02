#!/usr/bin/env python3
import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript"}:
            self.skip = True

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"}:
            self.skip = False

    def handle_data(self, data):
        text = " ".join(str(data or "").split())
        if text and not self.skip:
            self.parts.append(text)


def fetch_text(url, timeout=12):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 stock-trading-coach-agent/1.0",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(1024 * 1024)
        charset = resp.headers.get_content_charset() or "utf-8"
    parser = TextExtractor()
    parser.feed(raw.decode(charset, errors="replace"))
    return html.unescape(" ".join(parser.parts))


def search_market_text(trade_date):
    query = f"{trade_date} A股 收盘 上证指数 创业板 科创50 板块 涨跌"
    urls = [
        "https://www.bing.com/search?q=" + urllib.parse.quote(query),
        "https://cn.bing.com/search?q=" + urllib.parse.quote(query),
    ]
    errors = []
    for url in urls:
        try:
            text = fetch_text(url)
            if len(text) > 500:
                return text, url, ""
        except Exception as exc:  # noqa: BLE001 - recorded in output.
            errors.append(f"{type(exc).__name__}: {exc}")
    return "", "", "；".join(errors) or "联网搜索无可用结果"


def sentences(text):
    chunks = re.split(r"[。！？!?；;\n]+", text)
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 8]


def pick_sentences(text, keywords, limit=5):
    picked = []
    for sentence in sentences(text):
        if any(keyword in sentence for keyword in keywords):
            cleaned = re.sub(r"\s+", " ", sentence)
            if cleaned not in picked:
                picked.append(cleaned[:180])
        if len(picked) >= limit:
            break
    return picked


def classify_regime(text):
    if any(word in text for word in ["普跌", "大跌", "重挫", "杀跌", "跳水"]):
        if any(word in text for word in ["科技", "半导体", "通信", "AI", "人工智能", "科创"]):
            return "杀高弹性"
        return "普跌"
    if any(word in text for word in ["震荡", "分化", "冲高回落", "高开低走"]):
        return "震荡"
    if any(word in text for word in ["修复", "反弹", "回暖"]):
        return "修复"
    if any(word in text for word in ["防守", "高股息", "银行", "医药", "白马"]):
        return "防守轮动"
    if any(word in text for word in ["强趋势", "主线", "放量上涨"]):
        return "强趋势"
    return "无法判断"


def classify_style(text):
    styles = []
    if any(word in text for word in ["科技", "半导体", "AI", "通信", "机器人", "算力", "科创"]):
        styles.append("成长/科技")
    if any(word in text for word in ["银行", "保险", "高股息", "红利", "煤炭", "电力"]):
        styles.append("价值/高股息")
    if any(word in text for word in ["医药", "白马", "消费", "防守"]):
        styles.append("防守")
    if any(word in text for word in ["题材", "连板", "短线", "情绪"]):
        styles.append("题材")
    return "、".join(styles) if styles else "无法判断"


def has_useful_market_evidence(text):
    if not text:
        return False
    index_hits = sum(word in text for word in ["上证", "深成", "创业板", "科创", "沪指"])
    movement_hits = sum(word in text for word in ["收盘", "上涨", "下跌", "涨幅", "跌幅", "重挫", "反弹", "走弱", "走强", "%"])
    ui_noise = sum(word in text[:800] for word in ["搜索", "跳至内容", "辅助功能反馈", "网页 图片 视频"])
    return index_hits >= 2 and movement_hits >= 2 and ui_noise < 3


def risk_appetite(text, regime):
    if regime in {"普跌", "杀高弹性"}:
        return "低"
    if regime in {"震荡", "防守轮动"}:
        return "中"
    if regime in {"强趋势", "修复"}:
        return "中高"
    if any(word in text for word in ["跌停", "亏钱效应", "缩量", "退潮"]):
        return "低"
    return "无法判断"


def load_json(path, default):
    if not path or not Path(path).exists():
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def format_pct(value):
    if isinstance(value, (int, float)):
        return f"{value:+.2f}%"
    return "无法判断"


def format_amount(value):
    if isinstance(value, (int, float)):
        if abs(value) >= 100000000:
            return f"{value / 100000000:.1f}亿"
        return f"{value:.0f}"
    return "无法判断"


def format_index_line(item):
    name = item.get("name") or item.get("code") or "指数"
    return (
        f"{name} 收 {item.get('price', '无法判断')}，涨跌幅 {format_pct(item.get('change_pct'))}，"
        f"成交额 {format_amount(item.get('amount'))}，时间 {item.get('date', '')} {item.get('time', '')}".strip()
    )


def format_sector_line(item):
    name = item.get("sector_name") or item.get("stock_name") or item.get("name") or item.get("stock_code") or "未知方向"
    return f"{name} {format_pct(item.get('change_pct'))}"


def infer_style_from_snapshot(snapshot):
    names = " ".join(
        [item.get("sector_name", "") for item in snapshot.get("sector_strength", [])[:12]]
        + [item.get("stock_name", "") for item in snapshot.get("top_change", [])[:20]]
    )
    return classify_style(names)


def infer_regime_from_snapshot(snapshot):
    indices = {item.get("name"): item for item in snapshot.get("indices", [])}
    changes = [item.get("change_pct") for item in snapshot.get("indices", []) if isinstance(item.get("change_pct"), (int, float))]
    if not changes:
        return "无法判断"
    avg_change = sum(changes) / len(changes)
    sh = indices.get("上证指数", {}).get("change_pct")
    cyb = indices.get("创业板指", {}).get("change_pct")
    kc = indices.get("科创50", {}).get("change_pct")
    if avg_change <= -1.5:
        return "普跌"
    if isinstance(cyb, (int, float)) and isinstance(kc, (int, float)) and isinstance(sh, (int, float)):
        if cyb < sh - 1.0 and kc < sh - 1.0:
            return "杀高弹性"
    if max(changes) > 0 and min(changes) < 0:
        return "震荡"
    if avg_change >= 1.0:
        return "修复"
    if avg_change >= 0.2:
        return "强趋势"
    return "震荡"


def infer_risk_from_snapshot(snapshot, regime):
    if regime in {"普跌", "杀高弹性"}:
        return "低"
    if regime == "震荡":
        return "中"
    if regime in {"修复", "强趋势"}:
        return "中高"
    return "无法判断"


def build_from_market_data(args, snapshot):
    user_view = args.user_view or ""
    indices = snapshot.get("indices", [])
    verified = bool(snapshot.get("network_verified") and indices)
    regime = infer_regime_from_snapshot(snapshot) if verified else "无法判断"
    style = infer_style_from_snapshot(snapshot) if verified else "无法判断"
    appetite = infer_risk_from_snapshot(snapshot, regime) if verified else "无法判断"
    provider_messages = [
        f"{item.get('provider')}: {'OK' if item.get('ok') else 'FAIL'} {item.get('message', '')}"
        for item in snapshot.get("provider_status", [])
    ]
    if verified:
        coach_view = f"公开行情快照显示市场更接近“{regime}”，风格偏向“{style}”，风险偏好为“{appetite}”。"
    else:
        coach_view = "市场背景未联网验证，不能把用户判断直接当成事实。"
    agreement, correction = compare_user_view(user_view, coach_view, regime, style)
    if verified and regime in {"杀高弹性", "普跌"}:
        implication = "弱环境下，成长股低吸和做 T 需要更强确认；不是价格便宜就能试错。"
    elif verified and regime == "震荡":
        implication = "震荡环境下，临盘追涨和频繁切换容易被波动消耗，需降低交易频率。"
    elif verified and regime in {"修复", "强趋势"}:
        implication = "修复或趋势环境可以观察强弱分化，但仍需按失败条件控制仓位。"
    else:
        implication = "无法判断；缺少可靠市场背景时，应降低对宏观叙事的依赖。"
    return {
        "trade_date": args.trade_date,
        "network_verified": verified,
        "source_url": "market_data_snapshot.json",
        "fetch_error": "" if verified else "行情快照不足；" + "；".join(provider_messages[:4]),
        "major_indices": [format_index_line(item) for item in indices] or ["无法判断"],
        "sector_strength": [format_sector_line(item) for item in snapshot.get("sector_strength", [])[:8]] or [format_sector_line(item) for item in snapshot.get("top_change", [])[:8]] or ["无法判断"],
        "sector_weakness": [format_sector_line(item) for item in snapshot.get("sector_weakness", [])[:8]] or ["无法判断"],
        "style_bias": style,
        "risk_appetite": appetite,
        "market_regime": regime,
        "coach_view": coach_view,
        "user_view": user_view or "无法判断",
        "agreement": agreement,
        "correction": correction,
        "trading_implication": implication,
        "provider_status": snapshot.get("provider_status", []),
        "storage_policy": "只保存公开行情摘要、接口状态和纠偏判断，不保存网页全文。",
    }


def compare_user_view(user_view, coach_view, regime, style):
    if not user_view.strip():
        return "无法判断", "用户未提供市场判断。"
    hits = 0
    checks = [regime, style]
    if any(word in user_view for word in ["科技", "成长", "高弹性"]) and "科技" in style + coach_view:
        hits += 1
    if any(word in user_view for word in ["防守", "医药", "白马", "高股息"]) and any(word in style + coach_view for word in ["防守", "价值", "高股息"]):
        hits += 1
    if any(word in user_view for word in ["普跌", "杀", "回调", "冲高回落"]) and regime in {"普跌", "杀高弹性", "震荡"}:
        hits += 1
    if any(word in user_view for word in ["看不懂", "不确定", "不知道"]):
        return "部分一致", "不确定感本身是有效信号，但不能替代指数、题材、量能和强弱板块验证。"
    if hits >= 2:
        return "一致", "用户判断与独立市场背景大体一致。"
    if hits == 1:
        return "部分一致", "用户抓住了部分风格变化，但还需要用指数、板块强弱和量能校验。"
    return "不一致", "用户判断缺少可验证盘面证据，或与独立市场背景不匹配。"


def build_context(args):
    user_view = args.user_view or ""
    snapshot = load_json(args.market_data, {}) if getattr(args, "market_data", "") else {}
    if snapshot:
        return build_from_market_data(args, snapshot)

    market_text, source_url, error = search_market_text(args.trade_date)
    verified = has_useful_market_evidence(market_text)
    combined = market_text
    if market_text and not verified and not error:
        error = "联网成功但未提取到足够可靠的市场行情摘要"

    major_indices = pick_sentences(combined, ["上证", "深成", "创业板", "科创", "指数", "沪指"]) if verified else []
    sector_strength = pick_sentences(combined, ["领涨", "上涨", "强势", "涨幅", "走强", "活跃"]) if verified else []
    sector_weakness = pick_sentences(combined, ["领跌", "下跌", "跌幅", "走弱", "杀跌", "重挫"]) if verified else []
    regime = classify_regime(combined) if verified else "无法判断"
    style = classify_style(combined) if verified else "无法判断"
    appetite = risk_appetite(combined, regime) if verified else "无法判断"
    coach_view = (
        f"联网信息显示市场更接近“{regime}”，风格偏向“{style}”，风险偏好为“{appetite}”。"
        if verified
        else "市场背景未联网验证，不能把用户判断直接当成事实。"
    )
    agreement, correction = compare_user_view(user_view, coach_view, regime, style)
    if verified and regime in {"杀高弹性", "普跌"}:
        implication = "弱环境下，成长股低吸和做 T 需要更强确认；不是价格便宜就能试错。"
    elif verified and regime == "震荡":
        implication = "震荡环境下，临盘追涨和频繁切换容易被波动消耗，需降低交易频率。"
    elif verified and regime in {"修复", "强趋势"}:
        implication = "修复或趋势环境可以观察强弱分化，但仍需按失败条件控制仓位。"
    else:
        implication = "无法判断；缺少可靠市场背景时，应降低对宏观叙事的依赖。"

    return {
        "trade_date": args.trade_date,
        "network_verified": verified,
        "source_url": source_url,
        "fetch_error": error,
        "major_indices": major_indices or ["无法判断" if not verified else "未从公开页面提取到足够指数摘要"],
        "sector_strength": sector_strength or ["无法判断"],
        "sector_weakness": sector_weakness or ["无法判断"],
        "style_bias": style,
        "risk_appetite": appetite,
        "market_regime": regime,
        "coach_view": coach_view,
        "user_view": user_view or "无法判断",
        "agreement": agreement,
        "correction": correction,
        "trading_implication": implication,
        "storage_policy": "只保存市场摘要和纠偏判断，不保存网页全文。",
    }


def main():
    parser = argparse.ArgumentParser(description="独立判断市场环境并校正用户市场判断")
    parser.add_argument("--trade-date", default=date.today().isoformat())
    parser.add_argument("--user-view", default="")
    parser.add_argument("--article-url", action="append", default=[])
    parser.add_argument("--market-data", default="", help="market_data_provider.py 生成的行情快照。")
    parser.add_argument("-o", "--output", default="market_context.json")
    args = parser.parse_args()

    context = build_context(args)
    Path(args.output).write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
