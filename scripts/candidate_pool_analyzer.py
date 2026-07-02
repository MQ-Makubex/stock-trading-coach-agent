#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


DONGGE_WEIGHTS = {
    "theme_strength": 20,
    "technical_position": 15,
    "volume_initiative": 15,
    "risk_defined": 15,
    "trade_node": 10,
    "intraday_character": 5,
}

BINGBING_WEIGHTS = {
    "style_fit": 8,
    "external_risk": 6,
    "narrative_crowding": 6,
}


def load_json(path, default):
    if not path or not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_candidate_text(text):
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        code_match = re.search(r"(?<!\d)([036]\d{5})(?!\d)", line)
        if not code_match:
            continue
        code = code_match.group(1)
        after = line[code_match.end():].strip(" \t,，|")
        before = line[:code_match.start()].strip(" \t,，|")
        name = ""
        if after:
            name = re.split(r"[\s,，|]+", after)[0]
        if not name and before:
            name = re.split(r"[\s,，|]+", before)[-1]
        rows.append({"stock_code": code, "stock_name": name, "raw": line})
    return rows


def number(value, default=None):
    try:
        if value in (None, "", "-"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def market_rows_from_snapshot(snapshot, limit=20):
    rows = []
    seen = set()
    source_rows = []
    source_rows.extend(snapshot.get("top_change", [])[:limit])
    source_rows.extend(snapshot.get("top_amount", [])[:limit])
    if not source_rows:
        source_rows.extend(snapshot.get("stocks", [])[:limit])
    for item in source_rows:
        code = str(item.get("stock_code") or item.get("code") or "").strip()
        if not re.match(r"^[036]\d{5}$", code) or code in seen:
            continue
        seen.add(code)
        name = item.get("stock_name") or item.get("name") or ""
        if name.startswith("N") or "ST" in name.upper():
            continue
        chg = item.get("change_pct")
        amount = item.get("amount")
        turnover = item.get("turnover")
        volume_ratio = item.get("volume_ratio")
        raw = (
            f"{code} {name} 涨跌幅{chg if chg is not None else '未知'} "
            f"成交额{amount if amount is not None else '未知'} 换手{turnover if turnover is not None else '未知'} "
            f"量比{volume_ratio if volume_ratio is not None else '未知'}"
        )
        rows.append({
            "stock_code": code,
            "stock_name": name,
            "raw": raw,
            "market_snapshot": item,
        })
    return rows


def score_candidate(row, market_context):
    raw = row.get("raw", "")
    snapshot = row.get("market_snapshot", {})
    change_pct = number(snapshot.get("change_pct"))
    amount = number(snapshot.get("amount"))
    turnover = number(snapshot.get("turnover"))
    volume_ratio = number(snapshot.get("volume_ratio"))
    dongge = {
        "theme_strength": 10,
        "technical_position": 0,
        "volume_initiative": 0,
        "risk_defined": 8,
        "trade_node": 0,
        "intraday_character": 0,
    }
    if any(token in raw for token in ["主线", "强题材", "领涨", "核心", "板块前排"]):
        dongge["theme_strength"] = 18
    if change_pct is not None and change_pct >= 5:
        dongge["theme_strength"] = max(dongge["theme_strength"], 14)
    if any(token in raw for token in ["200日", "200 日", "年线", "5日", "10日", "均线"]):
        dongge["technical_position"] = 12
    if any(token in raw for token in ["放量", "量能", "换手", "主动", "分时"]):
        dongge["volume_initiative"] = 12
    if amount is not None and amount >= 1000000000:
        dongge["volume_initiative"] = max(dongge["volume_initiative"], 10)
    if turnover is not None and turnover >= 5:
        dongge["volume_initiative"] = max(dongge["volume_initiative"], 9)
    if volume_ratio is not None and volume_ratio >= 1.5:
        dongge["volume_initiative"] = max(dongge["volume_initiative"], 10)
    if any(token in raw for token in ["止损", "失效", "跌破", "尾盘"]):
        dongge["risk_defined"] = 14
    if any(token in raw for token in ["分歧", "修复", "低开承接", "突破", "节点"]):
        dongge["trade_node"] = 8
    if any(token in raw for token in ["股性", "弹性", "抗跌", "强承接"]):
        dongge["intraday_character"] = 4

    style = market_context.get("style_bias", "")
    bingbing = {
        "style_fit": 4,
        "external_risk": 3,
        "narrative_crowding": 3,
    }
    if style and style != "无法判断" and any(token in raw for token in style.split("、")):
        bingbing["style_fit"] = 7
    if any(token in raw for token in ["半导体", "AI", "算力", "存储", "机器人", "科技"]):
        bingbing["external_risk"] = 2
        bingbing["narrative_crowding"] = 2
    if any(token in raw for token in ["高股息", "医药", "消费", "防守"]):
        bingbing["external_risk"] = 5

    dongge_score = sum(dongge.values())
    bingbing_score = sum(bingbing.values())
    total = dongge_score + bingbing_score
    return dongge, bingbing, total


def build_candidate(row, market_context):
    dongge, bingbing, total = score_candidate(row, market_context)
    label = f"{row.get('stock_code')} {row.get('stock_name')}".strip()
    snapshot = row.get("market_snapshot", {})
    kline_note = ""
    if snapshot:
        kline_note = "公开快照只能确认当日强弱和量能，未确认 200 日均线位置。"
    if dongge["technical_position"] >= 12:
        buy_type = "均线先手/回踩试错"
        trigger = "接近 5/10 日线或 200 日线，且板块同步修复、分时主动、量能不虚。"
        stop = "跌破对应均线且尾盘无法站回；或盘中跌破后两次反弹站不回。"
    elif snapshot and dongge["theme_strength"] >= 14 and dongge["volume_initiative"] >= 9:
        buy_type = "强势放量候选，等待均线位置确认"
        trigger = "先确认是否上穿或回踩 200 日均线；若没有清晰止损锚点，只能列入观察。"
        stop = "若后续验证为 200 日线下方弱反抽，或放量后次日承接失败，不进入试错。"
    elif dongge["trade_node"] >= 8:
        buy_type = "分歧低吸/低开承接"
        trigger = "低开后出现强承接，板块没有继续退潮，个股重新成为前排。"
        stop = "低开承接失败，跌破承接区且二次反弹站不回。"
    else:
        buy_type = "只观察"
        trigger = "补齐题材强度、量能、均线位置和失败条件。"
        stop = "无法定义止损前不进入试错。"
    theme = "从公开行情快照推断，需人工确认题材" if snapshot else "从用户候选池文本推断，需人工确认"
    return {
        "security": label,
        "research_score": total,
        "dongge_score": dongge,
        "bingbing_score": bingbing,
        "theme": theme,
        "buy_point_type": buy_type,
        "trigger_condition": trigger,
        "stop_anchor": stop,
        "forbidden_condition": "没有强题材、没有量能、离止损锚点太远，或只是怕踏空时禁止买入。",
        "dongge_challenge": "这是节点买点，还是后手追涨？止损点能不能在下单前写清？",
        "bingbing_risk": "检查当前风格是否匹配，科技/高弹性方向要警惕叙事拥挤和外部风险扰动。",
        "market_snapshot_evidence": {
            "change_pct": snapshot.get("change_pct"),
            "amount": snapshot.get("amount"),
            "turnover": snapshot.get("turnover"),
            "volume_ratio": snapshot.get("volume_ratio"),
            "note": kline_note or "来自用户粘贴候选池，需人工确认行情证据。",
        },
    }


def build(args):
    market_context = load_json(args.market_context, {})
    market_data = load_json(args.market_data, {})
    candidate_text = ""
    if args.candidate_text_file and Path(args.candidate_text_file).exists():
        candidate_text = Path(args.candidate_text_file).read_text(encoding="utf-8", errors="ignore")
    elif args.candidate_text:
        candidate_text = args.candidate_text

    parsed = parse_candidate_text(candidate_text)
    source = "user_pasted_candidate_pool"
    message = "基于用户粘贴候选池生成研究预案；不是荐股，不构成买卖建议。"
    if not parsed and market_data:
        parsed = market_rows_from_snapshot(market_data)
        source = "market_data_snapshot"
        message = "基于公开行情快照生成研究候选；仅用于学术研究预案，未验证 200 日均线位置，不构成买卖建议。"
    if not parsed:
        return {
            "status": "unavailable",
            "source": "none",
            "network_attempted": bool(market_data),
            "message": "未获得可用公开候选池。请粘贴强势榜、候选池或板块前排，才能生成研究候选池。",
            "required_format": "每行包含：证券代码 证券名称 题材/位置/量能/均线/止损线索，例如：301421 波长光电 科技 放量 回踩200日线 止损200日线。",
            "weights": {"dongge": DONGGE_WEIGHTS, "bingbing": BINGBING_WEIGHTS},
            "candidates": [],
        }

    candidates = [build_candidate(row, market_context) for row in parsed]
    candidates.sort(key=lambda item: item["research_score"], reverse=True)
    return {
        "status": "ok",
        "source": source,
        "network_attempted": bool(market_data),
        "message": message,
        "weights": {"dongge": DONGGE_WEIGHTS, "bingbing": BINGBING_WEIGHTS},
        "candidates": candidates[:5],
    }


def main():
    parser = argparse.ArgumentParser(description="生成研究候选池。优先使用用户粘贴候选池，其次使用公开行情快照。")
    parser.add_argument("--market-context", default="market_context.json")
    parser.add_argument("--market-data", default="")
    parser.add_argument("--candidate-text", default="")
    parser.add_argument("--candidate-text-file", default="")
    parser.add_argument("-o", "--output", default="candidate_pool.json")
    args = parser.parse_args()

    result = build(args)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
