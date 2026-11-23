# Antigravity Usage Monitor (`usage-monitor`)

[English](README.md) | 简体中文

面向 Google Antigravity 的**零依赖、零 CDP 侵入**原生插件：提供**共享池闭环分账**、**1 分钟去噪全局水位监控**、**安静窗口分模型单价自动校准**以及**中英双语 Extensions 侧栏仪表盘**。

尤其适合多设备共用同一账号、与队友合租订阅池，或者想彻底看清服务端预扣抖动、休眠期间外部扣额以及各模型实际耗额比例的用户。

---

## 核心特性

- **共享池闭环分账（本机 vs 外部）**：结合对话级 Hook（`PreInvocation` / `Stop` + `transcript.jsonl`）与 Sidecar 每分钟本地 Language Server RPC 采样（`RetrieveUserQuotaSummary`），准确拆出 **我用的**、**别人用的(电脑开着时)**、**与你同时用(并发超额)** 以及 **电脑休眠期间**。
- **两阶段水位去噪器**：自动剔除服务端 `resetsAt` 倒退旧副本读数、修复 1–2 分钟孤立下探，并通过窗口内后缀最小值擦除服务端预扣脉冲/回退噪点，同时不丢失真实睡眠跨天增量。
- **安静窗口黄金样本 + 混合轮自动校准**：按 `In:Cache:Out = 1 : 0.05 : 5` 自动校准各模型每 `1M` 等效输入所耗周额度%，Pass-1 自动排除含 `search_web`/报错的轮次，Pass-2 从干净混合轮中反解未校准模型单价，并支持无损 `--backfill` 补录历史逐 step 模型标记。
- **多订阅 & 多配额档位兼容**：
  - 动态渲染宿主返回的全部配额桶（含 `Gemini 5h/Weekly`、`Argon Weekly`、`Claude/GPT 5h/Weekly` 及未来新增桶）。
  - 自动识别按量付费账号（`GetUserStatus`），仅保留本地 Token 账本而不强行展示空白池。
  - 从实测样本中动态拟合 `5h : 周` 比例，不再假定所有账号都是固定 `4:1`。
- **零 CDP、零第三方依赖**：纯 Python `3.9+` 标准库实现，不改 Antigravity 启动参数、不依赖外部 CLI 或包管理器。

---

## 安装指南

**环境要求**：Python `3.9+` 与 Antigravity 桌面端（`2.32+`，已在 `2.34.0` 实测）。

### macOS / Linux

```bash
git clone https://github.com/lenze374/Agy-usagemonitor.git
cd Agy-usagemonitor
chmod +x install.sh uninstall.sh
sh install.sh --with-cli
```

（若只需要侧栏插件和自动记账，不往 `~/.local/bin` 安装 `agy-usage` 命令行，可去掉 `--with-cli`。）

### Windows (PowerShell 或双击)

```powershell
git clone https://github.com/lenze374/Agy-usagemonitor.git
cd Agy-usagemonitor
.\install.ps1 --with-cli
```

或者直接双击 `install.bat`。

### 在 Antigravity 中启用

1. 打开 Antigravity → **Extensions / Plugins**。
2. 启用 **`usage-monitor` (`Antigravity Usage Monitor`)**。
3. 在侧栏打开 **UsageMonitor** 面板即可实时查看。

---

## 面板功能说明

1. **总览**：
   - **当前剩余额度**：卡片主数值显示 **3 位小数**（`XXX.XXX%`），健康度自动着色，消耗统一以 `-X.XXX%` 表示。
   - **这周谁用了多少？**：我用的 / 别人用的 / 电脑休眠期间占比条与细分。
   - **最近别人啥时候在用**（独立 `近24小时 / 近7天` 切换）：捕获静置、休眠以及与本机同时发生的并发超额消耗。
   - **我的简明账单**：今日与本周期汇总结算。
2. **趋势与分账**：
   - **额度剩余走势**：可交互 SVG 曲线（静置灰带、休眠斜纹桥接、周期重置竖线，支持叠加原始未过滤噪声曲线对比）。
   - **每小时 / 每天谁用了多少**：堆叠归因柱状图。
   - **每次扣额记录**：已剔除去噪归零的跳点假象，仅保留真实重置与有效扣额。
3. **我的用量**：
   - 各模型校准单价（`%/1M 等效`）、缓存命中率与最近 25 组对话明细（自动折叠并发子代理波次）。
4. **设置与诊断**：
   - 开关对话级自动记账 Hook、一键补录缺失 Token、**内存生成中/英 `.txt` 文本摘要**（支持一键复制或浏览器下载，后台不写任何日报文件到磁盘）、切换中英文界面、查看运行环境与 `5h:周` 校准诊断信息。

---

## 隐私与数据存储

全部采集与计算均在本地完成，`ANTIGRAVITY_CSRF_TOKEN` 仅在内存中用于访问本机 `127.0.0.1` 语言服务接口，绝不落盘或外发。

运行数据统一保存在系统标准用户数据目录（与插件源码完全隔离）：
- **macOS / Linux**：`~/.local/share/agy-usage/`（或 `$XDG_DATA_HOME/agy-usage/`）
- **Windows**：`%LOCALAPPDATA%\agy-usage\`
- 可通过环境变量 `AGY_USAGE_DATA_DIR` 自定义目录。

---

## 卸载

```bash
# macOS / Linux（默认保留你的历史账本与监控日志）
sh uninstall.sh

# Windows PowerShell
.\uninstall.ps1
```

如需连同历史账本与监控日志一并清除，可追加 `--purge-data`。

## License

[MIT](LICENSE)
