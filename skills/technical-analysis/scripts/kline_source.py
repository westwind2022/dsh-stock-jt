#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pandas", "requests"]
# ///
# -*- coding: utf-8 -*-
"""
kline_source.py - 投研取数 K 线源（KlineSource 多源抽象 · 主备可切）

数据源口径（最终定案）：
  - 主源 VipdocSource：本地 vipdoc .day/.lc5（不复权）→ 本地前复权 adjust_qfq_local。
  - 备源 TdxMcpSource：通达信云端 MCP tdx_kline（tqFlag=1 官方前复权）。
  - 主备按配置优先级尝试，高优先级不可用（初始化失败/数据缺失/周期不支持）自动降级。

自包含纪律：
  - 无盘符绝对路径（vipdoc 根 / MCP token / dll 路径全部由调用方经 config 传入）。
  - 无外部项目依赖（VipdocSource 二进制解析自包含，不复用其它模块工具）。
  - MCP 对接仅 requests + stdlib。

字段语义：KlinePacket 产出前复权 OHLCV，喂给 chanlun_api.CL_ImportKline。
"""

import json
import os
import struct
from collections import defaultdict
from datetime import datetime
from enum import IntEnum

import numpy as np
import pandas as pd
import requests


class DataPeriod(IntEnum):
    """数据周期枚举，对齐 DLL 侧 Enums.h DataPeriod"""
    NONE = 0
    M30 = 1      # 30分钟
    DAY = 2      # 日线
    WEEK = 3     # 周线
    MONTH = 4    # 月线


class KlinePacket:
    """K 线数据包（统一输出格式，OHLCV 平行数组）"""

    def __init__(self, stock_code, period, dates, opens, highs, lows,
                 closes, volumes):
        self.stock_code = stock_code
        self.period = period  # DataPeriod
        self.dates = dates
        self.opens = opens
        self.highs = highs
        self.lows = lows
        self.closes = closes
        self.volumes = volumes
        self.last_date = int(dates[-1]) if dates else None  # 末根日期（供新鲜度标注）

    def __len__(self):
        return len(self.dates)


def _market_dir(code):
    """按代码规则转 vipdoc 市场目录（sh/sz/bj）；板块指数 88 开头归 SH"""
    if code.startswith(("6", "9", "5")):
        return "sh"
    if code.startswith(("0", "3", "2")):
        return "sz"
    if code.startswith(("8", "4")):
        return "bj"
    return "sh"


# ============================================================
# KlineSource 抽象 + 实现
# ============================================================

class KlineSource:
    """K 线源策略接口，read 返回前复权 KlinePacket（或 None=不可用）"""

    name = "base"

    def read(self, stock_code, period, count) -> KlinePacket:
        raise NotImplementedError


class VipdocSource(KlineSource):
    """主源：本地 vipdoc .day/.lc5（不复权）+ 本地前复权。

    日/周/月读 .day（日线合成周/月），30min 读 .lc5 合成。
    前复权 = adjust_qfq_local（除权事件表经 xdxr_loader 注入，本地 gbbq 除权）。
    """

    name = "vipdoc"

    # 30 分钟桶边界（5 分钟 K 末刻分钟数；对齐通达信 30 分钟划分，午休不跨桶）
    _M30_BUCKETS = (600, 630, 660, 690, 810, 840, 870, 900)

    def __init__(self, vipdoc_root, xdxr_loader=None):
        if not vipdoc_root or not os.path.isdir(vipdoc_root):
            raise ValueError("vipdoc_root 不可达: {0}".format(vipdoc_root))
        self._root = vipdoc_root
        # xdxr_loader: callable(code) -> DataFrame[date,fenhong,peigu,peigujia,songzhuangu]
        self._xdxr_loader = xdxr_loader

    def _read_daily_raw(self, stock_code):
        """读单股日线（不复权），返回平行数组或 None"""
        mkt = _market_dir(stock_code)
        filepath = os.path.join(
            self._root, mkt, "lday", "{0}{1}.day".format(mkt, stock_code))
        if not os.path.exists(filepath):
            return None
        with open(filepath, "rb") as f:
            data = f.read()
        n = len(data) // 32
        dates, opens, highs, lows, closes, volumes = (
            [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n)
        for i in range(n):
            off = i * 32
            d, o, h, l, c, _a, v, _ = struct.unpack("IIIIIfII", data[off:off + 32])
            dates[i] = float(d)
            opens[i] = o / 100.0
            highs[i] = h / 100.0
            lows[i] = l / 100.0
            closes[i] = c / 100.0
            volumes[i] = float(v)
        return dates, opens, highs, lows, closes, volumes

    def _read_5min_raw(self, stock_code):
        """读单股五分钟线 .lc5（不复权），返回平行数组或 None"""
        mkt = _market_dir(stock_code)
        filepath = os.path.join(
            self._root, mkt, "fzline", "{0}{1}.lc5".format(mkt, stock_code))
        if not os.path.exists(filepath):
            return None
        with open(filepath, "rb") as f:
            data = f.read()
        n = len(data) // 32
        if n == 0:
            return None
        dates, times, opens, highs, lows, closes, volumes = (
            [0.0] * n, [0] * n, [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n)
        for i in range(n):
            off = i * 32
            raw_date, t, o, h, l, c, _amt, v = struct.unpack_from(
                "<HHffffII", data, off)
            yy = (raw_date // 2048) + 2004
            md = raw_date % 2048
            dates[i] = float(yy * 10000 + (md // 100) * 100 + md % 100)
            times[i] = t
            opens[i] = o
            highs[i] = h
            lows[i] = l
            closes[i] = c
            volumes[i] = float(v)
        return dates, times, opens, highs, lows, closes, volumes

    @staticmethod
    def _synthesize(daily, period, times=None):
        """日线→周/月、5min→30min 聚合。daily/五分钟 为平行数组元组。"""
        if period == DataPeriod.M30:
            return VipdocSource._synthesize_m30(daily, times)
        dates, opens, highs, lows, closes, volumes = daily
        groups = defaultdict(list)
        for i in range(len(dates)):
            d = int(dates[i])
            dt = datetime(d // 10000, (d // 100) % 100, d % 100)
            if period == DataPeriod.WEEK:
                iso = dt.isocalendar()
                key = (iso[0], iso[1])
            else:  # MONTH
                key = (d // 10000, (d // 100) % 100)
            groups[key].append(i)
        out_d, out_o, out_h, out_l, out_c, out_v = [], [], [], [], [], []
        for key in sorted(groups):
            idx = sorted(groups[key])
            out_d.append(dates[idx[-1]])
            out_o.append(opens[idx[0]])
            out_h.append(max(highs[i] for i in idx))
            out_l.append(min(lows[i] for i in idx))
            out_c.append(closes[idx[-1]])
            out_v.append(sum(volumes[i] for i in idx))
        return out_d, out_o, out_h, out_l, out_c, out_v

    @staticmethod
    def _synthesize_m30(five_min, times):
        """五分钟线→30分钟线合成（6 合 1，尾组不足按实际根数）"""
        dates, _, opens, highs, lows, closes, volumes = five_min
        buckets = defaultdict(list)
        for i in range(len(dates)):
            b = next((x for x in VipdocSource._M30_BUCKETS if times[i] <= x), None)
            if b is None:
                continue
            buckets[(dates[i], b)].append(i)
        out_d, out_o, out_h, out_l, out_c, out_v = [], [], [], [], [], []
        for (_d, _b), indices in sorted(buckets.items()):
            idx = sorted(indices)
            hhmm = (_b // 60) * 100 + _b % 60
            out_d.append(_d * 10000 + hhmm)  # 12 位 yyyymmddhhmm
            out_o.append(opens[idx[0]])
            out_h.append(max(highs[i] for i in idx))
            out_l.append(min(lows[i] for i in idx))
            out_c.append(closes[idx[-1]])
            out_v.append(sum(volumes[i] for i in idx))
        return out_d, out_o, out_h, out_l, out_c, out_v

    def read(self, stock_code, period, count):
        if period == DataPeriod.M30:
            five = self._read_5min_raw(stock_code)
            if not five or not five[0]:
                return None
            daily_raw = five
            times = five[1]
            arr = self._synthesize(daily_raw, DataPeriod.M30, times=times)
        elif period in (DataPeriod.WEEK, DataPeriod.MONTH):
            daily = self._read_daily_raw(stock_code)
            if not daily:
                return None
            arr = self._synthesize(daily, period)
        else:  # DAY
            daily = self._read_daily_raw(stock_code)
            if not daily:
                return None
            arr = daily
        dates, opens, highs, lows, closes, volumes = arr

        # 本地前复权（有除权事件表时）
        events = None
        if self._xdxr_loader is not None:
            events = self._xdxr_loader(stock_code)
        if events is not None and not (events is None or (hasattr(events, "empty") and events.empty)):
            adj = adjust_qfq_local(dates, opens, highs, lows, closes, volumes,
                                   period, events)
            if adj is not None:
                dates, opens, highs, lows, closes, volumes = adj

        # 截断到 count（倒序最新 count 根）
        if count and count > 0 and len(dates) > count:
            dates = dates[-count:]
            opens = opens[-count:]
            highs = highs[-count:]
            lows = lows[-count:]
            closes = closes[-count:]
            volumes = volumes[-count:]

        return KlinePacket(stock_code, period, dates, opens, highs, lows,
                           closes, volumes)


class TdxMcpSource(KlineSource):
    """备源：通达信云端 MCP tdx_kline（tqFlag=1 前复权）。

    复用 52 专题 06 原型 TdxMcpClient（requests + stdlib，标准 MCP streamable HTTP）。
    token 由调用方传 config，禁硬编码。
    """

    name = "tdxmcp"

    # period 映射：DataPeriod → tdx_kline period 字符串
    _PERIOD = {DataPeriod.DAY: "4", DataPeriod.WEEK: "5", DataPeriod.MONTH: "6",
               DataPeriod.M30: "2"}

    def __init__(self, base, token):
        self._base = base
        self._token = token
        self._session = None
        self._req = 0

    def _call(self, method, params):
        """统一 MCP 调用：post + 捕获 session + SSE 块解析（对齐 06 原型）。"""
        payload = {"jsonrpc": "2.0", "method": method, "params": params,
                   "id": self._req + 1}
        self._req += 1
        r = requests.post(self._base, headers={
            "Authorization": "Bearer {0}".format(self._token),
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": self._session or "",
        }, json=payload, timeout=30)
        sid = r.headers.get("MCP-Session-Id") or r.headers.get("mcp-session-id")
        if sid:
            self._session = sid
        ct = r.headers.get("content-type", "")
        if "text/event-stream" in ct:
            decoder = json.JSONDecoder()
            for block in r.text.split("\n\n"):  # SSE event 块
                if "data:" not in block:
                    continue
                lines = [ln[5:] for ln in block.split("\n")
                         if ln.startswith("data:")]
                blob = "\n".join(lines)
                if not blob.strip():
                    continue
                try:
                    return json.loads(blob)
                except Exception:
                    ki = blob.find('"structuredContent":')
                    if ki >= 0:
                        obj, _ = decoder.raw_decode(
                            blob, ki + len('"structuredContent":'))
                        return {"result": {"structuredContent": obj}}
            raise RuntimeError("SSE parse failed")
        return json.loads(r.text)

    def initialize(self):
        if self._token is None:
            raise ValueError("TDX_MCP_TOKEN 未配置")
        self._call("initialize", {"protocolVersion": "2025-03-26",
                                  "capabilities": {},
                                  "clientInfo": {"name": "deep_agent",
                                                 "version": "0.1"}})
        self._call("notifications/initialized", {})

    def read(self, stock_code, period, count):
        period_str = self._PERIOD.get(period)
        if period_str is None:
            return None
        try:
            if self._session is None:  # 懒初始化：首次调用先握手
                self.initialize()
            setcode = "1" if stock_code.startswith(("6", "9", "5")) else \
                      ("0" if stock_code.startswith(("0", "3", "2")) else "2")
            res = self._call("tools/call", {"name": "tdx_kline", "arguments": {
                "code": stock_code, "setcode": str(setcode),
                "period": str(period_str), "tqFlag": "1",
                "wantNum": str(count or 100)}})
        except Exception:
            return None
        sc = (res.get("result") or {}).get("structuredContent", {})
        rows = sc.get("Rows", [])
        if not rows:
            return None
        dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        for row in rows:
            dates.append(float(str(row.get("Data", ""))))
            opens.append(float(row.get("Open", 0)))
            highs.append(float(row.get("High", 0)))
            lows.append(float(row.get("Low", 0)))
            closes.append(float(row.get("Close", 0)))
            volumes.append(float(row.get("RawVolume", row.get("Volume", 0))))
        return KlinePacket(stock_code, period, dates, opens, highs, lows,
                           closes, volumes)


# ============================================================
# 本地前复权算法（gbbq 仅纳 cat=1 派息、未计含税，偏差 vs 官方 qfq ~0.28%，见 gbbq.py 口径）
# ============================================================

def adjust_qfq_local(dates, opens, highs, lows, closes, volumes, period,
                     events_df):
    """本地前复权：只改 OHLC，volume 不缩放。任意周期通用（分钟按日匹配）。

    events_df 列：date（datetime64）、fenhong、peigu、peigujia、songzhuangu（每10股）。
    返回平行数组元组，无事件时原样返回。
    """
    n = len(dates)
    if n == 0 or events_df is None or (hasattr(events_df, "empty") and events_df.empty):
        return dates, opens, highs, lows, closes, volumes

    close_arr = np.asarray(closes, dtype=float)
    open_arr = np.asarray(opens, dtype=float)
    high_arr = np.asarray(highs, dtype=float)
    low_arr = np.asarray(lows, dtype=float)

    # 日期归一化到"日"：日/周/月为 8 位 yyyymmdd，分钟线为 12 位 yyyymmddhhmm，
    # 事件侧恒为 8 位。此前统一 //10000 会把 8 位日期压成"年"，导致除权事件
    # 当年（含事件日之前）的 K 线漏乘因子（P0-①），并令 M30 前复权永不生效（P0-②）。
    def _to_day(v):
        iv = int(v)
        return iv // 10000 if iv >= 100000000 else iv
    day_arr = np.array([_to_day(d) for d in dates], dtype=np.int64)

    ev_days = np.array([_to_day(int(pd.Timestamp(t).strftime("%Y%m%d")))
                        for t in events_df["date"]], dtype=np.int64)
    pos = np.searchsorted(day_arr, ev_days, side="left")

    factor = np.ones(n)
    for k in range(len(ev_days) - 1, -1, -1):
        p = pos[k]
        if p <= 0:
            continue
        close_prev = close_arr[p - 1]
        if not np.isfinite(close_prev) or close_prev <= 0:
            continue
        fh = float(events_df.iloc[k].get("fenhong", 0) or 0)
        pg = float(events_df.iloc[k].get("peigu", 0) or 0)
        pgj = float(events_df.iloc[k].get("peigujia", 0) or 0)
        szg = float(events_df.iloc[k].get("songzhuangu", 0) or 0)
        denom = 10 + pg + szg
        if denom <= 0:
            continue
        preclose = (close_prev * 10 - fh + pg * pgj) / denom
        factor[:p] *= (preclose / close_prev)

    return (dates, list(open_arr * factor), list(high_arr * factor),
            list(low_arr * factor), list(close_arr * factor), volumes)


# ============================================================
# 除权事件表加载（本地 gbbq，最终口径：使用本地除权）
# ============================================================

def load_xdxr_events_gbbq(gbbq_index, code):
    """本地 gbbq 除权事件 → DataFrame[date,fenhong,peigu,peigujia,songzhuangu]。

    第一版只取 category=1 派息（fh=每10股派息）；category=2 配股 / 3 送转 / 5 股本基准
    待优化（07 文档：派息含税 + category=5 未纳入，与本专题偏差 ~0.28% 相关）。
    """
    rows = []
    for (_mkt, _c, date, category, fh, pg, pgj, szg) in gbbq_index.events_of(code):
        if category == 1 and fh and fh > 0:
            rows.append({
                "date": pd.Timestamp(year=date // 10000,
                                     month=(date // 100) % 100,
                                     day=date % 100),
                "fenhong": float(fh),
                "peigu": 0.0,
                "peigujia": 0.0,
                "songzhuangu": 0.0,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


# ============================================================
# 主备调度
# ============================================================

class SourceManager:
    """按优先级尝试多源，高优先级不可用自动降级到下一源。"""

    def __init__(self, sources):
        # sources: [(KlineSource, priority)] 按 priority 升序
        self._sources = sorted(sources, key=lambda x: x[1])

    def read(self, stock_code, period, count):
        used, last_err = None, None
        for src, _pri in self._sources:
            try:
                pkt = src.read(stock_code, period, count)
            except Exception as e:  # noqa: BLE001
                last_err = e
                pkt = None
            if pkt is not None and len(pkt) > 0:
                return pkt, src.name, None
            used = src.name
            last_err = last_err or ValueError("空数据")
        return None, used, last_err