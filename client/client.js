window.__ModuleLoader__.load({ id: "dsh-stock-jt", factory: (require) => {
  /** dsh-stock-jt client bundle v2:
   * 1) 环境设置区 —— 页面内读写 runtime.env（GET/POST /dsh-stock-jt/env，token 脱敏），
   *    数据源 3 选 1 + 路径/token 输入 + 保存；插件执行发现缺配置时引导到这里。
   * 2) 提示词区 —— 三块工作提示词（技术面分析 / 知识蒸馏 / 特征配置），
   *    特征配置含启动提示词 + 验收提示词，中间过程由会话内 LLM 逐步引导。
   * 纯前端 + 服务端 env 路由；无其它后端依赖。
   */
  var module = { exports: {} };
  var exports = module.exports;
  Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

  let react = require("react");
  let prim = require("@deepseek-ai/dsh-client-ui-primitives");

  const NS = "dsh-stock-jt";
  const ENV_URL = "/dsh-stock-jt/env";

  // ============================================================
  // 文案
  // ============================================================
  const zh = {
    nav: "技术面研判",
    subtitle: "dsh-stock-jt · 架梯动力学技术面研判（消费 chanlun 结构数据）",
    tabEnv: "环境设置",
    tabPrompts: "工作提示词",
    envTitle: "环境设置",
    envHint: "在此页面配置数据源与运行路径（写入插件 runtime.env）。勾选数据源后按需填写；会话中执行插件时若发现缺配置，会引导你回到这里。",
    dsTitle: "数据源（可多选）",
    ds1: "本地 vipdoc（通达信）",
    ds2: "云端 tdx-mcp",
    fieldTdxRoot: "TDX_ROOT（通达信根目录，勾选 vipdoc 时必填）",
    fieldToken: "TDX_MCP_TOKEN（勾选 tdx-mcp 时必填，自备 token，脱敏显示）",
    fieldVenv: "VENV_PYTHON（推荐指定解释器绝对路径，跨机可复现；留空用当前解释器）",
    probeTitle: "检测到本机 Python 解释器（点击填入 VENV_PYTHON）：",
    probeUse: "使用",
    probeNone: "未检测到本机 Python——请在 VENV_PYTHON 手动填写解释器绝对路径，或安装 Python ≥3.10 后重进本页。",
    depNote: "Python 依赖（取数需要）：numpy / pandas / requests；解释器要求 >=3.10。指定 VENV_PYTHON 后插件用该解释器（跨机可控）；留空则用当前解释器（env_check 会显示其绝对路径）。不会装依赖可复制「工作提示词 → 本地环境依赖检查与安装」给助手。",
    placeholderTdxRoot: "如 D:\\tdx2026\\new_tdx64_day（vipdoc/gbbq 由其推导）",
    placeholderToken: "自备 token，已配置则显示 ********",
    placeholderVenv: "如 D:\\...\\venv\\Scripts\\python.exe（Python >=3.10）",
    save: "保存配置",
    saving: "保存中…",
    saved: "✓ 已保存",
    saveFail: "保存失败: ",
    loadFail: "配置读取失败: ",
    promptTitle: "工作提示词（复制到会话使用）",
    promptHint: "在 DSH 会话中粘贴提示词，由 technical-analysis 技能 + LLM 执行；特征配置含启动/验收两段。",
    p1Title: "技术面分析",
    p1Desc: "对单标的做架梯动力学研判（势/形、挂坡 D⁺/D/D⁻、强势起步 E⁺/E/E⁻、背驰/强弱）",
    p1Copy: "请对 {code} 进行技术面分析",
    p2Title: "知识蒸馏",
    p2Desc: "把课件/笔记/案例蒸馏为技术面推理规则与特征表（推理规则.md + 特征/ + config/）",
    p2Copy: "执行技术面知识蒸馏：被蒸馏文件路径 = <请替换为课件/笔记/案例文件路径>。输入为该文件内容，输出更新到 internal/技术面/（推理规则.md、特征/{坐标,成色,刻度}.md、config/{polarity_table,weight_table,feature_anchor}.json、案例库.md）。蒸馏纪律：场景由框架定义不自造、看图次第四步固定不改序、事实层（因子名+字段+值）不调校、结论层（极性/权重）可调校、每条规则锚定 表.字段+因子值、阈值引用课件经验值不硬编码。产出物逐条自检后汇报差异清单。",
    p3Title: "特征配置",
    p3Desc: "配置特征锚定（feature_anchor）、极性表、权重表、能力自声明（capability_manifest）",
    p3StartTitle: "启动提示词",
    p3StartCopy: "启动特征配置任务：目标 = 维护 internal/技术面/config/ 的 {feature_anchor, polarity_table, weight_table, capability_manifest}.json。步骤：1) 先读现状（4 个 json + 推理规则.md 〇.4 + 特征/ 三表 + db/schema.md 字段语义）；2) 按「特征→字段锚定、极性三态、权重默认 1.0 可调、能力自声明」四个契约核对一致性；3) 逐项列出拟改项（字段名/极性/权重/声明），说明理由与出处；4) 不直接改文件，先给改单清单等我确认。红线：事实层（字段名+因子值）不调校、结论层（极性/权重）可调校、不硬编码阈值、场景由框架定义。",
    p3AcceptTitle: "验收提示词",
    p3AcceptCopy: "验收特征配置：对照 4 份 json 与推理规则.md/特征表/db schema 做一致性检查——1) feature_anchor 的每个 field 在 db/schema.md 或 struct JSON 中存在且语义一致；2) polarity_table 三态（+1/0/-1）覆盖所用因子、reversal 项与「中性·看位置」注释一致；3) weight_table 键集与 polarity_table 因子集对齐、权重可调；4) capability_manifest 的 injection_points.declarations 与特征表/锚定表一一对应；5) 无硬编码绝对阈值（引用出处表）；6) 输出「满足/不满足」二值结论 + 差异清单。",
    p4Title: "本地环境依赖检查与安装",
    p4Desc: "检查插件运行所需 Python 库（numpy/pandas/requests），缺失时给出安装指引（不自动装，由你确认）",
    p4Copy: "检查 dsh-stock-jt（技术面研判）本地环境依赖：1) 跑 scripts/env_check.py 看 PY_DEP:* 项与 venv 供给状态；2) 若 numpy/pandas/requests 缺失，列出缺失库与安装命令（python -m pip install <库>，可指定 venv）；3) 只输出检测结果与安装指引，不自动执行安装；4) 安装由用户确认后手动执行，装完重跑 env_check 复验 ready。",
    postTitle: "📚 架梯动力学知识贴（欢迎技术交流）",
    postLink: "https://www.55188.com/thread-40583984-1-1.html",
    copyBtn: "复制",
    copied: "✓ 已复制",
    statusTitle: "配置状态",
    statusOk: "已配置",
    statusEmpty: "未配置",
    statusHint: "★ 表示已配置；未配置项会话中会引导补充。",
    noteTitle: "说明",
    note1: "保存后立即写入插件 runtime.env（原子替换）；重启 dsh web 后 skill 取数即用新配置。",
    note2: "TDX_MCP_TOKEN 为机密，页面仅显示 ********，修改时直接输入新值保存。",
  };
  const en = zh;

  // ============================================================
  // 小工具
  // ============================================================
  function useEnv() {
    const [state, setState] = react.useState({ loading: true, error: null, payload: null });
    const reload = react.useCallback(() => {
      setState({ loading: true, error: null, payload: state.payload });
      fetch(ENV_URL, { headers: { accept: 'application/json' } })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))))
        .then((payload) => setState({ loading: false, error: null, payload }))
        .catch((e) => setState({ loading: false, error: e.message, payload: state.payload }));
    }, [state.payload]);
    react.useEffect(() => { reload(); }, [reload]);
    return [state, reload];
  }

  // ============================================================
  // 环境设置区
  // ============================================================
  function EnvSection(props) {
    const { t } = props;
    const [state, reload] = useEnv();
    const [form, setForm] = react.useState({});
    const [saveState, setSaveState] = react.useState('idle'); // idle|busy|done|fail
    const [saveError, setSaveError] = react.useState(null);

    // KLINE_SOURCES 拆分：vipdoc/tdxmcp 两个独立勾选
    const splitSources = (v) => ((v || 'vipdoc,tdxmcp').split(',').map((s) => s.trim()).filter(Boolean));
    const [checkVipdoc, setCheckVipdoc] = react.useState(true);
    const [checkTdxmcp, setCheckTdxmcp] = react.useState(true);

    react.useEffect(() => {
      if (state.payload && Object.keys(form).length === 0) {
        const vals = { ...state.payload.values };
        const srcs = splitSources(vals.KLINE_SOURCES);
        setCheckVipdoc(srcs.includes('vipdoc'));
        setCheckTdxmcp(srcs.includes('tdxmcp'));
        setForm(vals);
      }
    }, [state.payload]);

    // 勾选变化 → 重算 KLINE_SOURCES
    const applyChecks = (v, m) => {
      setCheckVipdoc(v);
      setCheckTdxmcp(m);
      const list = [];
      if (v) list.push('vipdoc');
      if (m) list.push('tdxmcp');
      setForm((f) => ({ ...f, KLINE_SOURCES: list.join(',') }));
    };

    const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
    const save = () => {
      setSaveState('busy');
      fetch(ENV_URL, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(form),
      })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))))
        .then((payload) => { setForm({ ...payload.values }); setSaveState('done'); reload(); })
        .catch((e) => { setSaveError(e.message); setSaveState('fail'); });
    };

    // 勾选联动必填字段（仅展示已勾选源所需配置）
    const needTdxRoot = checkVipdoc;
    const needToken = checkTdxmcp;

    return react.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 10 } },
      react.createElement('p', { style: { margin: 0, fontSize: 12, color: 'var(--dsh-color-text-secondary,#999)' } }, t('envHint')),

      // 数据源复选框
      react.createElement('div', { style: { display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' } },
        react.createElement('span', { style: { fontSize: 12, fontWeight: 600 } }, t('dsTitle')),
        react.createElement('label', { style: { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 } },
          react.createElement('input', { type: 'checkbox', checked: checkVipdoc, onChange: (e) => applyChecks(e.target.checked, checkTdxmcp) }),
          t('ds1')),
        react.createElement('label', { style: { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 } },
          react.createElement('input', { type: 'checkbox', checked: checkTdxmcp, onChange: (e) => applyChecks(checkVipdoc, e.target.checked) }),
          t('ds2'))),

      // 字段输入（勾选联动）
      needTdxRoot && react.createElement('label', { key: 'TDX_ROOT', style: { display: 'flex', flexDirection: 'column', gap: 3 } },
        react.createElement('span', { style: { fontSize: 12 } }, t('fieldTdxRoot') + ' *'),
        react.createElement(prim.Input, { value: form.TDX_ROOT ?? '', placeholder: t('placeholderTdxRoot'), onChange: set('TDX_ROOT') })),
      needToken && react.createElement('label', { key: 'TDX_MCP_TOKEN', style: { display: 'flex', flexDirection: 'column', gap: 3 } },
        react.createElement('span', { style: { fontSize: 12 } }, t('fieldToken') + ' *'),
        react.createElement(prim.Input, { value: form.TDX_MCP_TOKEN ?? '', placeholder: t('placeholderToken'), onChange: set('TDX_MCP_TOKEN') })),
      react.createElement('label', { key: 'VENV_PYTHON', style: { display: 'flex', flexDirection: 'column', gap: 3 } },
        react.createElement('span', { style: { fontSize: 12 } }, t('fieldVenv')),
        react.createElement(prim.Input, { value: form.VENV_PYTHON ?? '', placeholder: t('placeholderVenv'), onChange: set('VENV_PYTHON') })),

      // 探测到的解释器（一键填入 VENV_PYTHON）
      (state.payload?.pythonProbe?.length > 0) && react.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 4 } },
        react.createElement('span', { style: { fontSize: 12, fontWeight: 600 } }, t('probeTitle')),
        state.payload.pythonProbe.map((p) => react.createElement('div', { key: p.path, style: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 } },
          react.createElement('span', { style: { color: 'var(--dsh-color-text-secondary,#999)' } }, '[' + p.source + '] ' + p.path + '（' + p.version + '）'),
          react.createElement(prim.Button, {
            size: 'sm',
            onClick: () => setForm((f) => ({ ...f, VENV_PYTHON: p.path })),
          }, t('probeUse'))))),
      (state.payload && state.payload.pythonProbe?.length === 0) && react.createElement('p', { style: { margin: 0, fontSize: 11, color: 'var(--dsh-color-text-secondary,#999)' } }, t('probeNone')),

      // 依赖库备注
      react.createElement('p', { style: { margin: 0, fontSize: 11, color: 'var(--dsh-color-text-secondary,#999)' } }, t('depNote')),

      // 状态 + 保存
      react.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
        react.createElement(prim.Button, { onClick: save, disabled: saveState === 'busy', tone: 'primary' },
          saveState === 'busy' ? t('saving') : t('save')),
        saveState === 'done' && react.createElement('span', { style: { color: 'var(--dsh-color-success,#4caf50)', fontSize: 12 } }, t('saved')),
        saveState === 'fail' && react.createElement('span', { style: { color: 'var(--dsh-color-danger,#e53935)', fontSize: 12 } }, t('saveFail') + saveError)));
  }

  // ============================================================
  // 提示词区
  // ============================================================
  function PromptCard(props) {
    const { t, title, desc, prompts } = props; // prompts: [{label, text}]
    const [copied, setCopied] = react.useState(null);
    const copy = (text, idx) => () => {
      navigator.clipboard?.writeText(text).then(() => {
        setCopied(idx);
        setTimeout(() => setCopied(null), 1500);
      }).catch(() => {});
    };
    return react.createElement('div', { style: { border: '1px solid var(--dsh-color-border,#333)', borderRadius: 8, padding: 10, display: 'flex', flexDirection: 'column', gap: 6 } },
      react.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
        react.createElement('strong', { style: { fontSize: 13 } }, title),
        react.createElement('span', { style: { fontSize: 11, color: 'var(--dsh-color-text-secondary,#999)' } }, desc)),
      prompts.map((p, i) => react.createElement('div', { key: i, style: { display: 'flex', flexDirection: 'column', gap: 4 } },
        react.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
          react.createElement('span', { style: { fontSize: 12, fontWeight: 600 } }, p.label),
          react.createElement(prim.Button, { size: 'sm', onClick: copy(p.text, i) },
            copied === i ? t('copied') : t('copyBtn'))),
        react.createElement('textarea', {
          readOnly: true,
          value: p.text,
          style: { width: '100%', minHeight: 90, resize: 'vertical', fontFamily: 'monospace', fontSize: 11, background: '#ffffff', color: '#000000', border: '1px solid #ccc', borderRadius: 6, padding: 6 },
        }))));
  }

  function PromptsSection(props) {
    const { t } = props;
    const cards = [
      { title: t('p1Title'), desc: t('p1Desc'), prompts: [{ label: '提示词', text: t('p1Copy') }] },
      { title: t('p2Title'), desc: t('p2Desc'), prompts: [{ label: '提示词', text: t('p2Copy') }] },
      { title: t('p3Title'), desc: t('p3Desc'), prompts: [
        { label: t('p3StartTitle'), text: t('p3StartCopy') },
        { label: t('p3AcceptTitle'), text: t('p3AcceptCopy') },
      ] },
      { title: t('p4Title'), desc: t('p4Desc'), prompts: [{ label: '提示词', text: t('p4Copy') }] },
    ];
    return react.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 10 } },
      react.createElement('p', { style: { margin: 0, fontSize: 12, color: 'var(--dsh-color-text-secondary,#999)' } }, t('promptHint')),
      cards.map((c) => react.createElement(PromptCard, { key: c.title, t, ...c })),
      // 知识贴链接
      react.createElement('div', { style: { marginTop: 8, padding: 10, border: '1px solid var(--dsh-color-border,#333)', borderRadius: 8, display: 'flex', flexDirection: 'column', gap: 4 } },
        react.createElement('strong', { style: { fontSize: 13 } }, t('postTitle')),
        react.createElement('a', { href: 'https://www.55188.com/thread-40583984-1-1.html', target: '_blank', rel: 'noreferrer', style: { fontSize: 12, color: '#1e88e5' } }, t('postLink'))));
  }

  // ============================================================
  // 页面主体：两个 tab
  // ============================================================
  function TechnicalAnalysisSection(props) {
    const { t } = props;
    const [tab, setTab] = react.useState('env');
    return react.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 10 } },
      react.createElement('p', { style: { margin: 0, fontSize: 12, color: 'var(--dsh-color-text-secondary,#999)' } }, t('subtitle')),
      react.createElement('div', { style: { display: 'flex', gap: 8, borderBottom: '1px solid var(--dsh-color-border,#333)', paddingBottom: 6 } },
        [['env', t('tabEnv')], ['prompts', t('tabPrompts')]].map(([k, label]) =>
          react.createElement(prim.Button, {
            key: k,
            size: 'sm',
            tone: tab === k ? 'primary' : 'default',
            onClick: () => setTab(k),
          }, label))),
      tab === 'env'
        ? react.createElement(EnvSection, { t })
        : react.createElement(PromptsSection, { t }));
  }

  // ============================================================
  // 入口
  // ============================================================
  const REQUIRED_PRIMITIVES = ['Button', 'Input'];
  function missingPrimitives(mod) {
    return REQUIRED_PRIMITIVES.filter((name) => mod[name] === void 0);
  }
  const name = 'dsh-stock-jt';
  const inject = ['slots', 'locale'];

  function apply(ctx) {
    const gaps = missingPrimitives(prim);
    if (gaps.length > 0) {
      console.warn('[dsh-stock-jt] host ui-primitives missing ' + gaps.join(', ') + ' — settings section disabled');
      return;
    }
    ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'dsh-stock-jt: dictionaries');
    const t = ctx.locale.bind(NS);
    ctx.slots.inject('settings.section', () => ctx.slots.register({
      name: 'settings.section',
      id: 'stock-jt',
      order: 60,
      label: () => t('nav'),
      locale: NS,
      inject: () => ({ t })
    }, () => react.createElement(TechnicalAnalysisSection, { t })));
  }

  exports.REQUIRED_PRIMITIVES = REQUIRED_PRIMITIVES;
  exports.apply = apply;
  exports.inject = inject;
  exports.missingPrimitives = missingPrimitives;
  exports.name = name;
  return module.exports;
}});
