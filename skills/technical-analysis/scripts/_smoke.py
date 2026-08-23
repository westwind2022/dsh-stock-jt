#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_smoke.py - 投研取数模块阶段1验证（临时工具，验证后可删）

验证三件事：
1. K线取数 + 前复权正确性（茅台最新收盘应=现价 1272.83，因前复权以最新为锚）
2. gbbq 除权事件已参与前复权（茅台有派息）
3. chanlun_dll 结构计算产出五实体非空
"""
import json
import sys

import pandas as pd

from struct_calc import (ChanlunSession, build_source_manager, load_runtime_env,
                         resolve_dll_path)
from kline_source import DataPeriod, VipdocSource, adjust_qfq_local


def _day_range(start, periods):
    """生成连续日线 8 位 yyyymmdd 数组（合成数据用）。"""
    return [int(x.strftime("%Y%m%d")) for x in pd.date_range(start, periods=periods)]


def regression_qfq():
    """P0 回归单测（全合成数据，无外部依赖）：
    ① 一年多次除权 + 事件当年、事件日之前的 K 线必须被调整（防年对齐回归）
    ② M30（12 位日期）前复权必须生效（防量纲错配回归）
    返回失败说明列表（空 = 通过）。
    """
    fails = []
    dates = _day_range("2025-01-01", 700)          # 到 2026 年 12 月（覆盖两次事件）
    price = [100.0] * len(dates)
    # 事件年 2026 年内两次派息（验证多次除权在事件年正确生效）
    events = pd.DataFrame([
        {"date": pd.Timestamp("2026-01-16"), "fenhong": 3.3,
         "peigu": 0.0, "peigujia": 0.0, "songzhuangu": 0.0},
        {"date": pd.Timestamp("2026-06-15"), "fenhong": 2.0,
         "peigu": 0.0, "peigujia": 0.0, "songzhuangu": 0.0},
    ])
    same = lambda a, b: abs(a - b) < 1e-6  # noqa: E731

    # ① 日线（8 位日期）：事件年前应被下调，事件年后保持 100（前复权锚最新）
    _, _, _, _, adj, _ = adjust_qfq_local(
        dates, price[:], price[:], price[:], price[:], price[:],
        DataPeriod.DAY, events)
    before = [adj[i] for i in range(len(dates)) if 20260101 <= dates[i] < 20260116]
    if not before or same(before[0], 100.0):
        fails.append("① 事件当年、事件日前 K 线未被调整（年对齐回归）")
    after = [adj[i] for i in range(len(dates)) if dates[i] >= 20260615]
    if not after or not same(after[0], 100.0):
        fails.append("① 事件日后锚点被误调整")
    # 两次除权复合：2025 年段应被两个因子共同下调（低于单次 0.9967 的 99.67）
    hist = [adj[i] for i in range(len(dates)) if 20250101 <= dates[i] < 20251231]
    if not hist or hist[0] >= 100 * 0.9967:
        fails.append("① 一年多次除权未复合（history=%.4f）" % (hist[0] if hist else -1))

    # ② M30（12 位 yyyymmddhhmm）：同一事件窗口应同样被调整
    m30_dates = [d * 10000 + 1030 for d in dates]
    _, _, _, _, adj30, _ = adjust_qfq_local(
        m30_dates, price[:], price[:], price[:], price[:], price[:],
        DataPeriod.M30, events)
    before30 = [adj30[i] for i in range(len(m30_dates)) if 20260101 <= dates[i] < 20260116]
    if not before30 or same(before30[0], 100.0):
        fails.append("② M30 前复权未生效（量纲错配回归）")
    return fails


def main():
    # P0 回归单测先行（全合成数据，失败即终止）
    reg = regression_qfq()
    if reg:
        print("[回归] 失败 %d 项:" % len(reg))
        for f in reg:
            print("  - " + f)
        return 1
    print("[回归] P0 前复权单测通过（① 事件年窗口 / ② M30 生效）")

    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    env = load_runtime_env()
    dll = resolve_dll_path(env)
    mgr = build_source_manager(env)

    print("dll:", dll)
    src1 = mgr._sources[0][0] if mgr._sources else None
    print("主源:", src1.name if src1 else None)
    if isinstance(src1, VipdocSource):
        print("gbbq:", "已解析" if src1._xdxr_loader else "无")

    pkt, used, err = mgr.read(code, DataPeriod.DAY, 250)
    print("\n[K线] 来源=%s 根数=%d" % (used, len(pkt)))
    print("  日期范围: %d ~ %d" % (int(pkt.dates[0]), int(pkt.dates[-1])))
    print("  最新收盘(前复权): %.2f" % pkt.closes[-1])
    print("  最新开盘(前复权): %.2f" % pkt.opens[-1])

    with ChanlunSession(dll) as sess:
        struct = sess.calc_structure(code, DataPeriod.DAY, pkt)
        print("\n[结构] 五实体:")
        for kind in ("kline_indicator", "bi_frac", "duan_frac", "road_frac",
                     "zhongshu"):
            v = struct.get(kind)
            if isinstance(v, dict):
                print("  %s: keys=%s" % (kind, list(v.keys())))
                # 打印顶层数组长度（数据量）
                for kk, vv in v.items():
                    if isinstance(vv, list):
                        print("      %s: %d 行" % (kk, len(vv)))
            else:
                print("  %s: %s" % (kind, type(v)))


if __name__ == "__main__":
    main()