#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path


OUTPUT_FIELDS = [
    "trade_date",
    "trade_time",
    "stock_code",
    "stock_name",
    "side",
    "quantity",
    "price",
    "amount",
]

ALIASES = {
    "trade_time": ["成交时间", "发生时间", "委托时间", "时间", "trade_time"],
    "stock_code": ["证券代码", "股票代码", "代码", "stock_code", "symbol"],
    "stock_name": ["证券名称", "股票名称", "名称", "stock_name", "security_name"],
    "side": ["委托方向", "买卖方向", "交易类别", "买卖类别", "交易方向", "操作", "side"],
    "quantity": ["成交数量", "成交股数", "数量", "股数", "quantity", "qty"],
    "price": ["成交价格", "成交均价", "成交价", "价格", "price"],
    "amount": ["成交金额", "成交额", "发生金额", "总发生金额", "amount"],
}

REQUIRED = ["stock_code", "stock_name", "side", "quantity", "price"]


def norm(value):
    return re.sub(r"[\s_\-:：/()（）]+", "", str(value or "").strip().lower())


def split_line(line):
    line = line.strip()
    if "\t" in line:
        return [cell.strip() for cell in line.split("\t") if cell.strip()]
    return [cell.strip() for cell in re.split(r"\s{2,}", line) if cell.strip()]


def normalize_side(value):
    text = str(value or "").strip().upper()
    if any(token in text for token in ("证券买入", "买入", "买", "BUY", "B")):
        return "BUY"
    if any(token in text for token in ("证券卖出", "卖出", "卖", "SELL", "S")):
        return "SELL"
    return text


def clean_number(value):
    text = str(value or "").strip().replace(",", "").replace("￥", "").replace("¥", "")
    if text in {"", "--", "-", "无"}:
        return ""
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return ""
    number = match.group(0)
    if negative and not number.startswith("-"):
        number = "-" + number
    return number


def find_header(lines):
    best_index = -1
    best_score = -1
    best_cells = []
    alias_tokens = {token for aliases in ALIASES.values() for token in aliases}
    for idx, line in enumerate(lines):
        cells = split_line(line)
        if len(cells) < 4:
            continue
        score = sum(1 for cell in cells if any(norm(alias) == norm(cell) or norm(alias) in norm(cell) for alias in alias_tokens))
        if score > best_score:
            best_index = idx
            best_score = score
            best_cells = cells
    if best_index < 0 or best_score < 3:
        raise SystemExit("无法识别表头：请粘贴包含证券代码、证券名称、买卖方向、成交数量、成交价格的表格文本。")
    return best_index, best_cells


def build_mapping(headers):
    normalized = {norm(header): i for i, header in enumerate(headers)}
    mapping = {}
    for canonical, aliases in ALIASES.items():
        for alias in [canonical] + aliases:
            key = norm(alias)
            if key in normalized:
                mapping[canonical] = normalized[key]
                break
        if canonical not in mapping:
            for i, header in enumerate(headers):
                h = norm(header)
                if any(norm(alias) in h or h in norm(alias) for alias in aliases):
                    mapping[canonical] = i
                    break
    missing = [field for field in REQUIRED if field not in mapping]
    if missing:
        raise SystemExit("字段不足，缺少：" + "、".join(missing))
    return mapping


def get(cells, mapping, field):
    idx = mapping.get(field)
    if idx is None or idx >= len(cells):
        return ""
    return cells[idx].strip()


def parse_lines(text, trade_date):
    lines = [line for line in text.splitlines() if line.strip()]
    header_index, headers = find_header(lines)
    mapping = build_mapping(headers)
    rows = []
    for line_no, line in enumerate(lines[header_index + 1 :], start=header_index + 2):
        cells = split_line(line)
        if len(cells) < len(headers):
            cells = cells + [""] * (len(headers) - len(cells))
        code = get(cells, mapping, "stock_code")
        side = normalize_side(get(cells, mapping, "side"))
        quantity = clean_number(get(cells, mapping, "quantity"))
        price = clean_number(get(cells, mapping, "price"))
        if not re.fullmatch(r"\d{6}", code or ""):
            continue
        if side not in {"BUY", "SELL"}:
            continue
        if not quantity or not price:
            continue
        amount = clean_number(get(cells, mapping, "amount"))
        if not amount:
            try:
                amount = f"{float(quantity) * float(price):.3f}"
            except ValueError:
                amount = ""
        rows.append(
            {
                "trade_date": trade_date,
                "trade_time": get(cells, mapping, "trade_time"),
                "stock_code": code,
                "stock_name": get(cells, mapping, "stock_name"),
                "side": side,
                "quantity": quantity,
                "price": price,
                "amount": amount,
                "_source_line": line_no,
            }
        )
    if not rows:
        raise SystemExit("没有解析到有效成交记录。")
    return rows, headers, mapping


def write_csv(rows, output):
    with open(output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OUTPUT_FIELDS})


def main():
    parser = argparse.ArgumentParser(description="从复制粘贴的券商成交表格文本中提取标准交易 CSV")
    parser.add_argument("input_text_file")
    parser.add_argument("-o", "--output", default="pasted_trades_extracted.csv")
    parser.add_argument("--trade-date", default=date.today().isoformat())
    parser.add_argument("--report", default="pasted_trades_parse_report.json")
    args = parser.parse_args()

    text = Path(args.input_text_file).read_text(encoding="utf-8")
    rows, headers, mapping = parse_lines(text, args.trade_date)
    write_csv(rows, args.output)
    report = {
        "status": "ok",
        "row_count": len(rows),
        "source_headers": headers,
        "mapped_fields": mapping,
        "output_fields": OUTPUT_FIELDS,
        "privacy_note": "原始粘贴文本仅应保存在 local_outputs/run_* 下，不提交 Git。",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
