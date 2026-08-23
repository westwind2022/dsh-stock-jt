#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# -*- coding: utf-8 -*-
"""
chanlun_api.py - CL_* DLL ctypes 绑定（独立部署用）

薄封装，只做类型转换，不含业务逻辑。
dll_path 由调用方传入（struct_calc.py 的 resolve_dll_path 解析），本模块零第三方依赖、
零盘符硬编码、零外部依赖。

线程安全契约（接口说明 §2.7）：
  CL_ImportKline 不支持同股并发导入（每股单线程独占），CL_CalcStructure/CL_CalcFeature/
  CL_ExportStruct/CL_ReleaseRecord 均有记录锁串行化。单标的串行调用即可，无需额外加锁。
"""

import ctypes
import json
import os
from ctypes import (c_int, c_long, c_float, c_double, c_char_p,
                    POINTER, byref, create_string_buffer)


class ChanlunAPI:
    """chanlun64_jt.dll 的 Python 封装（ctypes 薄绑定）"""

    def __init__(self, dll_path):
        if not os.path.exists(dll_path):
            raise FileNotFoundError("DLL not found: {0}".format(dll_path))
        self._dll = ctypes.CDLL(dll_path)
        self._bind()

    def _bind(self):
        dll = self._dll

        # ---- 生命周期 ----
        dll.CL_Init.argtypes = [c_char_p]
        dll.CL_Init.restype = c_int

        dll.CL_Cleanup.argtypes = []
        dll.CL_Cleanup.restype = None

        dll.CL_ReleaseRecord.argtypes = [c_long]
        dll.CL_ReleaseRecord.restype = c_int

        # ---- 数据导入 ----
        dll.CL_ImportKline.argtypes = [
            c_char_p, c_int,
            POINTER(c_double), POINTER(c_float), POINTER(c_float),
            POINTER(c_float), POINTER(c_float), POINTER(c_float),
            c_int
        ]
        dll.CL_ImportKline.restype = c_long

        # ---- 结构计算 ----
        dll.CL_CalcStructure.argtypes = [c_long]
        dll.CL_CalcStructure.restype = c_int

        # ---- 特征计算 ----
        dll.CL_CalcFeature.argtypes = [c_long, c_char_p, c_int, c_char_p, c_int]
        dll.CL_CalcFeature.restype = c_int

        # ---- 结构导出 ----
        dll.CL_ExportStruct.argtypes = [c_long, c_char_p, c_int, c_int, c_char_p, c_int]
        dll.CL_ExportStruct.restype = c_int

        # ---- ParamSet 转换 ----
        dll.CL_EncodeParamSet.argtypes = [c_char_p, POINTER(c_long), POINTER(c_long)]
        dll.CL_EncodeParamSet.restype = c_int

        dll.CL_DecodeParamSet.argtypes = [c_long, c_long, c_char_p, c_int]
        dll.CL_DecodeParamSet.restype = c_int

        # ---- 动态调试 ----
        dll.CL_BeginDynamicDebug.argtypes = [c_char_p, c_int, c_int]
        dll.CL_BeginDynamicDebug.restype = c_int

        dll.CL_EndDynamicDebug.argtypes = [c_char_p, c_int]
        dll.CL_EndDynamicDebug.restype = c_int

    # ================================================================
    # 公开接口
    # ================================================================

    def init(self, config_json="{}"):
        """初始化 DLL 计算环境，返回 0=成功"""
        return self._dll.CL_Init(config_json.encode("utf-8"))

    def cleanup(self):
        """清理全部记录与缓存（会话收尾调用，全清含缓存）"""
        self._dll.CL_Cleanup()

    def release_record(self, handle):
        """释放指定 record"""
        return self._dll.CL_ReleaseRecord(handle)

    def import_kline(self, stock_code, period, dates, opens, highs, lows,
                     closes, volumes):
        """导入K线数据，返回 record 句柄。

        一次完成 HLOCV 导入 → 结构计算 → 指标/量化因子预计算 → 注册句柄。
        period 为 DataPeriod 整型（M30=1/DAY=2/WEEK=3/MONTH=4）。
        """
        n = len(dates)
        c_dates = (c_double * n)(*dates)
        c_open = (c_float * n)(*opens)
        c_high = (c_float * n)(*highs)
        c_low = (c_float * n)(*lows)
        c_close = (c_float * n)(*closes)
        c_vol = (c_float * n)(*volumes)
        return self._dll.CL_ImportKline(
            stock_code.encode("utf-8"), period,
            c_dates, c_open, c_high, c_low, c_close, c_vol, n
        )

    def calc_structure(self, handle):
        """幂等结构计算（回测逐点截断专用；投研导入即算好，无需调）"""
        return self._dll.CL_CalcStructure(handle)

    def calc_feature(self, handle, param_set_json, ref_idx=-1):
        """特征计算，返回 (ret_code, result_dict_or_none)"""
        js = param_set_json.encode("utf-8")
        cap = self._dll.CL_CalcFeature(handle, js, ref_idx, None, 0)
        if cap <= 0:
            return cap, None
        buf = create_string_buffer(cap + 1)
        ret = self._dll.CL_CalcFeature(handle, js, ref_idx, buf, cap)
        if ret != 0:
            return ret, None
        raw = buf.value
        if not raw:
            return -1, None
        return 0, json.loads(raw.decode("utf-8"))

    def export_struct(self, handle, entity_kind, offset=-1, limit=-1):
        """导出结构产物，返回 (ret_code, result_dict_or_none)

        entity_kind ∈ kline_indicator/bi_frac/duan_frac/road_frac/zhongshu
        （align_marker 已废弃，分片库不再导出）。
        """
        kind = entity_kind.encode("utf-8")
        cap = self._dll.CL_ExportStruct(handle, kind, offset, limit, None, 0)
        if cap <= 0:
            return cap, None
        buf = create_string_buffer(cap + 1)
        ret = self._dll.CL_ExportStruct(handle, kind, offset, limit, buf, cap)
        if ret != 0:
            return ret, None
        raw = buf.value
        if not raw:
            return -1, None
        return 0, json.loads(raw.decode("utf-8"))

    def encode_param_set(self, param_json):
        """JSON ParamSet → 通达信编码 (TZP1, TZP2)"""
        tzp1, tzp2 = c_long(0), c_long(0)
        ret = self._dll.CL_EncodeParamSet(param_json.encode("utf-8"),
                                           byref(tzp1), byref(tzp2))
        return ret, tzp1.value, tzp2.value

    def decode_param_set(self, tzp1, tzp2):
        """通达信编码 → JSON ParamSet"""
        cap = self._dll.CL_DecodeParamSet(tzp1, tzp2, None, 0)
        if cap <= 0:
            return None
        buf = create_string_buffer(cap + 1)
        ret = self._dll.CL_DecodeParamSet(tzp1, tzp2, buf, cap)
        if ret != 0:
            return None
        raw = buf.value
        return json.loads(raw.decode("utf-8")) if raw else None

    def begin_dynamic_debug(self, stock_code, start_idx, end_idx):
        """开启动态调试会话，返回 0=成功"""
        return self._dll.CL_BeginDynamicDebug(
            stock_code.encode("utf-8"), start_idx, end_idx)

    def end_dynamic_debug(self):
        """关闭动态调试会话，返回日志文件路径"""
        buf = create_string_buffer(4096)
        self._dll.CL_EndDynamicDebug(buf, 4096)
        return buf.value.decode("utf-8") if buf.value else ""