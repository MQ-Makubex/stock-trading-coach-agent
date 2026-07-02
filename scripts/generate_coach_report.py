#!/usr/bin/env python3
import argparse
import html
import json
from pathlib import Path


def e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def load_json(path, default):
    if not path or not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def money(value):
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value if value is not None else "无法判断")


def amount_units(value, unit=50000):
    if not isinstance(value, (int, float)) or unit <= 0:
        return "无法判断"
    units = abs(value) / unit
    if units < 0.25:
        return "<0.5单位"
    rounded = round(units * 2) / 2
    if rounded.is_integer():
        return f"约{int(rounded)}单位"
    return f"约{rounded:.1f}单位"


def security_label(code, item):
    return f"{code} {item.get('security_name', '')}".strip()


def top_stock_lines(per_stock):
    if not per_stock:
        return ["无法判断"]
    rows = sorted(per_stock.items(), key=lambda kv: kv[1].get("realized_pnl", 0))
    lines = []
    for code, item in rows[:8]:
        lines.append(f"{security_label(code, item)}：已实现盈亏 {money(item.get('realized_pnl', 0))}")
    return lines or ["无法判断"]


def triggered_behavior(behavior):
    rows = []
    for name, item in behavior.get("behavior_flags", {}).items():
        if item.get("status") == "触发":
            rows.append(f"{name}（{item.get('severity', '无法判断')}）：{item.get('interpretation', '无法判断')}")
    return rows or ["未发现明显触发项；样本不足处仍需人工复核。"]


def article_lines(digest):
    checks = digest.get("narrative_pollution_checks", {})
    lines = [f"文章：{digest.get('title', '无法判断')}"]
    for name, label in [
        ("reinforces_position_bias", "是否强化已有持仓偏见"),
        ("induces_chasing", "是否诱发追涨"),
        ("has_verifiable_facts", "是否提供可验证事实"),
        ("is_emotional_comfort", "是否只是情绪安慰"),
        ("affected_today_trade", "是否影响当天交易动作"),
    ]:
        item = checks.get(name, {})
        answer = "是" if item.get("flag") else "否/无法判断"
        lines.append(f"{label}：{answer}。{item.get('reason', '')}")
    viewpoints = digest.get("viewpoints") or ["无法判断"]
    lines.append("观点摘要：" + "；".join(viewpoints[:3]))
    return lines


def macro_lens_lines(macro_lenses):
    lenses = macro_lenses.get("macro_lenses", []) if isinstance(macro_lenses, dict) else []
    source = macro_lenses.get("source", {}) if isinstance(macro_lenses, dict) else {}
    if not lenses:
        return ["无法判断：尚未更新宏观镜片，或网页抓取没有得到可用文章。"]
    lines = []
    if source.get("name"):
        lines.append(f"宏观镜片来源：{source.get('name')}，更新时间：{source.get('updated_at', '无法判断')}。")
    for item in lenses[:5]:
        risks = "、".join(item.get("risk_tags", [])[:3]) or "未见明显叙事风险"
        lines.append(f"{item.get('lens', '宏观观察')}：{item.get('observation', '无法判断')}（风险标签：{risks}）")
    return lines


def journal_text(journal):
    fields = ["trading_idea", "trade_intent", "market_view", "plan", "review_note", "mood"]
    return "\n".join(str(journal.get(field, "") or "") for field in fields)


def market_context_lines(journal, digest, macro_lenses, market_context=None):
    market_context = market_context or {}
    if market_context:
        lines = [
            f"智能体独立判断：{market_context.get('coach_view', '无法判断')}",
            f"市场状态：{market_context.get('market_regime', '无法判断')}；风格偏向：{market_context.get('style_bias', '无法判断')}；风险偏好：{market_context.get('risk_appetite', '无法判断')}",
            f"交易影响：{market_context.get('trading_implication', '无法判断')}",
        ]
        if not market_context.get("network_verified"):
            lines.insert(0, "市场背景未联网验证，不能把用户判断直接当成结论。")
        return lines
    text = journal_text(journal)
    lines = []
    if any(word in text for word in ["大盘", "指数", "上涨", "回调", "市场", "风格"]):
        lines.append(f"用户盘面观察：{text[:220]}")
    else:
        lines.append("用户未提供足够盘面观察，市场环境无法独立判断。")
    if any(word in text for word in ["看不懂", "不确定", "不知道"]):
        lines.append("教练判断：当前主观状态是不确定，优先降低交易频率和仓位冲动，而不是用宏观叙事替代规则。")
    if any(word in text for word in ["科技", "医药", "白马", "防守", "低位"]):
        lines.append("教练判断：已出现风格切换叙事，但只能作为环境观察，不能直接推出单票买卖动作。")
    checks = digest.get("narrative_pollution_checks", {}) if isinstance(digest, dict) else {}
    if checks.get("reinforces_position_bias", {}).get("flag"):
        lines.append("文章影响：存在强化已有持仓偏见的风险，明日计划必须回到止损、仓位和验证条件。")
    lenses = macro_lenses.get("macro_lenses", []) if isinstance(macro_lenses, dict) else []
    if lenses:
        first = lenses[0]
        lines.append(f"宏观镜片提醒：{first.get('lens', '宏观观察')} - {first.get('observation', '无法判断')}")
    return lines or ["无法判断"]


def market_correction_lines(market_context):
    if not market_context:
        return ["无法判断：未生成 market_context.json。"]
    user_view = market_context.get("user_view") or "无法判断"
    lines = [
        f"你的原始判断：{user_view}",
        f"一致性：{market_context.get('agreement', '无法判断')}",
        f"需要校正：{market_context.get('correction', '无法判断')}",
    ]
    if market_context.get("major_indices"):
        lines.append("指数证据：" + "；".join(market_context.get("major_indices", [])[:2]))
    if market_context.get("sector_strength"):
        lines.append("强势方向：" + "；".join(market_context.get("sector_strength", [])[:2]))
    if market_context.get("sector_weakness"):
        lines.append("弱势方向：" + "；".join(market_context.get("sector_weakness", [])[:2]))
    lines.append("教练要求：用户判断只能作为待校正输入，不能直接作为买卖理由。")
    return lines


def t_trade_lines(lifecycle):
    rows = []
    for code, item in lifecycle.items():
        events = item.get("events", [])
        by_date = {}
        for event in events:
            by_date.setdefault(event.get("date", ""), []).append(event)
        for day, day_events in by_date.items():
            buys = [e for e in day_events if e.get("side") == "BUY"]
            sells = [e for e in day_events if e.get("side") == "SELL"]
            if not buys or not sells:
                continue
            buy_qty = sum(float(e.get("quantity") or 0) for e in buys)
            sell_qty = sum(float(e.get("quantity") or 0) for e in sells)
            buy_amt = sum(float(e.get("amount") or 0) for e in buys)
            sell_amt = sum(float(e.get("amount") or 0) for e in sells)
            avg_buy = buy_amt / buy_qty if buy_qty else 0
            avg_sell = sell_amt / sell_qty if sell_qty else 0
            result = "正 T" if avg_sell > avg_buy else "负 T" if avg_sell < avg_buy else "无法判断"
            label = security_label(code, item)
            rows.append(
                f"{label} {day}：买入均价 {avg_buy:.3f}，卖出均价 {avg_sell:.3f}，标记为{result}。A 股 T+1 下，同日卖出通常对应原有可卖持仓，需结合底仓判断。"
            )
    return rows or ["未发现同日同票买卖；T 交易无法判断。"]


def coach_reason_lines(summary, behavior, journal, digest, macro_lenses):
    lines = []
    total_trades = summary.get("total_trades")
    if isinstance(total_trades, int):
        lines.append(f"交易事实依据：今日有 {total_trades} 笔成交，因此判断先看行为质量，再看结果盈亏。")
    pnl = summary.get("realized_pnl")
    if isinstance(pnl, (int, float)):
        direction = "为正" if pnl >= 0 else "为负"
        lines.append(f"结果依据：已实现盈亏{direction}，但单日结果不能证明模式可复制。")
    triggered = [
        name for name, item in behavior.get("behavior_flags", {}).items()
        if item.get("status") == "触发"
    ]
    if triggered:
        lines.append("行为依据：触发了 " + "、".join(triggered[:5]) + "，明日计划必须先处理这些风险。")
    else:
        lines.append("行为依据：未发现明显触发项，但样本不足时不能过度解读。")
    if journal.get("trading_idea") or journal.get("trade_intent"):
        lines.append("主观依据：你记录了交易想法，因此报告会检查“计划动作”和“临盘情绪”是否一致。")
    if macro_lenses.get("macro_lenses"):
        lines.append("宏观依据：宏观镜片只用于解释市场环境，不覆盖单票止损和仓位规则。")
    if digest.get("viewpoints"):
        lines.append("文章依据：文章观点只作为叙事污染检查输入，不作为买卖理由。")
    return lines or ["无法判断"]


def tomorrow_plan_lines(journal, behavior, playbooks, guard):
    text = journal_text(journal)
    lines = []
    if any(word in text for word in ["5日", "五日", "5 日"]):
        lines.append("条件计划：若价格回到 5 日均线附近，只允许按事前定义的试错仓执行，并先写清失败条件。")
    if any(word in text for word in ["10日", "十日", "10 日", "止损"]):
        lines.append("条件计划：若尾盘有效跌破 10 日线，或跌破日内均线且两次反弹无法站回，按规则处理风险。")
    if any(word in text for word in ["看不懂", "不确定", "不知道", "风格"]):
        lines.append("条件计划：若大盘和风格仍无法判断，明日先减少临盘切换，等待市场确认后再评估。")
    if any(word in text for word in ["做T", "做 T", "卖飞"]):
        lines.append("条件计划：做 T 只允许服务于既定仓位和风险规则，不能用来修正卖飞焦虑。")
    for question in guard.get("questions", [])[:2]:
        lines.append(f"买前反问：{question}")
    if not lines:
        lines.extend(discipline_lines(behavior, playbooks, guard))
    return (lines or ["无法判断"])[:3]


def qualitative(summary, behavior, journal, digest):
    flags = behavior.get("behavior_flags", {})
    if flags.get("疑似补仓摊薄幻觉", {}).get("status") == "触发":
        return "做 T 或补仓可能降低账面成本感受，但加仓风险上升。"
    if flags.get("盈利拿不住", {}).get("status") == "触发" and flags.get("亏损持有过久", {}).get("status") == "触发":
        return "盈利票兑现偏快，亏损票处理偏慢。"
    checks = digest.get("narrative_pollution_checks", {})
    if checks.get("reinforces_position_bias", {}).get("flag"):
        return "交易纪律需要继续观察，文章观点可能强化了持仓偏见。"
    pnl = summary.get("realized_pnl")
    if isinstance(pnl, (int, float)) and pnl >= 0:
        return "今日交易结果为正，但仍需验证模式是否可重复且风险可控。"
    if isinstance(pnl, (int, float)) and pnl < 0:
        return "今日交易结果为负，应优先复盘风险暴露和退出纪律。"
    if journal.get("trading_idea") or journal.get("trade_intent"):
        return "有交易想法记录，但交易数据不足，今日定性无法判断。"
    return "无法判断。"


def discipline_lines(behavior, playbooks, guard):
    lines = []
    for item in playbooks.get("playbooks", {}).get("应避免", [])[:3]:
        lines.append(f"避免重复：{item.get('trigger_condition', '无法判断')}，先写最大风险。")
    for question in guard.get("questions", [])[:3]:
        lines.append(question)
    if not lines:
        lines.append("样本不足，明日前先写清入场理由、退出方式和最大风险。")
    return lines


def reusable_mode(playbooks):
    copied = playbooks.get("playbooks", {}).get("可复制", [])
    pending = playbooks.get("playbooks", {}).get("待验证", [])
    if copied:
        return [f"已存在可复制模式：{item.get('trigger_condition', '无法判断')}（证据 {item.get('evidence_count', 0)} 次）" for item in copied[:5]]
    if pending:
        return [f"待验证模式：{item.get('trigger_condition', '无法判断')}（证据 {item.get('evidence_count', 0)} 次，未满 3 次不升级）" for item in pending[:5]]
    return ["无法判断"]


def primary_behavior_tag(behavior):
    triggered = [
        name for name, item in behavior.get("behavior_flags", {}).items()
        if item.get("status") == "触发"
    ]
    return triggered[0] if triggered else "无明显触发"


def build_report(metrics, lifecycle, behavior, journal, digest, playbooks, guard, macro_lenses=None, market_context=None):
    macro_lenses = macro_lenses or {}
    market_context = market_context or {}
    summary = metrics.get("summary", {})
    per_stock = metrics.get("per_stock_pnl", {})
    tomorrow_plan = tomorrow_plan_lines(journal, behavior, playbooks, guard)
    payload = {
        "scope": "只做历史复盘、行为诊断和风控训练；不荐股、不预测涨跌、不输出买卖建议。",
        "trade_date": journal.get("trade_date", "无法判断"),
        "market_context": market_context_lines(journal, digest, macro_lenses, market_context),
        "market_correction": market_correction_lines(market_context),
        "market_regime": market_context.get("market_regime", "无法判断"),
        "risk_appetite": market_context.get("risk_appetite", "无法判断"),
        "primary_behavior_tag": primary_behavior_tag(behavior),
        "today_facts": [
            f"总交易次数：{summary.get('total_trades', '无法判断')}",
            f"买入次数：{summary.get('buy_count', '无法判断')}",
            f"卖出次数：{summary.get('sell_count', '无法判断')}",
            f"已实现盈亏：{money(summary.get('realized_pnl'))}",
            f"总费用：{money(summary.get('total_fees'))}",
        ],
        "per_stock_review": top_stock_lines(per_stock),
        "t_trade_analysis": t_trade_lines(lifecycle),
        "today_intent": [
            f"交易想法：{journal.get('trading_idea') or '无法判断'}",
            f"交易意图：{journal.get('trade_intent') or '无法判断'}",
            f"情绪状态：{journal.get('mood') or '无法判断'}",
        ],
        "today_qualitative": qualitative(summary, behavior, journal, digest),
        "coach_reasoning": coach_reason_lines(summary, behavior, journal, digest, macro_lenses),
        "done_well": done_well(summary, behavior),
        "risk_behaviors": triggered_behavior(behavior),
        "article_influence": article_lines(digest),
        "macro_lens": macro_lens_lines(macro_lenses),
        "tomorrow_discipline": tomorrow_plan,
        "reusable_mode": reusable_mode(playbooks),
    }
    payload["xueqiu_post"] = build_xueqiu_post(payload, metrics, journal)
    return payload


def done_well(summary, behavior):
    lines = []
    if summary.get("sell_count", 0):
        lines.append("有卖出动作记录，可复盘退出质量。")
    if not any(item.get("status") == "触发" and item.get("severity") == "高" for item in behavior.get("behavior_flags", {}).values()):
        lines.append("未发现高严重度行为模式；仍需结合样本量复核。")
    return lines or ["无法判断"]


def markdown_section(title, lines):
    return "## " + title + "\n\n" + "\n".join(f"- {line}" for line in lines) + "\n"


def to_markdown(report):
    sections = [
        "# 每日交易教练报告\n",
        f"> {report['scope']}\n",
        markdown_section("市场情况判断", report["market_context"]),
        markdown_section("市场判断校正", report["market_correction"]),
        markdown_section("今日交易事实", report["today_facts"]),
        markdown_section("单票动作复盘", report["per_stock_review"]),
        markdown_section("T 交易分析", report["t_trade_analysis"]),
        markdown_section("今日交易意图", report["today_intent"]),
        markdown_section("今日定性", [report["today_qualitative"]]),
        markdown_section("教练判断理由", report["coach_reasoning"]),
        markdown_section("做得好的地方", report["done_well"]),
        markdown_section("风险行为", report["risk_behaviors"]),
        markdown_section("文章观点影响", report["article_influence"]),
        markdown_section("宏观镜片", report["macro_lens"]),
        markdown_section("明日交易纪律", report["tomorrow_discipline"]),
        markdown_section("是否形成可复用交易模式", report["reusable_mode"]),
        "## 雪球发布版草稿\n\n```markdown\n" + to_xueqiu_markdown(report) + "```\n",
    ]
    return "\n".join(sections)


def list_html(lines):
    return "<ul>" + "".join(f"<li>{e(line)}</li>" for line in lines) + "</ul>"


def badge(text, kind="neutral"):
    return f'<span class="badge {e(kind)}">{e(text)}</span>'


def section_html(anchor, title, conclusion, lines, tone="neutral"):
    return (
        f'<section id="{e(anchor)}" class="report-section {e(tone)}">'
        f"<h2>{e(title)}</h2>"
        f'<p class="section-lead">{e(conclusion)}</p>'
        f"{list_html(lines)}"
        "</section>"
    )


def to_html(report):
    nav = [
        ("facts", "今日交易事实"),
        ("market-correction", "市场判断校正"),
        ("single-stock", "单票复盘"),
        ("t-trade", "T 交易分析"),
        ("risk", "风险行为"),
        ("article", "文章观点影响"),
        ("playbook", "Playbook 更新"),
        ("discipline", "明日纪律"),
    ]
    facts_rows = "".join(
        f"<tr><td>{e(line.split('：', 1)[0])}</td><td>{e(line.split('：', 1)[1] if '：' in line else line)}</td></tr>"
        for line in report["today_facts"]
    )
    sections = "\n".join([
        section_html("facts", "今日交易事实", "先看成交事实，再讨论动机和市场叙事。", report["today_facts"]),
        section_html("market-correction", "市场判断校正", "市场环境由智能体独立判断，用户判断只作为待校正输入。", report["market_correction"], "warning"),
        section_html("single-stock", "单票复盘", "单票结果只代表历史成交，不证明模式已经可复制。", report["per_stock_review"]),
        section_html("t-trade", "T 交易分析", "正 T / 负 T 只用于复盘执行质量，不作为未来涨跌判断。", report["t_trade_analysis"], "danger" if any("负 T" in line for line in report["t_trade_analysis"]) else "neutral"),
        section_html("risk", "风险行为", "先处理最危险的行为标签，再谈下一笔机会。", report["risk_behaviors"], "danger"),
        section_html("article", "文章观点影响", "文章只能提供假设，不能替代盘面验证和止损规则。", report["article_influence"], "warning"),
        section_html("playbook", "Playbook 更新", "少于 3 次类似证据的模式只能待验证，不能升级为可复制。", report["reusable_mode"]),
        section_html("discipline", "明日纪律", "明日纪律最多 3 条，必须可执行、可验证、可复盘。", report["tomorrow_discipline"], "positive"),
    ])
    nav_html = "".join(f'<a href="#{e(anchor)}">{e(label)}</a>' for anchor, label in nav)
    tomorrow_unique = report["tomorrow_discipline"][0] if report["tomorrow_discipline"] else "无法判断"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>每日交易教练报告</title>
  <style>
    :root {{
      --ink:#111827; --muted:#667085; --line:#d7dee8; --paper:#f7f3ea; --panel:#fffdf8;
      --accent:#0f766e; --danger:#b42318; --danger-bg:#fff1f0; --ok:#067647; --ok-bg:#ecfdf3;
      --warn:#b54708; --warn-bg:#fffaeb; --dark:#111827;
    }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{
      margin:0; font-family:Geist,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      color:var(--ink); background:
        radial-gradient(circle at 8% 0%, rgba(15,118,110,.18), transparent 28%),
        radial-gradient(circle at 85% 10%, rgba(180,35,24,.12), transparent 26%),
        linear-gradient(180deg,#fbfaf6 0%,#f4efe5 100%);
      line-height:1.68;
    }}
    main {{ width:100%; max-width:1180px; margin:0 auto; padding:28px 18px 72px; }}
    .topnav {{
      position:sticky; top:14px; z-index:10; display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:center;
      width:min(980px, calc(100vw - 28px)); margin:0 auto 44px; padding:10px; border:1px solid rgba(17,24,39,.12);
      border-radius:999px; background:rgba(255,253,248,.86); backdrop-filter:blur(16px); box-shadow:0 18px 60px rgba(17,24,39,.08);
    }}
    .topnav a {{ color:#344054; text-decoration:none; font-size:13px; padding:7px 10px; border-radius:999px; }}
    .topnav a:hover {{ background:#111827; color:#fff; }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1.15fr) minmax(260px,.85fr); gap:34px; align-items:end; padding:42px 0 56px; }}
    h1 {{ max-width:1120px; margin:0; font-size:clamp(34px,5vw,72px); line-height:1.04; letter-spacing:0; }}
    .hero p {{ color:#475467; font-size:17px; max-width:620px; }}
    .hero-panel {{ border:1px solid rgba(17,24,39,.12); border-radius:22px; padding:22px; background:rgba(255,255,255,.72); box-shadow:0 24px 70px rgba(17,24,39,.10); }}
    .bento {{ display:grid; grid-template-columns:repeat(12,1fr); grid-auto-flow:dense; gap:14px; margin:14px 0 56px; }}
    .card {{ border:1px solid rgba(17,24,39,.10); border-radius:20px; background:var(--panel); padding:18px; min-height:132px; transition:transform .45s ease, box-shadow .45s ease; overflow:hidden; }}
    .card:hover {{ transform:translateY(-3px); box-shadow:0 20px 60px rgba(17,24,39,.10); }}
    .span-6 {{ grid-column:span 6; }} .span-3 {{ grid-column:span 3; }} .span-4 {{ grid-column:span 4; }} .span-8 {{ grid-column:span 8; }}
    .eyebrow {{ color:#667085; font-size:12px; margin:0 0 8px; }}
    .value {{ font-size:22px; line-height:1.25; margin:0; font-weight:760; }}
    .badge {{ display:inline-flex; align-items:center; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:700; border:1px solid rgba(17,24,39,.10); }}
    .badge.danger {{ color:var(--danger); background:var(--danger-bg); }} .badge.positive {{ color:var(--ok); background:var(--ok-bg); }}
    .badge.warning {{ color:var(--warn); background:var(--warn-bg); }} .badge.neutral {{ color:#344054; background:#f2f4f7; }}
    .layout {{ display:grid; grid-template-columns:240px minmax(0,1fr); gap:30px; align-items:start; }}
    .toc {{ position:sticky; top:92px; border-left:1px solid var(--line); padding-left:14px; }}
    .toc a {{ display:block; color:#475467; text-decoration:none; margin:0 0 10px; font-size:14px; }}
    .toc a:hover {{ color:#111827; }}
    .report-section {{ margin:0 0 26px; padding:24px; border:1px solid rgba(17,24,39,.10); border-radius:22px; background:rgba(255,253,248,.82); }}
    .report-section.danger {{ background:linear-gradient(180deg,#fff8f7,#fffdf8); border-color:#fecdca; }}
    .report-section.warning {{ background:linear-gradient(180deg,#fffbeb,#fffdf8); border-color:#fedf89; }}
    .report-section.positive {{ background:linear-gradient(180deg,#f0fdf4,#fffdf8); border-color:#abefc6; }}
    h2 {{ margin:0 0 8px; font-size:24px; line-height:1.2; letter-spacing:0; }}
    .section-lead {{ color:#344054; margin:0 0 14px; font-weight:650; }}
    ul {{ margin:0; padding-left:20px; }} li {{ margin:7px 0; }}
    table {{ width:100%; border-collapse:collapse; margin-top:12px; font-size:14px; }}
    td {{ padding:8px 10px; border-bottom:1px solid var(--line); }} td:last-child {{ text-align:right; font-variant-numeric:tabular-nums; }}
    .footer {{ margin-top:46px; padding:28px; background:#111827; color:#fff; border-radius:24px; }}
    .footer p {{ margin:0; color:#d0d5dd; }}
    @media (max-width:860px) {{
      main {{ padding:18px 12px 48px; }} .topnav {{ border-radius:18px; justify-content:flex-start; }}
      .hero, .layout {{ grid-template-columns:1fr; }} .toc {{ position:relative; top:auto; border-left:0; padding-left:0; display:grid; grid-template-columns:repeat(2,1fr); gap:8px; }}
      .bento {{ grid-template-columns:1fr; }} .span-6,.span-3,.span-4,.span-8 {{ grid-column:span 1; }}
    }}
  </style>
</head>
<body>
<main>
  <nav class="topnav">{nav_html}</nav>
  <header class="hero">
    <div>
      <h1>每日交易教练报告</h1>
      <p>{e(report['scope'])}</p>
      <p>{badge('交易日期 ' + str(report.get('trade_date', '无法判断')), 'neutral')} {badge('不荐股', 'warning')} {badge('不预测涨跌', 'warning')}</p>
    </div>
    <aside class="hero-panel">
      <p class="eyebrow">今日定性</p>
      <p class="value">{e(report['today_qualitative'])}</p>
    </aside>
  </header>
  <section class="bento">
    <article class="card span-6"><p class="eyebrow">今日定性</p><p class="value">{e(report['today_qualitative'])}</p></article>
    <article class="card span-3"><p class="eyebrow">市场环境</p><p class="value">{e(report.get('market_regime','无法判断'))}</p></article>
    <article class="card span-3"><p class="eyebrow">风险偏好</p><p class="value">{e(report.get('risk_appetite','无法判断'))}</p></article>
    <article class="card span-4"><p class="eyebrow">今日最关键行为标签</p><p class="value">{e(report.get('primary_behavior_tag','无法判断'))}</p></article>
    <article class="card span-8"><p class="eyebrow">明日唯一纪律</p><p class="value">{e(tomorrow_unique)}</p></article>
  </section>
  <div class="layout">
    <aside class="toc">{nav_html}</aside>
    <div>
      <section class="report-section">
        <h2>核心指标</h2>
        <p class="section-lead">成交事实压缩表，数字右对齐便于扫读。</p>
        <table>{facts_rows}</table>
      </section>
      {sections}
    </div>
  </div>
  <footer class="footer"><p>本报告只做历史复盘、行为诊断和风控训练。所有明日计划均为条件纪律，不构成投资建议。</p></footer>
</main>
</body>
</html>
"""


def stock_action_lines(metrics):
    per_stock = metrics.get("per_stock_pnl", {})
    if not per_stock:
        return ["单票动作：无法判断。"]
    lines = []
    for code, item in sorted(per_stock.items(), key=lambda kv: kv[1].get("trade_count", 0), reverse=True)[:8]:
        label = security_label(code, item)
        turnover_basis = abs(item.get("sell_revenue", 0) or 0) + abs(item.get("realized_cost", 0) or 0)
        unit_text = amount_units(turnover_basis)
        pnl = item.get("realized_pnl")
        result = "正贡献" if isinstance(pnl, (int, float)) and pnl > 0 else "负贡献" if isinstance(pnl, (int, float)) and pnl < 0 else "结果无法判断"
        lines.append(f"{label}：{item.get('trade_count', '无法判断')} 笔成交，成交规模{unit_text}，已实现结果为{result}。")
    return lines


def build_xueqiu_post(report, metrics, journal):
    date = report.get("trade_date") or "无法判断"
    lines = [
        f"# {date} 每日复盘与明日计划",
        "",
        "仅为个人交易复盘，不构成投资建议。",
        "",
        "## 今日市场观察",
    ]
    lines.extend(f"- {line}" for line in report.get("market_context", []))
    lines.extend(["", "## 今日操作复盘"])
    lines.extend(f"- {line}" for line in stock_action_lines(metrics))
    lines.extend(["", "## 今日定性"])
    lines.append(f"- {report.get('today_qualitative', '无法判断')}")
    lines.extend(["", "## 教练判断与理由"])
    lines.extend(f"- {line}" for line in report.get("coach_reasoning", []))
    lines.extend(["", "## 明日计划"])
    lines.extend(f"- {line}" for line in report.get("tomorrow_discipline", []))
    lines.extend(["", "## 复盘提醒"])
    plan = journal.get("plan") or "无法判断"
    lines.append(f"- 原计划/备注：{plan}")
    lines.append("- 明日所有动作只按条件触发，不做确定性预测。")
    return {
        "title": f"{date} 每日复盘与明日计划",
        "lines": lines,
        "storage_policy": "发布版不展示资金余额或账户信息；成交金额默认转换为单位表达。",
    }


def to_xueqiu_markdown(report):
    return "\n".join(report["xueqiu_post"]["lines"]) + "\n"


def to_xueqiu_html(report):
    body = []
    in_list = False
    for line in report["xueqiu_post"]["lines"]:
        if line.startswith("# "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h1>{e(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h2>{e(line[3:])}</h2>")
        elif line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{e(line[2:])}</li>")
        elif line.strip():
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<p>{e(line)}</p>")
    if in_list:
        body.append("</ul>")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(report["xueqiu_post"]["title"])}</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:#17202a; line-height:1.75; background:#fff; }}
    main {{ max-width:860px; margin:0 auto; padding:32px 20px 56px; }}
    h1 {{ font-size:30px; margin:0 0 14px; }}
    h2 {{ font-size:22px; margin:28px 0 10px; border-bottom:1px solid #d7dee8; padding-bottom:6px; }}
    li {{ margin:7px 0; }}
    p {{ color:#475467; }}
  </style>
</head>
<body><main>
{chr(10).join(body)}
</main></body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="生成每日交易教练报告")
    parser.add_argument("--metrics", default="metrics.json")
    parser.add_argument("--lifecycle", default="trade_lifecycle.json")
    parser.add_argument("--behavior", default="behavior_flags.json")
    parser.add_argument("--journal", default="daily_journal.json")
    parser.add_argument("--article", default="article_digest.json")
    parser.add_argument("--playbooks", default="local_state/playbooks.json")
    parser.add_argument("--guard", default="pre_trade_guard.json")
    parser.add_argument("--macro-lenses", default="local_state/macro_lenses.json")
    parser.add_argument("--market-context", default="market_context.json")
    parser.add_argument("--json-output", default="daily_coach_report.json")
    parser.add_argument("--markdown-output", default="daily_coach_report.md")
    parser.add_argument("--html-output", default="daily_coach_report.html")
    parser.add_argument("--xueqiu-markdown-output", default="daily_xueqiu_post.md")
    parser.add_argument("--xueqiu-html-output", default="daily_xueqiu_post.html")
    args = parser.parse_args()

    report = build_report(
        load_json(args.metrics, {}),
        load_json(args.lifecycle, {}),
        load_json(args.behavior, {}),
        load_json(args.journal, {}),
        load_json(args.article, {}),
        load_json(args.playbooks, {}),
        load_json(args.guard, {}),
        load_json(args.macro_lenses, {}),
        load_json(args.market_context, {}),
    )
    Path(args.json_output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.markdown_output).write_text(to_markdown(report), encoding="utf-8")
    Path(args.html_output).write_text(to_html(report), encoding="utf-8")
    Path(args.xueqiu_markdown_output).write_text(to_xueqiu_markdown(report), encoding="utf-8")
    Path(args.xueqiu_html_output).write_text(to_xueqiu_html(report), encoding="utf-8")
    print(f"wrote {args.json_output}")
    print(f"wrote {args.markdown_output}")
    print(f"wrote {args.html_output}")
    print(f"wrote {args.xueqiu_markdown_output}")
    print(f"wrote {args.xueqiu_html_output}")


if __name__ == "__main__":
    main()
