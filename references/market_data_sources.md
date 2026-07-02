# 免费行情接口优先级

本项目只使用公开行情快照做市场环境校验和研究预案，不荐股、不预测涨跌、不输出买卖建议。

## 优先级 1：新浪实时行情

- 用途：主要指数、用户成交股票的实时/收盘快照。
- 接口：`https://hq.sinajs.cn/list=sh000001,sz399001,sz399006,sh000688`
- 需要请求头：`Referer: https://finance.sina.com.cn/`
- 字段要点：名称、开盘、昨收、当前价、最高、最低、成交量、成交额、日期、时间。
- 当前状态：本地已验证可访问。

## 优先级 2：新浪全市场榜单

- 用途：A 股涨幅榜、成交额榜，用于生成研究候选池初筛。
- 接口：`https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData`
- 参数示例：`page=1&num=80&sort=changepercent&asc=0&node=hs_a`
- 关键字段：`code` 代码，`name` 名称，`trade` 最新价，`changepercent` 涨跌幅，`amount` 成交额，`turnoverratio` 换手率。
- 当前状态：本地已验证可访问。
- 限制：会包含新股首日等异常涨幅；候选池会过滤 `N` 开头新股和 ST，但仍需人工确认题材与技术位置。

## 优先级 3：腾讯实时行情备用源

- 用途：当新浪实时行情缺失时，补全指数和个股快照。
- 接口：`https://qt.gtimg.cn/q=sh000001,sz399001`
- 返回格式：GBK 文本，字段用 `~` 分隔。
- 当前状态：本地已验证可访问。

## 优先级 4：新浪日 K

- 用途：用户成交股票的日 K、MA5、MA10、MA20、MA60、MA200。
- 接口：`https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData`
- 参数示例：`symbol=sz301171&scale=240&datalen=260`
- 当前状态：本地已验证可访问。

## 优先级 5：东方财富 push2

- 用途：A 股涨幅榜、成交额榜、行业/概念板块快照。
- 接口：`/api/qt/clist/get`
- 关键字段：`f12` 代码，`f14` 名称，`f2` 最新价，`f3` 涨跌幅，`f6` 成交额，`f8` 换手率，`f10` 量比。
- 当前状态：当前网络下可能 RemoteDisconnected 或 502；脚本会多 host 尝试并降级。

## 优先级 6：东方财富 push2his

- 用途：个股日 K、MA5、MA10、MA20、MA60、MA200。
- 接口：`/api/qt/stock/kline/get`
- 关键字段：`f51` 日期，`f52` 开盘，`f53` 收盘，`f54` 最高，`f55` 最低，`f56` 成交量，`f57` 成交额。
- 当前状态：当前网络下可能 RemoteDisconnected 或 502；缺失时报告必须写明“未确认 200 日均线位置”。

## 优先级 7：AKShare 可选依赖

- 用途：作为后续增强源。
- 策略：不强制安装；`market_data_provider.py --include-akshare-status` 只检测是否可用。

## 兜底：用户粘贴候选池

当公开行情接口不可用或缺少足够证据时，要求用户粘贴强势榜、候选池或板块前排文本。

候选池格式示例：

```text
301421 波长光电 科技 放量 回踩200日线 止损200日线
```
