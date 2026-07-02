#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path


USER_RULES = {
    "position_unit": "5 万元为一个单位",
    "buyback_rule": "5 日线附近只允许试错仓，不允许情绪性买回",
    "stop_rule": "破 10 日线按尾盘有效跌破处理；或盘中跌破日内均线且两次反弹无法站回时处理风险",
    "style": "硬判断 + 条件句",
}


def load_json(path, default):
    if not path or not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_text(path):
    if not path or not Path(path).exists():
        return ""
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def security_label(code, item):
    return f"{code} {item.get('security_name', '')}".strip()


def fnum(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def events_by_stock_day(lifecycle):
    grouped = defaultdict(list)
    for code, item in lifecycle.items():
        for event in item.get("events", []):
            grouped[(code, item.get("security_name", ""), event.get("date", ""))].append(event)
    return grouped


def t_trade_map(lifecycle):
    results = {}
    for (code, name, day), events in events_by_stock_day(lifecycle).items():
        buys = [event for event in events if event.get("side") == "BUY"]
        sells = [event for event in events if event.get("side") == "SELL"]
        if not buys or not sells:
            continue
        buy_qty = sum(fnum(event.get("quantity")) for event in buys)
        sell_qty = sum(fnum(event.get("quantity")) for event in sells)
        buy_amt = sum(fnum(event.get("amount")) for event in buys)
        sell_amt = sum(fnum(event.get("amount")) for event in sells)
        avg_buy = buy_amt / buy_qty if buy_qty else 0.0
        avg_sell = sell_amt / sell_qty if sell_qty else 0.0
        gross_cash_result = min(buy_qty, sell_qty) * (avg_sell - avg_buy)
        if avg_sell > avg_buy:
            label = "正 T"
        elif avg_sell < avg_buy:
            label = "负 T"
        else:
            label = "平 T"
        results[code] = {
            "date": day,
            "security_name": name,
            "avg_buy": round(avg_buy, 3),
            "avg_sell": round(avg_sell, 3),
            "matched_quantity": min(buy_qty, sell_qty),
            "gross_cash_result": round(gross_cash_result, 2),
            "label": label,
        }
    return results


def infer_buy_point(code, item, t_result, journal_text):
    text = journal_text
    if t_result:
        if t_result["label"] == "负 T":
            return "负 T 修复动作"
        return t_result["label"]
    events = item.get("events", [])
    has_buy = any(event.get("side") == "BUY" for event in events)
    has_sell = any(event.get("side") == "SELL" for event in events)
    if has_buy and not has_sell:
        if "200" in text and (code in text or item.get("security_name", "") in text):
            return "200 日线试错"
        if any(token in text for token in ["5日", "五日", "5 日"]):
            return "5 日线先手待验证"
        return "新开仓待验证"
    if has_sell and not has_buy:
        return "退出动作"
    return "无法判断"


def stock_guidance(code, item, t_result, journal, market_context):
    label = security_label(code, item)
    journal_text = json.dumps(journal, ensure_ascii=False)
    buy_point = infer_buy_point(code, item, t_result, journal_text)
    market_regime = market_context.get("market_regime", "无法判断")
    risk_appetite = market_context.get("risk_appetite", "无法判断")
    has_open = fnum(item.get("open_quantity")) > 0

    if buy_point == "负 T 修复动作":
        hard = f"{label}：硬判断，这是负 T，不是舒服买点。今天的核心问题不是卖飞，而是弱环境里先买后卖导致试错成本外溢。"
        trigger = "只有重新出现板块同步修复、分时主动转强、站回关键均线，才允许按一个单位以内重新定义试错。"
        forbid = "如果只是因为亏损、卖飞或想把成本做回来，不允许加仓。"
    elif buy_point == "200 日线试错":
        hard = f"{label}：硬判断，这是 200 日线附近的趋势修复试错，不是确认买点。"
        trigger = "只有收盘继续在动态 200 日线上方，且题材/板块没有继续走弱，才算试错没有失败。"
        forbid = "若收盘跌回 200 日线下方，不能用长期叙事替代止损纪律。"
    elif buy_point in {"新开仓待验证", "5 日线先手待验证"}:
        hard = f"{label}：硬判断，这是待验证开仓，缺少市场和题材证据时不能升级为模式。"
        trigger = "补齐题材强度、放量主动性、均线位置和失败条件后，才允许评价买点质量。"
        forbid = "没有题材和量能证据时，不把价格回落当成买点。"
    elif buy_point == "退出动作":
        hard = f"{label}：硬判断，这是退出动作，复盘重点是退出是否来自计划，而不是事后涨跌。"
        trigger = "若退出依据是尾盘有效跌破或二次反弹失败，属于纪律执行；否则要复盘是否被盘中波动驱动。"
        forbid = "卖出后不能只因拉回或后悔而买回。"
    else:
        hard = f"{label}：硬判断，交易动作缺少上下文，买点质量无法判断。"
        trigger = "必须补充入场理由、题材归属、均线锚点和止损口径。"
        forbid = "证据不足时禁止把成交本身解释为模式。"

    stop_anchor = "第一锚点：买点触发条件失效；第二锚点：尾盘有效跌破 10 日线或对应均线；日内紧急条件：跌破日内均线且两次反弹无法站回。"
    if "200" in buy_point:
        stop_anchor = "第一锚点：动态 200 日线；第二锚点：收盘有效跌回 200 日线下方；日内紧急条件：跌破后两次反弹无法站回。"
    if risk_appetite in {"低", "无法判断"}:
        macro_constraint = "小美镜片约束：风险偏好低或无法验证时，仓位不扩大，买点必须更靠近止损锚点。"
    else:
        macro_constraint = f"小美镜片约束：当前风险偏好 {risk_appetite}，仍需防止科技叙事和风格切换造成过度自信。"

    return {
        "security": label,
        "buy_point_type": buy_point,
        "hard_judgment": hard,
        "trigger_condition": trigger,
        "stop_anchor": stop_anchor,
        "forbidden_condition": forbid,
        "macro_constraint": macro_constraint,
        "open_position_note": "仍有开放仓位，明日复盘必须继续跟踪。" if has_open else "当前导入数据内未显示开放仓位。",
        "market_regime": market_regime,
    }


def dongge_lens(stock_reviews, market_context):
    lines = [
        "先看环境，再看题材，再看个股，再看买点；现在市场背景未被可靠验证时，不允许用单票愿望替代盘面证据。",
        "均线只做风控工具，不做上涨预测；5 日线/10 日线/200 日线都必须同时写清买点和失败条件。",
    ]
    if any(review.get("buy_point_type") == "负 T 修复动作" for review in stock_reviews):
        lines.append("负 T 的本质是交易计划失控或环境确认不足，下一笔必须先问：这是节点买点，还是想把成本做回来。")
    lines.append("低开直接追只在强题材、强承接、分时主动、失败成本可控时成立；否则是后手追涨或情绪修复。")
    return lines


def bingbing_lens(macro_lenses):
    lenses = macro_lenses.get("macro_lenses", []) if isinstance(macro_lenses, dict) else []
    if not lenses:
        return ["宏观镜片缺失：无法判断外部利率、科技叙事、风格跷跷板和风险偏好。"]
    lines = []
    for item in lenses[:4]:
        lines.append(f"{item.get('lens', '宏观观察')}：{item.get('observation', '无法判断')} 教练约束：{item.get('coach_usage', item.get('教练用法', '不能直接推出单票买卖。'))}")
    lines.append("小美式约束：宏观判断只能决定仓位和频率，不替代个股止损；科技叙事越拥挤，越要防止把长期故事当短线承接。")
    return lines


def shared_conclusion(stock_reviews):
    if any(review.get("buy_point_type") == "负 T 修复动作" for review in stock_reviews):
        primary = "明日唯一纪律：先处理负 T 后的风险暴露，任何买回必须先写清触发条件和止损锚点。"
    else:
        primary = "明日唯一纪律：所有新交易先写买点类型、触发条件、止损锚点和最大亏损预算。"
    return [
        primary,
        "可以继续观察强题材和关键均线附近的试错机会，但没有量能和板块同步时不能扩大。",
        "候选池不足时，不硬编股票；先要求用户粘贴强势榜/候选池。"
    ]


def build(args):
    metrics = load_json(args.metrics, {})
    lifecycle = load_json(args.lifecycle, {})
    behavior = load_json(args.behavior, {})
    journal = load_json(args.journal, {})
    market_context = load_json(args.market_context, {})
    macro_lenses = load_json(args.macro_lenses, {})
    playbooks = load_json(args.playbooks, {})
    dongge_text = load_text(args.dongge_distillation)
    bingbing_text = load_text(args.bingbing_distillation)
    prior_context = "\n\n".join(load_text(path) for path in args.prior_context if Path(path).exists())
    combined_journal = "\n".join([
        json.dumps(journal, ensure_ascii=False),
        prior_context,
        dongge_text[:1200],
        bingbing_text[:1200],
    ])

    t_results = t_trade_map(lifecycle)
    stock_reviews = [
        stock_guidance(code, item, t_results.get(code), json.loads(json.dumps({"journal": journal, "prior_context": prior_context}, ensure_ascii=False)), market_context)
        for code, item in lifecycle.items()
    ]
    for review in stock_reviews:
        review["personal_rules"] = USER_RULES

    if any(review.get("buy_point_type") == "负 T 修复动作" for review in stock_reviews):
        today_verdict = "今日定性：有负 T 修复动作，核心问题是弱环境或证据不足时先买后卖，明日必须先收敛仓位和频率。"
    elif any(review.get("buy_point_type") == "200 日线试错" for review in stock_reviews):
        today_verdict = "今日定性：存在 200 日线试错仓，结果不能提前下结论，明日只按收盘有效跌破规则处理。"
    else:
        today_verdict = "今日定性：交易事实不足以证明模式有效，先补齐市场、题材、买点和止损证据。"

    return {
        "today_verdict": today_verdict,
        "dongge_lens": dongge_lens(stock_reviews, market_context),
        "bingbing_lens": bingbing_lens(macro_lenses),
        "stock_reviews": stock_reviews,
        "shared_conclusion": shared_conclusion(stock_reviews),
        "buy_point_taxonomy": [
            "可试错：强题材 + 明确均线锚点 + 失败成本可控。",
            "只观察：市场背景或题材证据不足。",
            "后手追涨：离止损锚点太远，或只因盘中拉升追入。",
            "禁止追：没有量能、题材或指数支持，只因怕卖飞/想扳回。",
            "等回踩：强题材未坏，但买点不在 5/10 日线或 200 日线附近。",
            "放弃：触发条件失效，或宏观/风格风险与题材不匹配。",
        ],
        "personal_rules": USER_RULES,
        "playbook_note": "少于 3 次类似证据的成功模式只能待验证；亏损或风险失控进入应避免。",
        "data_limits": [
            "缺少完整历史持仓时，已实现盈亏和持仓天数可能无法判断。",
            "缺少可靠市场行情时，主线、风格和风险偏好不能硬编。",
            "候选股研究必须来自联网行情或用户粘贴候选池。",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="生成懂哥/冰冰小美双镜片教练判断")
    parser.add_argument("--metrics", default="metrics.json")
    parser.add_argument("--lifecycle", default="trade_lifecycle.json")
    parser.add_argument("--behavior", default="behavior_flags.json")
    parser.add_argument("--journal", default="daily_journal.json")
    parser.add_argument("--market-context", default="market_context.json")
    parser.add_argument("--macro-lenses", default="local_state/macro_lenses.json")
    parser.add_argument("--playbooks", default="local_state/playbooks.json")
    parser.add_argument("--dongge-distillation", default="local_state/dongge_weekend_fantang_distillation.md")
    parser.add_argument("--bingbing-distillation", default="local_state/bingbingxiaomei_macro_distillation.md")
    parser.add_argument("--prior-context", action="append", default=[])
    parser.add_argument("-o", "--output", default="coach_lens.json")
    args = parser.parse_args()

    result = build(args)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
