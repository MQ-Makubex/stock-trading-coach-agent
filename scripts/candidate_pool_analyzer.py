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


def score_candidate(row, market_context):
    raw = row.get("raw", "")
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
    if any(token in raw for token in ["200日", "200 日", "年线", "5日", "10日", "均线"]):
        dongge["technical_position"] = 12
    if any(token in raw for token in ["放量", "量能", "换手", "主动", "分时"]):
        dongge["volume_initiative"] = 12
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
    if dongge["technical_position"] >= 12:
        buy_type = "均线先手/回踩试错"
        trigger = "接近 5/10 日线或 200 日线，且板块同步修复、分时主动、量能不虚。"
        stop = "跌破对应均线且尾盘无法站回；或盘中跌破后两次反弹站不回。"
    elif dongge["trade_node"] >= 8:
        buy_type = "分歧低吸/低开承接"
        trigger = "低开后出现强承接，板块没有继续退潮，个股重新成为前排。"
        stop = "低开承接失败，跌破承接区且二次反弹站不回。"
    else:
        buy_type = "只观察"
        trigger = "补齐题材强度、量能、均线位置和失败条件。"
        stop = "无法定义止损前不进入试错。"
    return {
        "security": label,
        "research_score": total,
        "dongge_score": dongge,
        "bingbing_score": bingbing,
        "theme": "从用户候选池文本推断，需人工确认",
        "buy_point_type": buy_type,
        "trigger_condition": trigger,
        "stop_anchor": stop,
        "forbidden_condition": "没有强题材、没有量能、离止损锚点太远，或只是怕踏空时禁止买入。",
        "dongge_challenge": "这是节点买点，还是后手追涨？止损点能不能在下单前写清？",
        "bingbing_risk": "检查当前风格是否匹配，科技/高弹性方向要警惕叙事拥挤和外部风险扰动。",
    }


def build(args):
    market_context = load_json(args.market_context, {})
    candidate_text = ""
    if args.candidate_text_file and Path(args.candidate_text_file).exists():
        candidate_text = Path(args.candidate_text_file).read_text(encoding="utf-8", errors="ignore")
    elif args.candidate_text:
        candidate_text = args.candidate_text

    parsed = parse_candidate_text(candidate_text)
    if not parsed:
        return {
            "status": "unavailable",
            "source": "none",
            "network_attempted": False,
            "message": "第一阶段不硬编全市场候选。请粘贴强势榜、候选池或板块前排，才能生成研究候选池。",
            "required_format": "每行包含：证券代码 证券名称 题材/位置/量能/均线/止损线索，例如：301421 波长光电 科技 放量 回踩200日线 止损200日线。",
            "weights": {"dongge": DONGGE_WEIGHTS, "bingbing": BINGBING_WEIGHTS},
            "candidates": [],
        }

    candidates = [build_candidate(row, market_context) for row in parsed]
    candidates.sort(key=lambda item: item["research_score"], reverse=True)
    return {
        "status": "ok",
        "source": "user_pasted_candidate_pool",
        "network_attempted": False,
        "message": "基于用户粘贴候选池生成研究预案；不是荐股，不构成买卖建议。",
        "weights": {"dongge": DONGGE_WEIGHTS, "bingbing": BINGBING_WEIGHTS},
        "candidates": candidates[:5],
    }


def main():
    parser = argparse.ArgumentParser(description="生成研究候选池。第一阶段只使用用户粘贴候选池，不硬编全市场筛选。")
    parser.add_argument("--market-context", default="market_context.json")
    parser.add_argument("--candidate-text", default="")
    parser.add_argument("--candidate-text-file", default="")
    parser.add_argument("-o", "--output", default="candidate_pool.json")
    args = parser.parse_args()

    result = build(args)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
