#!/usr/bin/env python3
import argparse
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


SINA_INDEX_CODES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
}

SINA_REFERER = "https://finance.sina.com.cn/"
EASTMONEY_REFERER = "https://quote.eastmoney.com/"
TENCENT_REFERER = "https://stockapp.finance.qq.com/"

EASTMONEY_SPOT_HOSTS = [
    "https://push2.eastmoney.com",
    "http://push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "http://82.push2.eastmoney.com",
    "https://25.push2.eastmoney.com",
    "http://25.push2.eastmoney.com",
]

EASTMONEY_HIS_HOSTS = [
    "https://push2his.eastmoney.com",
    "http://push2his.eastmoney.com",
    "https://82.push2his.eastmoney.com",
    "http://82.push2his.eastmoney.com",
]


def request_text(url, encoding="utf-8", referer="", timeout=10):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 stock-trading-coach-agent/1.0",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Referer": referer,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(3 * 1024 * 1024)
        charset = resp.headers.get_content_charset() or encoding
    return raw.decode(charset, errors="replace")


def to_float(value):
    try:
        if value in (None, "", "-"):
            return None
        number = float(value)
        if math.isnan(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def to_int(value):
    try:
        if value in (None, "", "-"):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def pct_change(current, previous):
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / previous * 100, 2)


def sina_symbol(code):
    code = str(code or "").strip().lower()
    if not code:
        return ""
    if code.startswith(("sh", "sz")):
        return code
    if code.startswith(("6", "9")):
        return "sh" + code
    return "sz" + code


def eastmoney_secid(code):
    code = str(code or "").strip()
    if code.startswith("sh"):
        return "1." + code[2:]
    if code.startswith("sz"):
        return "0." + code[2:]
    if code.startswith(("6", "9")):
        return "1." + code
    return "0." + code


def parse_sina_response(text):
    rows = {}
    pattern = re.compile(r'var hq_str_([a-z0-9]+)="([^"]*)";')
    for symbol, payload in pattern.findall(text or ""):
        parts = payload.split(",")
        if len(parts) < 32 or not parts[0]:
            continue
        open_price = to_float(parts[1])
        prev_close = to_float(parts[2])
        current = to_float(parts[3])
        high = to_float(parts[4])
        low = to_float(parts[5])
        rows[symbol] = {
            "symbol": symbol,
            "code": symbol[2:] if symbol.startswith(("sh", "sz")) else symbol,
            "name": parts[0],
            "open": open_price,
            "prev_close": prev_close,
            "price": current,
            "high": high,
            "low": low,
            "change": round(current - prev_close, 3) if current is not None and prev_close is not None else None,
            "change_pct": pct_change(current, prev_close),
            "volume": to_int(parts[8]),
            "amount": to_float(parts[9]),
            "date": parts[30] if len(parts) > 30 else "",
            "time": parts[31] if len(parts) > 31 else "",
            "provider": "sina_hq",
        }
    return rows


def parse_tencent_response(text):
    rows = {}
    pattern = re.compile(r'v_([a-z0-9]+)="([^"]*)";')
    for symbol, payload in pattern.findall(text or ""):
        parts = payload.split("~")
        if len(parts) < 40 or not parts[1]:
            continue
        code = parts[2]
        current = to_float(parts[3])
        prev_close = to_float(parts[4])
        open_price = to_float(parts[5])
        high = to_float(parts[32])
        low = to_float(parts[33])
        amount = to_float(parts[37])
        if amount is not None and amount < 100000000:
            amount = amount * 10000
        rows[symbol] = {
            "symbol": symbol,
            "code": code,
            "name": parts[1],
            "open": open_price,
            "prev_close": prev_close,
            "price": current,
            "high": high,
            "low": low,
            "change": to_float(parts[30]),
            "change_pct": to_float(parts[31]),
            "volume": to_int(parts[6]),
            "amount": amount,
            "date": parts[29][:8] if len(parts[29]) >= 8 else "",
            "time": parts[29][8:] if len(parts[29]) > 8 else "",
            "provider": "tencent_qt",
        }
    return rows


def fetch_sina(symbols):
    symbols = [s for s in symbols if s]
    if not symbols:
        return {}, ""
    url = "https://hq.sinajs.cn/list=" + ",".join(symbols)
    text = request_text(url, encoding="gbk", referer=SINA_REFERER)
    return parse_sina_response(text), url


def fetch_tencent(symbols):
    symbols = [s for s in symbols if s]
    if not symbols:
        return {}, ""
    url = "https://qt.gtimg.cn/q=" + ",".join(symbols)
    text = request_text(url, encoding="gbk", referer=TENCENT_REFERER)
    return parse_tencent_response(text), url


def normalize_sina_market_row(row):
    return {
        "stock_code": str(row.get("code") or ""),
        "stock_name": row.get("name") or "",
        "symbol": row.get("symbol") or "",
        "price": to_float(row.get("trade")),
        "change_pct": to_float(row.get("changepercent")),
        "change": to_float(row.get("pricechange")),
        "volume": to_float(row.get("volume")),
        "amount": to_float(row.get("amount")),
        "high": to_float(row.get("high")),
        "low": to_float(row.get("low")),
        "open": to_float(row.get("open")),
        "prev_close": to_float(row.get("settlement")),
        "turnover": to_float(row.get("turnoverratio")),
        "pe_dynamic": to_float(row.get("per")),
        "pb": to_float(row.get("pb")),
        "provider": "sina_market_center",
    }


def fetch_sina_market_center(sort_field, limit):
    params = {
        "page": "1",
        "num": str(limit),
        "sort": sort_field,
        "asc": "0",
        "node": "hs_a",
        "symbol": "",
        "_s_r_a": "page",
    }
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?" + urllib.parse.urlencode(params)
    text = request_text(url, encoding="gbk", referer=SINA_REFERER, timeout=10)
    data = json.loads(text)
    rows = []
    for item in data if isinstance(data, list) else []:
        row = normalize_sina_market_row(item)
        if re.match(r"^[036]\d{5}$", row.get("stock_code", "")):
            rows.append(row)
    return rows, url


def eastmoney_json_from_hosts(hosts, path, params):
    errors = []
    query = urllib.parse.urlencode(params)
    for host in hosts:
        url = host + path + "?" + query
        try:
            text = request_text(url, referer=EASTMONEY_REFERER, timeout=8)
            if text.startswith("jQuery") and "(" in text:
                text = text[text.find("(") + 1:text.rfind(")")]
            return json.loads(text), url, errors
        except Exception as exc:  # noqa: BLE001 - record provider failure without leaking data.
            errors.append({"url": host + path, "error": f"{type(exc).__name__}: {exc}"})
    return None, "", errors


def normalize_eastmoney_stock(row):
    return {
        "stock_code": str(row.get("f12") or ""),
        "stock_name": row.get("f14") or "",
        "price": to_float(row.get("f2")),
        "change_pct": to_float(row.get("f3")),
        "change": to_float(row.get("f4")),
        "volume": to_float(row.get("f5")),
        "amount": to_float(row.get("f6")),
        "amplitude": to_float(row.get("f7")),
        "turnover": to_float(row.get("f8")),
        "volume_ratio": to_float(row.get("f10")),
        "high": to_float(row.get("f15")),
        "low": to_float(row.get("f16")),
        "open": to_float(row.get("f17")),
        "prev_close": to_float(row.get("f18")),
        "pe_dynamic": to_float(row.get("f9")),
        "pb": to_float(row.get("f23")),
        "provider": "eastmoney_push2",
    }


def normalize_eastmoney_sector(row):
    return {
        "sector_code": str(row.get("f12") or ""),
        "sector_name": row.get("f14") or "",
        "price": to_float(row.get("f2")),
        "change_pct": to_float(row.get("f3")),
        "main_inflow": to_float(row.get("f62")),
        "provider": "eastmoney_push2",
    }


def fetch_eastmoney_stocks(limit):
    fields = "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23"
    params = {
        "pn": "1",
        "pz": str(limit),
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": fields,
    }
    data, url, errors = eastmoney_json_from_hosts(EASTMONEY_SPOT_HOSTS, "/api/qt/clist/get", params)
    rows = []
    if data and data.get("data") and data["data"].get("diff"):
        rows = [normalize_eastmoney_stock(item) for item in data["data"]["diff"]]
    return rows, url, errors


def fetch_eastmoney_sectors(limit):
    fields = "f2,f3,f12,f14,f62,f184"
    outputs = []
    sources = []
    errors = []
    for fs, source_name in [("m:90+t:2", "concept_board"), ("m:90+t:1", "industry_board")]:
        params = {
            "pn": "1",
            "pz": str(limit),
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": fs,
            "fields": fields,
        }
        data, url, errs = eastmoney_json_from_hosts(EASTMONEY_SPOT_HOSTS, "/api/qt/clist/get", params)
        errors.extend(errs)
        if url:
            sources.append({"source": source_name, "url": url})
        if data and data.get("data") and data["data"].get("diff"):
            for item in data["data"]["diff"]:
                row = normalize_eastmoney_sector(item)
                row["board_type"] = source_name
                outputs.append(row)
    outputs.sort(key=lambda item: item.get("change_pct") if item.get("change_pct") is not None else -999, reverse=True)
    return outputs[:limit], sources, errors


def parse_kline(data):
    klines = []
    if not data or not data.get("data") or not data["data"].get("klines"):
        return klines
    for item in data["data"]["klines"]:
        parts = item.split(",")
        if len(parts) < 6:
            continue
        klines.append({
            "date": parts[0],
            "open": to_float(parts[1]),
            "close": to_float(parts[2]),
            "high": to_float(parts[3]),
            "low": to_float(parts[4]),
            "volume": to_float(parts[5]),
            "amount": to_float(parts[6]) if len(parts) > 6 else None,
            "amplitude": to_float(parts[7]) if len(parts) > 7 else None,
            "change_pct": to_float(parts[8]) if len(parts) > 8 else None,
            "change": to_float(parts[9]) if len(parts) > 9 else None,
            "turnover": to_float(parts[10]) if len(parts) > 10 else None,
        })
    return klines


def moving_average(values, window):
    values = [value for value in values if value is not None]
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 3)


def fetch_kline_for_code(code, limit=260):
    params = {
        "secid": eastmoney_secid(code),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": "20200101",
        "end": "20500101",
        "lmt": str(limit),
    }
    data, url, errors = eastmoney_json_from_hosts(EASTMONEY_HIS_HOSTS, "/api/qt/stock/kline/get", params)
    klines = parse_kline(data)
    closes = [item.get("close") for item in klines]
    summary = {
        "stock_code": str(code),
        "provider": "eastmoney_push2his",
        "source_url": url,
        "available": bool(klines),
        "rows": len(klines),
        "ma5": moving_average(closes, 5),
        "ma10": moving_average(closes, 10),
        "ma20": moving_average(closes, 20),
        "ma60": moving_average(closes, 60),
        "ma200": moving_average(closes, 200),
        "last_close": closes[-1] if closes else None,
        "last_date": klines[-1].get("date") if klines else "",
        "errors": errors if not klines else [],
    }
    return summary


def fetch_sina_kline_for_code(code, limit=260):
    symbol = sina_symbol(code)
    params = urllib.parse.urlencode({"symbol": symbol, "scale": "240", "datalen": str(limit)})
    url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?" + params
    try:
        text = request_text(url, encoding="utf-8", referer=SINA_REFERER, timeout=10)
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        return {
            "stock_code": str(code),
            "provider": "sina_kline",
            "source_url": url,
            "available": False,
            "rows": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
    klines = []
    for item in data if isinstance(data, list) else []:
        klines.append({
            "date": item.get("day", ""),
            "open": to_float(item.get("open")),
            "close": to_float(item.get("close")),
            "high": to_float(item.get("high")),
            "low": to_float(item.get("low")),
            "volume": to_float(item.get("volume")),
        })
    closes = [item.get("close") for item in klines]
    return {
        "stock_code": str(code),
        "provider": "sina_kline",
        "source_url": url,
        "available": bool(klines),
        "rows": len(klines),
        "ma5": moving_average(closes, 5),
        "ma10": moving_average(closes, 10),
        "ma20": moving_average(closes, 20),
        "ma60": moving_average(closes, 60),
        "ma200": moving_average(closes, 200),
        "last_close": closes[-1] if closes else None,
        "last_date": klines[-1].get("date") if klines else "",
        "errors": [] if klines else ["新浪 K 线未返回有效数据"],
    }


def optional_akshare_status():
    try:
        import akshare  # type: ignore  # noqa: F401
        return {"installed": True, "message": "akshare 已安装，可作为后续增强源。"}
    except Exception as exc:  # noqa: BLE001
        return {"installed": False, "message": f"akshare 未安装或不可用：{type(exc).__name__}"}


def suitable_for_research_candidate(item):
    name = str(item.get("stock_name") or item.get("name") or "")
    code = str(item.get("stock_code") or item.get("code") or "")
    if not re.match(r"^[036]\d{5}$", code):
        return False
    if name.startswith("N") or "ST" in name.upper():
        return False
    return True


def build_snapshot(args):
    provider_status = []
    requested_symbols = list(SINA_INDEX_CODES.keys())
    quote_codes = []
    if args.quotes:
        quote_codes = [code.strip() for code in re.split(r"[,，\s]+", args.quotes) if code.strip()]
        requested_symbols.extend(sina_symbol(code) for code in quote_codes)

    indices = []
    quotes = []
    try:
        sina_rows, sina_url = fetch_sina(requested_symbols)
        for symbol in SINA_INDEX_CODES:
            if symbol in sina_rows:
                indices.append(sina_rows[symbol])
        for code in quote_codes:
            symbol = sina_symbol(code)
            if symbol in sina_rows:
                quotes.append(sina_rows[symbol])
        provider_status.append({"provider": "sina_hq", "ok": bool(indices or quotes), "source_url": sina_url, "message": "已获取指数/个股快照" if indices or quotes else "新浪未返回有效数据"})
    except Exception as exc:  # noqa: BLE001
        provider_status.append({"provider": "sina_hq", "ok": False, "message": f"{type(exc).__name__}: {exc}"})

    missing_index_symbols = [symbol for symbol in SINA_INDEX_CODES if not any(item.get("symbol") == symbol for item in indices)]
    missing_quote_symbols = [sina_symbol(code) for code in quote_codes if not any(item.get("symbol") == sina_symbol(code) for item in quotes)]
    if missing_index_symbols or missing_quote_symbols:
        try:
            tencent_rows, tencent_url = fetch_tencent(missing_index_symbols + missing_quote_symbols)
            for symbol in missing_index_symbols:
                if symbol in tencent_rows:
                    indices.append(tencent_rows[symbol])
            for symbol in missing_quote_symbols:
                if symbol in tencent_rows:
                    quotes.append(tencent_rows[symbol])
            provider_status.append({"provider": "tencent_qt", "ok": bool(tencent_rows), "source_url": tencent_url, "message": "腾讯行情补全指数/个股快照" if tencent_rows else "腾讯未返回有效数据"})
        except Exception as exc:  # noqa: BLE001
            provider_status.append({"provider": "tencent_qt", "ok": False, "message": f"{type(exc).__name__}: {exc}"})

    stocks = []
    stock_source = ""
    try:
        sina_top_change, sina_change_url = fetch_sina_market_center("changepercent", args.limit)
        sina_top_amount, sina_amount_url = fetch_sina_market_center("amount", args.limit)
        seen = set()
        for item in sina_top_change + sina_top_amount:
            code = item.get("stock_code")
            if code in seen:
                continue
            seen.add(code)
            stocks.append(item)
        stock_source = sina_change_url
        provider_status.append({
            "provider": "sina_market_center",
            "ok": bool(stocks),
            "source_url": {"top_change": sina_change_url, "top_amount": sina_amount_url},
            "message": f"获取 {len(stocks)} 条新浪全市场股票快照" if stocks else "新浪全市场接口未返回有效数据",
        })
    except Exception as exc:  # noqa: BLE001
        provider_status.append({"provider": "sina_market_center", "ok": False, "message": f"{type(exc).__name__}: {exc}"})

    stock_source = ""
    sector_rows = []
    sector_sources = []
    if not args.skip_eastmoney:
        eastmoney_stocks, stock_source, stock_errors = fetch_eastmoney_stocks(args.limit)
        if eastmoney_stocks:
            seen = {item.get("stock_code") for item in stocks}
            for item in eastmoney_stocks:
                if item.get("stock_code") not in seen:
                    stocks.append(item)
                    seen.add(item.get("stock_code"))
        provider_status.append({
            "provider": "eastmoney_push2_stocks",
            "ok": bool(eastmoney_stocks),
            "source_url": stock_source,
            "message": f"获取 {len(eastmoney_stocks)} 条全市场股票快照" if eastmoney_stocks else "未获取到全市场股票快照",
            "errors": stock_errors[:6],
        })
        sector_rows, sector_sources, sector_errors = fetch_eastmoney_sectors(args.sector_limit)
        provider_status.append({
            "provider": "eastmoney_push2_sectors",
            "ok": bool(sector_rows),
            "source_url": sector_sources,
            "message": f"获取 {len(sector_rows)} 条板块快照" if sector_rows else "未获取到板块快照",
            "errors": sector_errors[:6],
        })

    kline = {}
    if quote_codes and not args.skip_kline:
        for code in quote_codes[: args.kline_limit]:
            sina_kline = fetch_sina_kline_for_code(code)
            if sina_kline.get("available"):
                kline[code] = sina_kline
            else:
                eastmoney_kline = fetch_kline_for_code(code)
                if eastmoney_kline.get("errors"):
                    eastmoney_kline["errors"] = sina_kline.get("errors", []) + eastmoney_kline.get("errors", [])
                kline[code] = eastmoney_kline
        provider_status.append({
            "provider": "sina_kline_or_eastmoney_push2his",
            "ok": any(item.get("available") for item in kline.values()),
            "message": f"尝试获取 {len(kline)} 只股票日 K 与均线",
        })

    if args.include_akshare_status:
        provider_status.append({"provider": "akshare_optional", **optional_akshare_status()})

    research_stocks = [item for item in stocks if suitable_for_research_candidate(item)]
    top_change = sorted(research_stocks, key=lambda item: item.get("change_pct") if item.get("change_pct") is not None else -999, reverse=True)[:20]
    top_amount = sorted(research_stocks, key=lambda item: item.get("amount") if item.get("amount") is not None else -1, reverse=True)[:20]
    sector_strength = sector_rows[:12]
    sector_weakness = sorted(sector_rows, key=lambda item: item.get("change_pct") if item.get("change_pct") is not None else 999)[:12]

    return {
        "as_of_date": date.today().isoformat(),
        "generated_at_epoch": int(time.time()),
        "source_priority": [
            "sina_hq: 指数与个股实时快照，当前环境已验证可用",
            "sina_market_center: 全市场涨幅榜、成交额榜，当前环境已验证可用",
            "tencent_qt: 指数与个股实时快照备用源",
            "sina_kline: 个股日 K 与 MA5/MA10/MA200，失败时用 eastmoney_push2his 降级",
            "eastmoney_push2: 全市场涨幅榜、成交额榜、板块榜，失败时降级",
            "eastmoney_push2his: 个股日 K 与 MA5/MA10/MA200 备用源",
            "akshare: 可选本地依赖，不强制安装",
            "manual_candidate_pool: 用户粘贴候选池兜底",
        ],
        "provider_status": provider_status,
        "network_verified": any(item.get("ok") for item in provider_status if item.get("provider") in {"sina_hq", "tencent_qt", "sina_market_center", "eastmoney_push2_stocks", "eastmoney_push2_sectors"}),
        "indices": indices,
        "quotes": quotes,
        "stocks": stocks,
        "top_change": top_change,
        "top_amount": top_amount,
        "sector_strength": sector_strength,
        "sector_weakness": sector_weakness,
        "kline": kline,
        "privacy_policy": "只保存公开行情快照，不保存用户身份或账户信息。",
        "boundary": "行情快照只用于市场环境与研究预案，不构成荐股、预测或买卖建议。",
    }


def main():
    parser = argparse.ArgumentParser(description="免费行情接口聚合：新浪优先，东方财富增强，AKShare 可选。")
    parser.add_argument("-o", "--output", default="market_data_snapshot.json")
    parser.add_argument("--quotes", default="", help="逗号分隔的股票代码，用于获取个股快照和均线。")
    parser.add_argument("--limit", type=int, default=80, help="东方财富全市场股票快照数量。")
    parser.add_argument("--sector-limit", type=int, default=50, help="东方财富板块快照数量。")
    parser.add_argument("--kline-limit", type=int, default=20, help="最多为多少只 quotes 拉取 K 线。")
    parser.add_argument("--skip-eastmoney", action="store_true")
    parser.add_argument("--skip-kline", action="store_true")
    parser.add_argument("--include-akshare-status", action="store_true")
    args = parser.parse_args()

    snapshot = build_snapshot(args)
    Path(args.output).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = [item.get("provider") for item in snapshot.get("provider_status", []) if item.get("ok")]
    print(f"wrote {args.output}; ok providers: {', '.join(ok) if ok else 'none'}")


if __name__ == "__main__":
    main()
