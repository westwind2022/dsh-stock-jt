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

from struct_calc import (ChanlunSession, build_source_manager, load_runtime_env,
                         resolve_dll_path)
from kline_source import DataPeriod, VipdocSource


def main():
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