#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pandas", "requests"]
# ///
# -*- coding: utf-8 -*-
"""
struct_calc.py - 投研取数入口：K 线源组装 + chanlun_dll 结构计算

链路：load config → resolve dll/vipdoc 路径 → 组装主备 KlineSource → 取前复权 K 线
      → CL_ImportKline（导入即算好）→ CL_ExportStruct ×5 → 结构 JSON。

自包含纪律：dll/vipdoc/MCP token 全部经 config（runtime.env）/环境变量，禁硬编码盘符与密钥。

用法：
    python struct_calc.py 600519 day 250        # 单标日线结构
    python struct_calc.py 600519 month 200      # 月线
    python struct_calc.py 600519 m30 100        # 30分钟

config（{实例根}/config/runtime.env，KEY=VALUE）；最小只需 TDX_ROOT：
    TDX_ROOT          # 通达信根目录（推导 vipdoc=TDX_ROOT/vipdoc、gbbq=TDX_ROOT/T0002/hq_cache/gbbq）
    CHANLUN_DLL_PATH  # chanlun64_jt.dll 独立配置（未设置则默认：部署 T0002/dlls + 开发 chanlun_dll/out/build）
    以下为可选覆盖（非标准布局时）：
    VIPDOC_ROOT       # vipdoc 根目录显式覆盖
    GBBQ_PATH         # gbbq 除权库显式覆盖
    TDX_MCP_BASE      # MCP base url（默认 txmcp.tdx.com.cn:3001/clawmcp）
    TDX_MCP_TOKEN     # 备源 MCP token（机密）
    KLINE_SOURCES     # 主备顺序（默认 "vipdoc,tdxmcp"）
"""

import json
import os
import sys
from contextlib import contextmanager
from datetime import date

from chanlun_api import ChanlunAPI
from gbbq import GbbqIndex
from kline_source import (DataPeriod, SourceManager, VipdocSource, TdxMcpSource,
                          load_xdxr_events_gbbq)

# CL_ExportStruct 导出的五类实体（align_marker 已废弃）
_ENTITY_KINDS = ("kline_indicator", "bi_frac", "duan_frac", "road_frac", "zhongshu")

_PERIOD_MAP = {"m30": DataPeriod.M30, "day": DataPeriod.DAY,
               "week": DataPeriod.WEEK, "month": DataPeriod.MONTH}

MCP_BASE_DEFAULT = "https://txmcp.tdx.com.cn:3001/clawmcp"


# ============================================================
# 配置加载与路径解析（config 优先，相对兜底，禁硬编码盘符）
# ============================================================

def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def instance_root():
    """实例根 = scripts 上 3 层（scripts → technical-analysis → skills → 插件包根）"""
    return os.path.dirname(os.path.dirname(os.path.dirname(script_dir())))


def load_runtime_env(root=None):
    """读环境变量 + config/runtime.env（KEY=VALUE），环境变量优先。

    插件部署形态：TA_RUNTIME_ENV 显式指向
    runtime.env 文件（部署机可把配置放任意位置），优先于默认
    {instance_root}/config/runtime.env；未设置时用默认查找。
    """
    root = root or instance_root()
    env = dict(os.environ)
    explicit = env.get("TA_RUNTIME_ENV", "")
    env_file = explicit if explicit else os.path.join(root, "config", "runtime.env")
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if "#" in v:  # 行内注释剥离（"value   # comment" → "value"）
                    v = v.split("#", 1)[0].strip()
                env.setdefault(k, v)
    return env


def _tdx_root(env):
    """通达信根目录（expanduser），未配置返回 None。"""
    p = env.get("TDX_ROOT", "")
    return os.path.expanduser(p) if p else None


def resolve_dll_path(env, root=None):
    """chanlun64_jt.dll 解析（优先级）：① 插件包 vendor/chanlun64_jt.dll（发布自带）→
    ② CHANLUN_DLL_PATH 显式 → ③ 默认推导（开发 out/build + 部署 T0002/dlls）。

    chanlun64_jt.dll 是 chanlun_dll 编译产物，不从 TDX_ROOT 推导。插件发布形态随包 vendor/ 分发，优先命中即无需任何配置。
    """
    # ① 插件包 vendor（root 默认 = instance_root() = 插件包根；vendor 与 skills/ 同级）
    root = root or instance_root()
    bundled = os.path.join(root, "vendor", "chanlun64_jt.dll")
    if os.path.exists(bundled):
        return bundled
    # ② 显式配置
    p = env.get("CHANLUN_DLL_PATH", "")
    if p:
        p = os.path.expanduser(p)
        if os.path.exists(p):
            return p
    # ③ 默认推导
    ws = os.path.dirname(root)  # workspace 根
    candidates = [
        os.path.join(ws, "chanlun_dll", "out", "build", "x64-Release", "chanlun64_jt.dll"),
        os.path.join(ws, "chanlun_dll", "out", "build", "x64-Debug", "chanlun64_jt.dll"),
        os.path.join(root, "T0002", "dlls", "chanlun64_jt.dll"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError("chanlun64_jt.dll 未找到，尝试路径: {0}".format(candidates))


def resolve_vipdoc_root(env, root=None):
    """vipdoc 根：config 显式优先，TDX_ROOT/vipdoc 推导，相对兜底。"""
    p = env.get("VIPDOC_ROOT", "")
    if p:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            return p
    tdx = _tdx_root(env)
    if tdx:
        cand = os.path.join(tdx, "vipdoc")
        if os.path.isdir(cand):
            return cand
    root = root or instance_root()
    ws = os.path.dirname(root)
    for c in [os.path.join(ws, "vipdoc"), os.path.join(root, "vipdoc")]:
        if os.path.isdir(c):
            return c
    return None  # 无 vipdoc → 主源不可用，走备源 MCP


def resolve_gbbq_path(env, vipdoc_root=None):
    """gbbq 除权库：config 显式优先，TDX_ROOT/T0002/hq_cache/gbbq 推导，vipdoc 同级兜底。"""
    p = env.get("GBBQ_PATH", "")
    if p:
        p = os.path.expanduser(p)
        if os.path.exists(p):
            return p
    tdx = _tdx_root(env)
    if tdx:
        cand = os.path.join(tdx, "T0002", "hq_cache", "gbbq")
        if os.path.exists(cand):
            return cand
    if vipdoc_root:
        cand = os.path.join(os.path.dirname(vipdoc_root), "T0002", "hq_cache", "gbbq")
        if os.path.exists(cand):
            return cand
    return None


# ============================================================
# 结构计算封装（长驻会话 + 缓存复用）
# ============================================================

class ChanlunSession:
    """长驻会话：持 dll 实例，跨多次 calc_structure 复用 record 缓存。

    会话收尾调用 close()（CL_Cleanup 全清，含缓存），会话内不释放单股 record。
    """

    def __init__(self, dll_path, config_json="{}"):
        self.api = ChanlunAPI(dll_path)
        rc = self.api.init(config_json)
        if rc != 0:
            raise RuntimeError("CL_Init 失败: rc={0}".format(rc))

    def calc_structure(self, stock_code, period, packet):
        """导入单标 K 线 → 导出五类实体结构 JSON。period 为 DataPeriod。"""
        handle = self.api.import_kline(
            stock_code, int(period), packet.dates, packet.opens,
            packet.highs, packet.lows, packet.closes, packet.volumes)
        if handle is None or handle <= 0:
            raise RuntimeError("CL_ImportKline 失败: handle={0}".format(handle))
        result = {}
        for kind in _ENTITY_KINDS:
            rc, data = self.api.export_struct(handle, kind)
            result[kind] = data if rc == 0 else None
        return result

    def close(self):
        self.api.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@contextmanager
def chanlun_session(dll_path, config_json="{}"):
    s = ChanlunSession(dll_path, config_json)
    try:
        yield s
    finally:
        s.close()


# ============================================================
# K 线源组装（主备按 config 可切）
# ============================================================

def build_source_manager(env, root=None):
    """按 config 组装主/备 K 线源。sources: vipdoc,tdxmcp（逗号分隔，顺序即优先级）。"""
    root = root or instance_root()
    order = env.get("KLINE_SOURCES", "vipdoc,tdxmcp").split(",")
    vipdoc_root = resolve_vipdoc_root(env, root)

    # 本地 gbbq 除权（最终口径：使用本地除权）
    gbbq_path = resolve_gbbq_path(env, vipdoc_root)
    gbbq_index = GbbqIndex(gbbq_path) if gbbq_path else None
    xdxr_loader = (lambda code: load_xdxr_events_gbbq(gbbq_index, code)) \
        if gbbq_index is not None else None

    srcs = []
    skipped = []  # 因缺配置被跳过的源（P3：备源缺失不静默，随 mgr.skipped 披露）
    for name in [s.strip() for s in order if s.strip()]:
        if name == "vipdoc" and vipdoc_root:
            srcs.append((VipdocSource(vipdoc_root, xdxr_loader), 1))
        elif name == "vipdoc":
            skipped.append("vipdoc(未找到 vipdoc 根目录)")
        elif name == "tdxmcp":
            token = env.get("TDX_MCP_TOKEN", "")
            base = env.get("TDX_MCP_BASE", MCP_BASE_DEFAULT)
            if token:
                srcs.append((TdxMcpSource(base, token), 2))
            else:
                skipped.append("tdxmcp(未配置 TDX_MCP_TOKEN)")
    if not srcs:
        raise RuntimeError("无可用 K 线源（vipdoc 无数据且 MCP token 未配置）")
    mgr = SourceManager(srcs)
    mgr.skipped = skipped
    return mgr


# ============================================================
# 顶层入口
# ============================================================

def _stale_days(last_date):
    """末根日期（8 位 yyyymmdd 或 12 位 yyyymmddhhmm）距今天数（日历日，负值截 0）。"""
    if not last_date:
        return None
    iv = int(last_date)
    if iv >= 100000000:
        iv = iv // 10000
    try:
        last = date(iv // 10000, (iv // 100) % 100, iv % 100)
    except ValueError:
        return None
    return max(0, (date.today() - last).days)


def read_structure(session, source_mgr, stock_code, period, count):
    """取前复权 K 线 → 算结构。返回 (structure_dict, source_name, degrade_info, meta)。

    degrade_info：None 或 "vipdoc空数据→tdxmcp" 等降级描述（供简报 §6 披露）。
    meta：{"last_date": 末根日期, "stale_days": 陈旧天数}，供新鲜度披露（P1-③）。
    """
    pkt, used_src, err = source_mgr.read(stock_code, period, count)
    if pkt is None:
        # 主备全不可用
        names = [s.name for s, _ in source_mgr._sources]
        return None, used_src, "来源[{0}]均不可用: {1}".format(",".join(names), err), None
    degrade = "降级[{0}]".format(used_src) if _was_degraded(source_mgr, used_src) else None
    struct = session.calc_structure(stock_code, period, pkt)
    meta = {"last_date": pkt.last_date, "stale_days": _stale_days(pkt.last_date)}
    return struct, used_src, degrade, meta


def _was_degraded(source_mgr, used_name):
    """是否非首选源（用于降级披露）。"""
    first = source_mgr._sources[0][0].name if source_mgr._sources else None
    return first != used_name


# ============================================================
# CLI（阶段 1 验证用）
# ============================================================

def _fix_stdout_utf8():
    """Windows 控制台中文乱码加固：stdout/stderr 固定 UTF-8（P1-④）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main():
    _fix_stdout_utf8()
    import argparse
    ap = argparse.ArgumentParser(
        description="投研取数：取前复权 K 线 → chanlun_dll 五实体结构计算")
    ap.add_argument("code", nargs="?", default="600519",
                    help="股票代码（默认 600519）")
    ap.add_argument("period", nargs="?", default="day",
                    choices=list(_PERIOD_MAP),
                    help="周期 day/week/month/m30（默认 day）")
    ap.add_argument("count", nargs="?", default=250, type=int,
                    help="取最近 N 根（默认 250）")
    args = ap.parse_args()
    code, period_name, count = args.code, args.period, args.count
    period = _PERIOD_MAP[period_name]

    env = load_runtime_env()
    dll = resolve_dll_path(env)
    mgr = build_source_manager(env)

    print("dll: {0}".format(dll))
    skipped = getattr(mgr, "skipped", [])
    if skipped:
        print("备源跳过: {0}".format("；".join(skipped)))
    with chanlun_session(dll) as sess:
        struct, used, degrade, meta = read_structure(sess, mgr, code, period, count)
        if struct is None:
            print("取数失败: {0}".format(degrade))
            return 1
        print("来源: {0}；{1}".format(used, degrade or "正常"))
        if meta and meta["stale_days"] is not None:
            flag = "（陈旧，请检查数据更新）" if meta["stale_days"] >= 7 else ""
            print("数据: 末根 {0}，距今 {1} 天{2}".format(
                meta["last_date"], meta["stale_days"], flag))
        for kind in _ENTITY_KINDS:
            v = struct.get(kind)
            n = len(v) if isinstance(v, (list, dict)) else "?"
            print("  {0}: {1}".format(kind, n))


if __name__ == "__main__":
    sys.exit(main())