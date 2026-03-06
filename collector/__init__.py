"""
AI Signal Collector — 多层内容采集系统 (v2: channels 架构)

架构三层：
  Layer 1 - 信源管理 (SourceManager): 统一管理 213+ 信源，按需筛选
  Layer 2 - 采集引擎 (FetcherEngine): 14 个可插拔渠道 (channels/)，每个渠道多工具降级
  Layer 3 - 任务调度 (TaskProfile): 不同目的调用不同策略

可插拔渠道 (channels/):
  web / rss / twitter / youtube / github / bilibili / reddit
  xiaohongshu / douyin / linkedin / bosszp / exa_search / api / browser

外部服务：
  ClawFeed (http://127.0.0.1:8767): AI新闻摘要，通过 ClawFeedHelper 调用
"""
