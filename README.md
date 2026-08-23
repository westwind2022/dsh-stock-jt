# dsh-stock-jt — 技术面研判（架梯动力学）DSH 插件

**技术面维度**独立 DSH 插件：独立 skill（`technical-analysis`）+ 投研取数脚本（`struct_calc.py`），消费 chanlun_dll 结构数据产出**供人决策的论据**（架梯分型 / 挂坡 D⁺/D/D⁻ / 强势起步 E⁺/E/E⁻ / 背驰 / 强弱）。

## 结构

```
dsh-stock-jt/
├── index.js               # cordis 插件入口：注册极简 skill provider（只服务本包 skills/）
├── client/
│   └── client.js          # ★ Web 前端 bundle：设置页「技术面研判」功能菜单（sidebar.settings → settings.section）
├── cordis.patch.yml       # bundle patch：insert 一行（dshmarket 同款）
├── package.json           # name + main + dsh.bundle.patch + dsh.client
├── vendor/
│   └── chanlun64.dll      # ★ 随包分发的 chanlun_dll 编译产物（x64 静态链接，见「dll 版本同步」）
├── config/
│   └── runtime.env.example # 部署参数模板（复制为 runtime.env 填入）
└── skills/
    └── technical-analysis/
        ├── SKILL.md       # 独立 skill 入口
        ├── internal/技术面/  # 知识层（推理规则 1-12 / 结构 / 特征 / config / 案例库）
        └── scripts/       # 取数脚本（struct_calc.py / env_check.py / chanlun_api.py / gbbq.py / kline_source.py / _smoke.py）
```

## 安装

```sh
# 从 GitHub 安装（推荐）
dsh plugin --profile web add github:westwind2022/dsh-stock-jt
# 或本地路径（开发期）
dsh plugin --profile web add /path/to/dsh-stock-jt
# 卸载
dsh plugin --profile web remove dsh-stock-jt
```

安装后**重启 dsh web 生效**。headless profile 同样可装（无前端）。

## Web 前端（client bundle · 设置页 v2）

插件带 `client/client.js`（`__ModuleLoader__` 格式，dshmarket 同款机制）：通过 **`settings.section` slot** 在 DSH 设置面板注册「**技术面研判**」功能页（侧边栏底部设置入口 → 设置 → 技术面研判），页面分两大块：

**① 环境设置区（可交互）**——读写插件 `runtime.env`（经服务端 `GET/POST /dsh-stock-jt/env`，同源校验 + token 脱敏 + 原子写）：
- 数据源复选框（vipdoc / tdx-mcp / 双源）勾选联动必填；
- TDX_ROOT / TDX_MCP_TOKEN（脱敏 ********）/ VENV_PYTHON 输入 + 保存；
- **自动探测本机 Python 解释器**（服务端 probePython：包内 venv / 常见 venv / 系统 python + py），页面列出可一键填入 VENV_PYTHON；
- **会话中插件发现缺配置时，引导用户到本页配置**（SKILL.md 引导协议已改：页面优先，会话 `--write` 备选）。

**② 工作提示词区**——四块工作，复制到会话执行：
- **技术面分析**：一句式「请对 {code} 进行技术面分析」；
- **知识蒸馏**：要求携带被蒸馏文件路径（`被蒸馏文件路径 = <替换>`）；
- **特征配置**：启动提示词（先读现状→核对契约→出改单清单待确认）+ **验收提示词**（一致性二值检查）；中间过程由会话内 LLM 逐步引导；
- **本地环境依赖检查与安装**：只检测+给命令，不自动装。
- 底部附 **架梯动力学知识贴链接**（55188，欢迎技术交流）。

> 服务端路由在 `index.js`（`ctx.inject(['webServer'])` 延迟注入）：web profile 提供 env 读写；headless 无 webServer 时路由静默跳过，skill 能力不受影响。升级 client/服务端后需重启 dsh web（client bundle 不热更）。

## 数据源配置（部署机）

**数据源复选框**（`KLINE_SOURCES`，vipdoc / tdx-mcp 独立勾选可多选，缺省 `vipdoc,tdxmcp`）：

| 勾选 | KLINE_SOURCES | 需用户提供 |
|---|---|---|
| ✅ vipdoc | `vipdoc` | `TDX_ROOT` 通达信根目录（vipdoc/gbbq 由其推导） |
| ✅ tdx-mcp | `tdxmcp` | `TDX_MCP_TOKEN`（**用户自备，无通用 token**，禁入库） |
| ✅✅ 两者 | `vipdoc,tdxmcp` | `TDX_ROOT` + `TDX_MCP_TOKEN` |

复制 `config/runtime.env.example` → `config/runtime.env`（或任一路径，用环境变量 `TA_RUNTIME_ENV` 显式指向）：

| 配置 | 说明 | 必填 |
|---|---|---|
| `KLINE_SOURCES` | 数据源（复选框组合：vipdoc / tdxmcp / 双源） | ✅ |
| `TDX_ROOT` | 通达信根目录（推导 vipdoc / gbbq） | 勾选 vipdoc 时必填 |
| `TDX_MCP_TOKEN` | MCP token（自备） | 勾选 tdxmcp 时必填 |
| `VENV_PYTHON` | **推荐指定解释器绝对路径（≥3.10，跨机可复现）**；留空用当前解释器（env_check 显示其路径） | 可选 |

> **不再提供配置**：`CHANLUN_DLL_PATH`（已随包 vendor/ 分发）、`VIPDOC_ROOT`/`GBBQ_PATH`（由 TDX_ROOT 推导）。Python 依赖 numpy/pandas/requests 由用户解释器提供（工作提示词「本地环境依赖检查与安装」协助，不自动装）。目标机器无 python 时，在设置页 `VENV_PYTHON` 填解释器绝对路径或安装 Python ≥3.10。

```sh
python skills/technical-analysis/scripts/struct_calc.py 600519 day 250
```

## dll 版本同步纪律（vendor/chanlun64.dll）

- **来源**：`chanlun_dll/out/build/x64-Release/chanlun64.dll`（自研编译产物，静态链接 /MT，单文件无外部运行库依赖）。
- **架构**：x64 绑定（当前构建）。跨架构部署需重新编译并替换 `vendor/chanlun64.dll`。
- **同步**：chanlun_dll 升级（改特征/结构计算）后，须**重新复制新 dll 到 `vendor/` 并 bump 插件版本**（`package.json` version + 本 README 登记），否则插件携带旧结构算法。
- **解析优先级**（struct_calc.py / env_check.py 同口径）：包内 `vendor/` → `CHANLUN_DLL_PATH` → 默认推导（开发 out/build + 部署 T0002/dlls）。

## 环境配套自检与引导（会话内）

调用 `technical-analysis` 技能前，LLM 会先跑 `scripts/env_check.py` 自检数据源模式 / vipdoc / tdx-mcp / chanlun64.dll / **Python 依赖**（numpy/pandas/requests）/ gbbq：

```sh
python skills/technical-analysis/scripts/env_check.py            # 人类可读报告
python skills/technical-analysis/scripts/env_check.py --json    # 机器可读（LLM 解析）
```

- **`ready: true`** → 直接研判；
- **`ready: false`（硬缺失）** → 会话中主动输出「环境配套声明」，先让用户**数据源 3 选 1**（vipdoc / tdx-mcp / 双源），再按选择收集路径/token 落盘：
  ```sh
  python skills/technical-analysis/scripts/env_check.py --write="KLINE_SOURCES=vipdoc,tdxmcp" --write="TDX_ROOT=D:\..." --write="TDX_MCP_TOKEN=..."
  ```
- Python 依赖缺失 → 引导 `python -m pip install numpy pandas requests`（或 venv 三模式）；
- 未选数据源自动 `skipped`（仅 vipdoc 不查 token，仅 tdx-mcp 不查 TDX_ROOT）；`optional-missing`（gbbq）不阻塞。

> 注：依赖自检由本插件 `env_check.py` 自包含完成（不依赖外部 env 扫描）。

## 验证

1. 重启后技能目录出现 `technical-analysis`；
2. `skill(technical-analysis)` 可加载（frontmatter name/description 单行）；
3. `env_check.py` 自检 `ready: true`（vipdoc + dll 就绪）；
4. 取数实跑出五实体结构 JSON；
5. 既有技能不受影响——本插件**不覆盖** `skill-filesystem` 行，只新增独立 provider。

## 维护（版本同步）

| 组件 | 同步要点 |
|---|---|
| `vendor/chanlun64.dll` | chanlun_dll 升级后重新复制并 bump 版本（见「dll 版本同步」） |
| 知识层 `skills/technical-analysis/internal/` | 推理规则/特征/config 变更随版本发布 |

## 红线（技术面四条，见 SKILL.md）

双轨制（只解读不计算/检出）｜三条禁止（无信号结论/无固化分数/不覆盖检出集合）｜可追溯（锚 `表.字段 + 因子值`）｜自包含（无盘符绝对路径）。
