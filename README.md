# 众筹选品库自动更新

自动抓取 Kickstarter 和 Indiegogo 的众筹项目，去重后写入飞书「众筹选品库」多维表格，仅追加新项目。

## 触发条件

- 用户说"更新众筹选品库"、"抓一下众筹项目"、"众筹数据同步"
- 每周六下午 1 点自动运行（automation）

## 前置依赖

1. `playwright-scraper-skill` 已安装（Stealth 模式脚本路径: `~/.workbuddy/skills/playwright-scraper-skill/scripts/playwright-stealth.js`）
2. `lark-cli` 已安装且已授权（路径: `~/.npm-global/bin/lark-cli`）
3. Node.js + Python3 环境可用
4. 飞书多维表格: Base Token `YVvgbBsyVaMFz0sbOFhcO9Jln7g`, Table ID `tblmUS3FqJBwvOUd`

## 工作流

### Step 1: 抓取 Kickstarter

```bash
cd /Users/tobias/WorkBuddy/Claw
python3 kickstarter_scraper.py
```

- 翻页抓取 10 页，过滤 2025-03-01 以后上线的成功项目
- 输出: `kickstarter_projects_YYYYMMDD_HHMMSS.json`
- 核心: HTML 中 `data-project` 属性 → `html.unescape()` → `json.loads()`

### Step 2: 抓取 Indiegogo

```bash
cd /Users/tobias/WorkBuddy/Claw
OUTPUT_JSON=./indiegogo_data.json node indiegogo-stealth.js
```

- 抓取 4 个分类页（technology / home / design / outdoor）
- Playwright Stealth + 滚动懒加载 + DOM 启发式提取
- 输出: `indiegogo_data.json`

### Step 3: 合并去重写入飞书

```bash
cd /Users/tobias/WorkBuddy/Claw
python3 crowdfunding_to_feishu.py
```

行为:
1. 先查询飞书已有全部记录的「项目链接」字段
2. 加载 Kickstarter + Indiegogo JSON
3. 按 URL 去重（已有链接跳过）
4. 按众筹金额降序排列
5. 逐条写入，每条附带「更新时间」字段（当前时间）
6. 只追加新项目，不更新旧记录

### 手动跳过抓取（仅写入本地已有 JSON）

```bash
python3 crowdfunding_to_feishu.py --skip-scrape
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `kickstarter_scraper.py` | Kickstarter 翻页抓取 + 解析 |
| `indiegogo-stealth.js` | Indiegogo Stealth 抓取 |
| `crowdfunding_to_feishu.py` | 合并 → 去重 → 写入飞书 |

## 飞书表格字段

- `项目名` (text)
- `平台` (select: Kickstarter / Indiegogo)
- `项目链接` (text) — 去重键
- `众筹金额` (number)
- `支持者数` (number)
- `品类` (select: 科技 / 家居 / 其他)
- `状态` (select: 待分析 / ...)
- `更新时间` (datetime) — 新增

## 自动化配置

- 频率: 每周六 13:00 (RRULE: FREQ=WEEKLY;BYDAY=SA;BYHOUR=13;BYMINUTE=0)
- Prompt: "运行众筹选品库自动更新：先抓取 Kickstarter 和 Indiegogo 新项目，然后合并去重写入飞书多维表格"
- CWD: `/Users/tobias/WorkBuddy/Claw`

## 历史踩坑

1. **Indiegogo Cloudflare 拦截** → 必须用 Playwright Stealth（禁用 `AutomationControlled` + 隐藏 `navigator.webdriver`）
2. **Indiegogo 无 SSR 数据** → `window.__INITIAL_STATE__` 不含 campaigns，改为 DOM 启发式提取（链接 + 货币符号向上遍历父元素）
3. **Backers 解析 `4.9k` → 4** → `int()` 截断，应先用 `float()` 再乘 1000
4. **飞书写入重复** → 先全量查询已有 URL，过滤后再写入，避免重复记录
5. **Kickstarter 时间过滤** → `launched_at` 是 UTC 时间戳，与 `1740787200`（2025-03-01 00:00 UTC）比较
