/**
 * dsh-stock-jt host entry: registers a minimal, isolated skill provider
 * that serves only this package's `skills/` directory.
 *
 * Pattern: dshmarket — cordis.patch.yml inserts one row `{id: dsh-stock-jt,
 * name: 'dsh-stock-jt'}`, the loader imports this package's main and calls
 * the exported `apply(ctx, config)`.
 *
 * Why a self-contained provider instead of patching `skill-filesystem`:
 * 1. cordis patches REPLACE a row's whole config (never merge) — overriding
 *    `skill-filesystem` would wipe the home-level customSkillDirs.
 * 2. `!!js` expressions evaluate in `with (ctx)` (cordis-plugin-loader), where
 *    `join`/`__dirname` are not in scope — unreliable for path injection.
 * 3. Zero external imports (no @deepseek-ai/dsh-skill-filesystem dependency),
 *    P3 self-contained, resourceBase resolved via import.meta.url.
 */
import { readdir, readFile, writeFile, rename } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const name = 'dsh-stock-jt';

/** Requires the `skills` service (mandatory); `webServer` is injected lazily
 * so the plugin works in headless profiles without a web server (routes are a
 * web-only enhancement). Same contract as @deepseek-ai/dsh-skill-filesystem. */
export const inject = ['skills'];

/** Absolute plugin package root (100% reliable under ESM). */
const ROOT = dirname(fileURLToPath(import.meta.url));
/** Skills root served by this provider. */
const SKILLS_DIR = join(ROOT, 'skills');
/** Plugin config root (runtime.env lives here). */
const CONFIG_DIR = join(ROOT, 'config');
const RUNTIME_ENV_FILE = join(CONFIG_DIR, 'runtime.env');

/** CUSTOM rank, matching @deepseek-ai/dsh-skill-filesystem's custom root rank. */
const CUSTOM_RANK = 300;
const PROVIDER_NAME = 'ta-filesystem';

/**
 * Minimal SKILL.md frontmatter parser (this package controls its own SKILL.md:
 * `name` and `description` stay single-line). Fails closed: unparsable → skill
 * not registered.
 */
function parseFrontmatter(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) return { name: undefined, description: undefined };
  const body = m[1];
  const name = body.match(/^name:\s*(.+)$/m)?.[1]?.trim();
  const description = body.match(/^description:\s*(.+)$/m)?.[1]?.trim();
  return { name, description };
}

/** Strip the YAML frontmatter block, returning the markdown body. */
function stripFrontmatter(text) {
  return text.replace(/^---\r?\n[\s\S]*?\r?\n---/, '').trim();
}

export function apply(ctx, config) {
  const providerDisposer = ctx.skills.registerProvider((control) => ({
    name: PROVIDER_NAME,

    async list() {
      const entries = await readdir(SKILLS_DIR, { withFileTypes: true });
      const candidates = [];
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;
        const skillDir = join(SKILLS_DIR, entry.name);
        const skillFile = join(skillDir, 'SKILL.md');
        const text = await readFile(skillFile, 'utf8').catch(() => null);
        if (!text) continue;
        const { name: skillName, description } = parseFrontmatter(text);
        if (!skillName || !description) continue;
        candidates.push({
          name: skillName,
          description,
          invocation: { modelInvocable: true, userInvocable: true },
          source: 'custom',
          provider: PROVIDER_NAME,
          rank: CUSTOM_RANK,
          locator: skillFile,
          path: skillFile,
        });
      }
      return candidates;
    },

    async get(candidate) {
      const text = await readFile(candidate.locator, 'utf8').catch(() => null);
      if (!text) return undefined;
      const { name: skillName, description } = parseFrontmatter(text);
      if (!skillName || !description) return undefined;
      return {
        name: skillName,
        description,
        invocation: { modelInvocable: true, userInvocable: true },
        source: 'custom',
        provider: PROVIDER_NAME,
        resourceBase: { kind: 'directory', path: dirname(candidate.locator) },
        content: stripFrontmatter(text),
        path: candidate.locator,
      };
    },
  }));

  // ---- 环境配置 HTTP 路由（供设置页读写 runtime.env，token 脱敏）----
  const mountRoutes = (host) => {
    const disposeGet = host.webServer.register({
      kind: 'exact',
      path: '/dsh-stock-jt/env',
      handler: async (request, response) => {
        if (request.method !== 'GET') {
          response.writeHead(405, { allow: 'GET, POST' });
          response.end();
          return;
        }
        try {
          sendJson(response, 200, readEnvPayload());
        } catch (error) {
          sendJson(response, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      },
    });
    const disposePost = host.webServer.register({
      kind: 'exact',
      path: '/dsh-stock-jt/env',
      handler: async (request, response) => {
        if (request.method !== 'POST') {
          response.writeHead(405, { allow: 'GET, POST' });
          response.end();
          return;
        }
        if (!sameOrigin(request)) {
          sendJson(response, 403, { error: 'untrusted origin' });
          return;
        }
        try {
          const body = await readJsonBody(request);
          await writeEnvFromBody(body);
          sendJson(response, 200, readEnvPayload());
        } catch (error) {
          sendJson(response, 400, { error: error instanceof Error ? error.message : String(error) });
        }
      },
    });
    return () => {
      disposeGet();
      disposePost();
    };
  };

  ctx.inject(['webServer'], (hostCtx) => {
    hostCtx.effect(() => mountRoutes(hostCtx), 'dsh-stock-jt: env routes');
  });

  return providerDisposer;
}

// ============================================================
// runtime.env 读写（服务端）
// ============================================================

/** 可被前端修改的白名单键（其余键原样保留在文件，不回传明文值）。
 * 仅 4 项可编辑：数据源、通达信根目录、MCP token（自备）、可选 venv。
 * VIPDOC_ROOT/GBBQ_PATH 由 TDX_ROOT 推导、CHANLUN_DLL_PATH 已随包 vendor/ —— 不再提供配置项。 */
const EDITABLE_KEYS = ['KLINE_SOURCES', 'TDX_ROOT', 'TDX_MCP_TOKEN', 'VENV_PYTHON'];
/** 机密键：GET 时脱敏（不回传明文 token）。 */
const SECRET_KEYS = ['TDX_MCP_TOKEN'];

/** 解析 runtime.env（KEY=VALUE，# 注释剥离），返回键值对象。 */
function parseEnvFile(text) {
  const out = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const eq = line.indexOf('=');
    const k = line.slice(0, eq).trim();
    let v = line.slice(eq + 1).trim();
    const hash = v.indexOf(' #');
    if (hash >= 0) v = v.slice(0, hash).trim();
    if (k) out[k] = v;
  }
  return out;
}

/** 序列化为 runtime.env 文本（编辑键在前，其余既有键原样保留，注释为文档）。 */
function serializeEnvFile(values) {
  const lines = [
    '# dsh-stock-jt 运行配置（由设置页维护，勿手改；机密值不回传明文）',
    'KLINE_SOURCES=' + (values.KLINE_SOURCES || 'vipdoc,tdxmcp'),
    'TDX_ROOT=' + (values.TDX_ROOT || ''),
    'TDX_MCP_TOKEN=' + (values.TDX_MCP_TOKEN || ''),
    'VENV_PYTHON=' + (values.VENV_PYTHON || ''),
  ];
  for (const k of Object.keys(values)) {
    if (EDITABLE_KEYS.includes(k)) continue;
    lines.push(k + '=' + values[k]);
  }
  return lines.join('\n') + '\n';
}

/** GET 载荷：编辑键的当前值（机密脱敏）+ 全键清单（非机密显示值）。 */
function readEnvPayload() {
  const existing = existsSync(RUNTIME_ENV_FILE)
    ? parseEnvFile(readFileSync(RUNTIME_ENV_FILE, 'utf8'))
    : {};
  const values = {};
  for (const k of EDITABLE_KEYS) {
    const raw = existing[k] ?? '';
    values[k] = SECRET_KEYS.includes(k) ? (raw ? '********' : '') : raw;
  }
  return {
    values,
    secretKeys: SECRET_KEYS,
    editableKeys: EDITABLE_KEYS,
    fileExists: existsSync(RUNTIME_ENV_FILE),
    configDir: CONFIG_DIR,
    pythonProbe: probePython(),
  };
}

/** 探测本机可用的 Python/venv 解释器（供设置页显式指定 VENV_PYTHON）。
 * 返回 [{path, version, source}]：source = system（PATH 中的 python / py）/ venv（插件包或仓库 .venv）。
 * 探测失败返回 []（页面显示"未检测到，请手动填写"）。 */
function probePython() {
  const found = [];
  // 1) 插件包 .venv（若有）
  const bundledVenv = join(ROOT, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  if (existsSync(bundledVenv)) {
    const v = pythonVersion(bundledVenv);
    if (v) found.push({ path: bundledVenv, version: v, source: 'venv(包内)' });
  }
  // 2) PATH 中的 python / py（系统解释器）
  for (const candidate of [['python', ['-c', 'import sys; print(sys.executable)']],
                           ['py', ['-3', '-c', 'import sys; print(sys.executable)']]]) {
    const [cmd, args] = candidate;
    const r = spawnSync(cmd, args, { encoding: 'utf8', timeout: 8000 });
    if (r.status === 0 && r.stdout) {
      const p = r.stdout.trim().split(/\r?\n/)[0];
      if (p && existsSync(p) && !found.some((f) => f.path === p)) {
        const v = pythonVersion(p);
        if (v) found.push({ path: p, version: v, source: 'system' });
      }
    }
  }
  return found;
}

function pythonVersion(pythonPath) {
  const r = spawnSync(pythonPath, ['-c', 'import sys; print("%d.%d.%d" % sys.version_info[:3])'], { encoding: 'utf8', timeout: 8000 });
  if (r.status === 0 && r.stdout) return r.stdout.trim().split(/\r?\n/)[0];
  return null;
}

/** POST：接受白名单键的明文（机密键非 '********' 时视为新值），原子写盘。 */
async function writeEnvFromBody(body) {
  const existing = existsSync(RUNTIME_ENV_FILE)
    ? parseEnvFile(readFileSync(RUNTIME_ENV_FILE, 'utf8'))
    : {};
  const next = { ...existing };
  for (const k of EDITABLE_KEYS) {
    if (!(k in body)) continue;
    const v = String(body[k] ?? '').trim();
    if (SECRET_KEYS.includes(k) && v === '********') continue; // 未改动的脱敏占位
    next[k] = v;
  }
  const tmp = RUNTIME_ENV_FILE + '.tmp';
  await writeFile(tmp, serializeEnvFile(next), 'utf8');
  await rename(tmp, RUNTIME_ENV_FILE);
}

// ---- HTTP 小工具（dshmarket 同款语义）----
function sendJson(response, status, payload) {
  response.writeHead(status, {
    'cache-control': 'no-store',
    'content-type': 'application/json; charset=utf-8',
  });
  response.end(JSON.stringify(payload));
}
function sameOrigin(request) {
  const origin = request.headers.origin;
  const host = request.headers.host;
  if (origin === undefined || host === undefined) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
async function readJsonBody(request, maxBytes = 8192) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > maxBytes) throw new Error('request body too large');
    chunks.push(buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}
