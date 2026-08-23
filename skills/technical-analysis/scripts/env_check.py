#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
# -*- coding: utf-8 -*-
"""
env_check.py - 技术面插件（dsh-stock-jt）环境配套自检

检查投研取数所需的运行时路径是否就绪：vipdoc / chanlun64_jt.dll / gbbq / MCP 备源。
供 LLM 在会话中主动声明插件环境配套、向用户收集缺失路径并落盘。

用法：
    python env_check.py                 # 自检，输出人类可读报告（含 JSON 摘要行）
    python env_check.py --json          # 只输出 JSON 报告（机器可读）
    python env_check.py --write KEY=V   # 把 KEY=V 写入 config/runtime.env（原子替换），
                                        #   写后立即重检并输出报告（可多次 --write）

退出码：0 = 全部就绪；1 = 存在缺失/不可用项（供 LLM 判断是否需引导用户）。

输出契约（JSON 摘要，LLM 按此解析）：
{
  "ready": false,                       # true=全部就绪
  "config_file": "<runtime.env 路径或 null>",
  "items": [                            # 每项一个
    {"key": "TDX_ROOT", "ok": false, "state": "missing|invalid|ok|optional-missing",
     "detail": "现状说明", "need": "用户需提供什么（缺失时才非空）"}
  ]
}

原子写纪律：--write 走 .tmp + 替换（项目红线）；不直接改部署机机密之外的配置。
"""

import json
import os
import sys

# 自包含纪律：本脚本零第三方依赖（importlib 探测依赖），顶层不 import struct_calc
# （struct_calc → kline_source 链会 import numpy/pandas/requests，缺依赖时自检会崩）。
# 路径解析纯函数在此内联（与 struct_calc 同口径，无第三方依赖）。

CONFIG_FILENAME = "runtime.env"


def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def package_root():
    """插件包根 = scripts 上 3 层（scripts → technical-analysis → skills → 包根）。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(script_dir())))


def config_path():
    """runtime.env 路径：TA_RUNTIME_ENV 显式优先，否则包根 config/runtime.env。"""
    explicit = os.environ.get("TA_RUNTIME_ENV", "")
    if explicit:
        return explicit
    return os.path.join(package_root(), "config", CONFIG_FILENAME)


def load_runtime_env(root=None):
    """读环境变量 + config/runtime.env（KEY=VALUE），环境变量优先；同 struct_calc 口径。"""
    root = root or package_root()
    env = dict(os.environ)
    explicit = env.get("TA_RUNTIME_ENV", "")
    env_file = explicit if explicit else os.path.join(root, "config", CONFIG_FILENAME)
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if "#" in v:  # 行内注释剥离
                    v = v.split("#", 1)[0].strip()
                env.setdefault(k, v)
    return env


def _tdx_root(env):
    p = env.get("TDX_ROOT", "")
    return os.path.expanduser(p) if p else None


def resolve_dll_path(env, root=None):
    """chanlun64_jt.dll（优先级）：① 插件包 vendor/ 自带 → ② CHANLUN_DLL_PATH 显式 → ③ 默认推导。同 struct_calc 口径。"""
    root = root or package_root()
    bundled = os.path.join(root, "vendor", "chanlun64_jt.dll")
    if os.path.exists(bundled):
        return bundled
    p = env.get("CHANLUN_DLL_PATH", "")
    if p:
        p = os.path.expanduser(p)
        if os.path.exists(p):
            return p
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
    """vipdoc 根：config 显式优先，TDX_ROOT/vipdoc 推导，相对兜底。同 struct_calc 口径。"""
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
    root = root or package_root()
    ws = os.path.dirname(root)
    for c in [os.path.join(ws, "vipdoc"), os.path.join(root, "vipdoc")]:
        if os.path.isdir(c):
            return c
    return None


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


def _version_ge(version_str, minimum):
    """'3.10' 等版本串是否 >= minimum (major, minor)。解析失败返回 False。"""
    try:
        parts = [int(p) for p in version_str.split(".") if p.isdigit()]
        if len(parts) < 2:
            return False
        return (parts[0], parts[1]) >= minimum
    except (ValueError, TypeError):
        return False


def check(env):
    """逐项检查，返回 (items, ready)。"""
    items = []

    # 0. 数据源模式（KLINE_SOURCES 三选一：vipdoc / tdxmcp / vipdoc,tdxmcp）
    #    模式决定哪些源为硬必需：vipdoc 需要 TDX_ROOT，tdxmcp 需要 TDX_MCP_TOKEN。
    sources = [s.strip() for s in env.get("KLINE_SOURCES", "vipdoc,tdxmcp").split(",") if s.strip()]
    valid_sources = {"vipdoc", "tdxmcp"}
    unknown = [s for s in sources if s not in valid_sources]
    if not sources:
        mode_ok = False
        mode_detail = "KLINE_SOURCES 为空（至少选一个数据源）"
        mode_need = "三选一：vipdoc（仅本地）/ tdxmcp（仅云端 MCP）/ vipdoc,tdxmcp（本地主 + 云端辅）"
    elif unknown:
        mode_ok = False
        mode_detail = "KLINE_SOURCES 含未知源: {0}".format(",".join(unknown))
        mode_need = "修正为三选一：vipdoc / tdxmcp / vipdoc,tdxmcp"
    else:
        mode_ok = True
        mode_detail = "模式: {0}".format(
            "仅本地 vipdoc" if sources == ["vipdoc"] else
            "仅云端 tdx-mcp" if sources == ["tdxmcp"] else
            "vipdoc 主 + tdx-mcp 辅")
        mode_need = ""
    items.append({
        "key": "DATA_SOURCE", "ok": mode_ok, "state": "ok" if mode_ok else "invalid",
        "detail": mode_detail + "（KLINE_SOURCES={0}）".format(env.get("KLINE_SOURCES", "vipdoc,tdxmcp")),
        "need": mode_need,
    })
    need_vipdoc = "vipdoc" in sources
    need_tdxmcp = "tdxmcp" in sources

    # 1. TDX_ROOT → vipdoc（模式含 vipdoc 时硬必需）
    if need_vipdoc:
        tdx = env.get("TDX_ROOT", "").strip()
        if not tdx:
            items.append({
                "key": "TDX_ROOT", "ok": False, "state": "missing",
                "detail": "未配置通达信根目录（当前模式需要 vipdoc）",
                "need": "通达信安装根目录，如 D:\\tdx2026\\new_tdx64_day（推导 vipdoc=TDX_ROOT/vipdoc）",
            })
        else:
            vipdoc = resolve_vipdoc_root(env)
            if vipdoc:
                items.append({
                    "key": "TDX_ROOT", "ok": True, "state": "ok",
                    "detail": "vipdoc 可用: {0}".format(vipdoc), "need": "",
                })
            else:
                items.append({
                    "key": "TDX_ROOT", "ok": False, "state": "invalid",
                    "detail": "已配置 {0}，但 {0}\\vipdoc 目录不存在（本地主源不可用）".format(tdx),
                    "need": "正确的通达信根目录（含 vipdoc 子目录），或显式 VIPDOC_ROOT",
                })
    else:
        items.append({
            "key": "TDX_ROOT", "ok": True, "state": "skipped",
            "detail": "当前模式不需要 vipdoc（仅 tdx-mcp）", "need": "",
        })

    # 2. chanlun64_jt.dll（独立配置；默认推导路径在插件包布局下通常不适用）
    try:
        dll = resolve_dll_path(env)
        items.append({
            "key": "CHANLUN_DLL_PATH", "ok": True, "state": "ok",
            "detail": "chanlun64_jt.dll 可用: {0}".format(dll), "need": "",
        })
    except FileNotFoundError as e:
        items.append({
            "key": "CHANLUN_DLL_PATH", "ok": False, "state": "missing",
            "detail": str(e),
            "need": "chanlun64_jt.dll 的完整路径（chanlun_dll 编译产物），如 D:\\trading_kit\\chanlun_dll\\out\\build\\x64-Release\\chanlun64_jt.dll",
        })

    # 3. Python 解释器 + 依赖（struct_calc/kline_source 的 PEP 723 声明；本脚本零第三方依赖，
    #    用目标解释器探测——插件目录不在外部 env skill 扫描范围内，必须自检）
    #    venv 供给（用户可控，SKILL.md 引导协议）：
    #      A 用户显式指定解释器 → 配置 VENV_PYTHON=<python/venv 的绝对路径>（推荐：跨机可复现）
    #      C 未配置 → 用当前解释器 sys.executable（env_check 会显示其绝对路径，便于确认）
    #    依赖缺失只给手动安装指引，**不自动安装**（由用户确认后手动执行）。
    import importlib
    import subprocess
    venv_py = (env.get("VENV_PYTHON", "") or "").strip()
    venv_invalid = bool(venv_py) and not os.path.exists(venv_py)
    if venv_invalid:
        items.append({
            "key": "VENV_PYTHON", "ok": False, "state": "invalid",
            "detail": "已配置 {0}，但文件不存在".format(venv_py),
            "need": "正确的 python/venv 解释器绝对路径（如 D:\\...\\venv\\Scripts\\python.exe），或在设置页 VENV_PYTHON 处修正",
        })
    target = venv_py if (venv_py and os.path.exists(venv_py)) else sys.executable
    # 解释器版本（PEP 723 requires-python >=3.10；struct_calc 依赖）
    try:
        ver_out = subprocess.check_output(
            [target, "-c", "import sys; print('%d.%d' % (sys.version_info[0], sys.version_info[1]))"],
            stderr=subprocess.DEVNULL, text=True).strip()
        ver_ok = _version_ge(ver_out, (3, 10))
        items.append({
            "key": "PY_VERSION", "ok": ver_ok, "state": "ok" if ver_ok else "invalid",
            "detail": "解释器版本: {0}（要求 >=3.10）".format(ver_out or "未知"),
            "need": "" if ver_ok else "需 Python >=3.10 的解释器（struct_calc 需要）；在设置页 VENV_PYTHON 指定或升级",
        })
    except (OSError, subprocess.CalledProcessError) as e:
        items.append({
            "key": "PY_VERSION", "ok": False, "state": "invalid",
            "detail": "无法运行解释器 {0}: {1}".format(target, e),
            "need": "该解释器不可执行——确认 VENV_PYTHON 指向有效 python.exe，或当前环境无 python（需在设置页 VENV_PYTHON 指定，或安装 Python >=3.10）",
        })
    items.append({
        "key": "VENV_PYTHON", "ok": not venv_invalid, "state": "ok" if not venv_invalid else "invalid",
        "detail": "目标解释器: {0}{1}".format(
            target,
            "（显式指定 VENV_PYTHON）" if venv_py and not venv_invalid else "（未配置或配置无效，用当前解释器——建议在设置页显式指定以便跨机复现）"),
        "need": "",
    })
    probe = [target, "-c", "import importlib.util; mods=['numpy','pandas','requests']; "
             "print(' '.join(m for m in mods if importlib.util.find_spec(m) is None))"]
    try:
        missing_out = subprocess.check_output(probe, stderr=subprocess.DEVNULL, text=True).strip()
        missing_deps = missing_out.split() if missing_out else []
    except (OSError, subprocess.CalledProcessError) as e:
        missing_deps = []
        items.append({
            "key": "PY_PROBE", "ok": False, "state": "invalid",
            "detail": "目标解释器探测失败: {0}".format(e),
            "need": "检查 VENV_PYTHON 是否为有效 python.exe",
        })
    for dep in ("numpy", "pandas", "requests"):
        ok = dep not in missing_deps
        items.append({
            "key": "PY_DEP:" + dep, "ok": ok, "state": "ok" if ok else "missing",
            "detail": "{0} 在目标解释器 {1}".format("可 import" if ok else "不可 import", target),
            "need": "" if ok else "手动安装（用户确认后执行）：{0} -m pip install {1}；装完重跑本脚本复验".format(target, dep),
        })

    # 4. gbbq 除权库（仅 vipdoc 模式检查；前复权正确性依赖，缺失降级为无除权）
    if need_vipdoc:
        gbbq = resolve_gbbq_path(env, resolve_vipdoc_root(env))
        items.append({
            "key": "GBBQ_PATH", "ok": gbbq is not None, "state": "ok" if gbbq else "optional-missing",
            "detail": "gbbq 除权库: {0}".format(gbbq) if gbbq else "未找到（前复权可能不含除权事件，主源 vipdoc 仍可读）",
            "need": "" if gbbq else "（可选）通达信 gbbq 除权库路径，如 {TDX_ROOT}\\T0002\\hq_cache\\gbbq",
        })
    else:
        items.append({
            "key": "GBBQ_PATH", "ok": True, "state": "skipped",
            "detail": "当前模式不需要 gbbq（仅 tdx-mcp）", "need": "",
        })

    # 5. TDX_MCP_TOKEN（模式含 tdxmcp 时硬必需；仅 vipdoc 模式跳过）
    if need_tdxmcp:
        token = env.get("TDX_MCP_TOKEN", "").strip()
        items.append({
            "key": "TDX_MCP_TOKEN", "ok": bool(token),
            "state": "ok" if token else "missing",
            "detail": "MCP 备源 token: {0}".format("已配置" if token else "未配置（当前模式需要 tdx-mcp）"),
            "need": "" if token else "通达信云端 MCP token（机密，只写入部署机 runtime.env）",
        })
    else:
        items.append({
            "key": "TDX_MCP_TOKEN", "ok": True, "state": "skipped",
            "detail": "当前模式不需要 tdx-mcp（仅 vipdoc）", "need": "",
        })

    # 就绪判定：只认硬缺失（missing/invalid）；optional-missing（备源/质量项）不阻塞
    ready = all(it["state"] not in ("missing", "invalid") for it in items)
    return items, ready


def write_config(assignments, path):
    """原子写 runtime.env：新增/覆盖 KEY=VALUE。返回更新后的完整文本。"""
    new_lines = []
    keys = {k for k, _ in assignments}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = f.readlines()
        kept = []
        for line in existing:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                kept.append(line)
                continue
            k = s.split("=", 1)[0].strip()
            if k in keys:
                continue  # 将被覆盖
            kept.append(line)
        new_lines = kept
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    for k, v in assignments:
        new_lines.append("{0}={1}\n".format(k, v))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    os.replace(tmp, path)  # 原子替换
    return path


def _fix_stdout_utf8():
    """Windows 控制台中文乱码加固：stdout/stderr 固定 UTF-8（P1-④）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main():
    _fix_stdout_utf8()
    args = sys.argv[1:]
    json_only = "--json" in args
    writes = [a for a in args if a.startswith("--write=")]
    path = config_path()

    if writes:
        assignments = []
        for w in writes:
            kv = w[len("--write="):]
            k, _, v = kv.partition("=")
            if not k or not v:
                print("bad --write (need KEY=VALUE): {0}".format(w))
                return 2
            assignments.append((k.strip(), v.strip()))
        write_config(assignments, path)
        # 重检基于「文件既有内容（含环境变量覆盖）+ 本次写入」，不丢已有配置
        merged = load_runtime_env()
        for k, v in assignments:
            merged[k] = v
        env = merged
    else:
        env = load_runtime_env()

    items, ready = check(env)
    report = {
        "ready": ready,
        "config_file": path if os.path.exists(path) else None,
        "items": items,
    }

    if json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ready else 1

    print("== dsh-stock-jt 环境配套自检 ==")
    print("config: {0}".format(report["config_file"] or "（未找到 runtime.env，需 --write 创建）"))
    for it in items:
        mark = "OK " if it["ok"] else "MISS"
        print("[{0}] {1}: {2}".format(mark, it["key"], it["detail"]))
        if it["need"]:
            print("       需要: {0}".format(it["need"]))
    print("== 就绪: {0} ==".format("是" if ready else "否（缺失项见上，可 --write KEY=VALUE 补齐后重检）"))
    print("__ENV_CHECK_JSON__ " + json.dumps(report, ensure_ascii=False))
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
