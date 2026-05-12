# 众筹选品库自动更新

自动抓取 Kickstarter、Indiegogo、Makuake（日本）、Wadiz（韩国）四个众筹平台的项目，过滤掉与电商无关的品类，去重后写入飞书「众筹选品库」多维表格。

---

## 支持的4个平台

| 平台 | 国家 | 页面类型 | 数据完整度 | 反爬强度 |
|------|------|---------|-----------|---------|
| Kickstarter | 美国 | SSR | ⭐⭐⭐ 金额/支持者/创建时间/品类全有 | 中等 |
| Indiegogo | 美国 | SSR + JS Hydration | ⭐⭐ 金额/达成率/品类有，支持者/创建时间不全 | 中等 |
| Makuake | 日本 | SSR | ⭐⭐ 金额/达成率/剩余天数有，支持者/创建时间需估算 | 低 |
| Wadiz | 韩国 | SPA（重度） | ⭐ 仅达成率 + 链接，金额/支持者需进详情页 | 高 |

---

## 前置依赖

1. `playwright-scraper-skill` 已安装（Stealth 模式脚本路径: `~/.workbuddy/skills/playwright-scraper-skill/scripts/playwright-stealth.js`）
2. `lark-cli` 已安装且已授权（路径: `~/.npm-global/bin/lark-cli`）
3. Node.js + Python3 环境可用
4. 飞书多维表格: Base Token `YVvgbBsyVaMFz0sbOFhcO9Jln7g`, Table ID `tblmUS3FqJBwvOUd`

---

## 完整工作流

### 方式1：一键运行（推荐）

```bash
cd /Users/tobias/WorkBuddy/Claw
python3 crowdfunding_to_feishu.py
```

自动抓取 4 个平台 → 合并去重 → 过滤无关品类 → 写入飞书。

### 方式2：只写入（不重新抓取）

```bash
python3 crowdfunding_to_feishu.py --skip-scrape
```

### 方式3：单独运行某个平台

```bash
# Kickstarter（翻页抓取10页，过滤2025-03-01以后项目）
python3 kickstarter_scraper.py

# Indiegogo（多分类页抓取）
OUTPUT_JSON=./indiegogo_data.json node indiegogo-stealth.js

# Makuake（多分类页：all/technology/home/fashion）
python3 makuake_scraper.py

# Wadiz（首页抓取，反爬强，需缓存fallback）
python3 wadiz_scraper.py
```

---

## 关键文件

| 文件 | 说明 |
|------|------|
| `kickstarter_scraper.py` | Kickstarter 翻页抓取 + JSON 解析 |
| `indiegogo-stealth.js` | Indiegogo Playwright Stealth 抓取 |
| `indiegogo_scraper.py` | Indiegogo 备用抓取（Python版） |
| `makuake_scraper.py` | Makuake 多分类页抓取 |
| `wadiz_scraper.py` | Wadiz SPA 抓取（含缓存fallback） |
| `crowdfunding_to_feishu.py` | 合并 → 去重 → 过滤 → 写入飞书 |
| `SKILL.md` | WorkBuddy Skill 文档（完整使用指南） |

---

## 过滤规则

**已过滤（不写入飞书）：**
- 书籍/文学/漫画/小说/摄影集
- 音乐/专辑/唱片
- 电影/视频/短片/纪录片
- App/软件/平台
- 食物/餐饮/食谱
- 3D打印模型/STL文件

**保留（不过滤）：**
- 卡牌/桌游/塔罗/骰子/RPG ✅
- 科技/电子/家居/穿戴/运动等实物产品 ✅

> 完整过滤逻辑和品类映射见 `SKILL.md` 或 `crowdfunding_to_feishu.py` 中的 `FILTERED_CATEGORIES`

---

## 飞书表格字段

- `项目名` (text)
- `平台` (select: Kickstarter / Indiegogo / Makuake / Wadiz)
- `项目链接` (text) — 去重键
- `众筹金额` (number)
- `支持者数` (number)
- `目标达成率` (number)
- `品类` (select: 科技 / 家居 / 其他)
- `状态` (select: 待分析 / ...)
- `项目创建时间` (datetime)

---

## 自动化配置

- 频率: 每周六 13:00
- Prompt: "运行众筹选品库自动更新：先抓取 Kickstarter、Indiegogo、Makuake、Wadiz 新项目，然后合并去重写入飞书多维表格"
- CWD: `/Users/tobias/WorkBuddy/Claw`

---

## 历史踩坑

1. **Indiegogo Cloudflare 拦截** → 必须用 Playwright Stealth
2. **Indiegogo 无 SSR 数据** → `window.__INITIAL_STATE__` 不含 campaigns，改为 DOM 启发式提取
3. **Wadiz 反爬** → 多次请求返回空页，fallback 到本地最大缓存 HTML
4. **Wadiz 列表页无金额** → SPA 动态渲染，初始 HTML 里没有金额/支持者/创建时间
5. **中文过滤不生效** → 原用单词分词匹配，中文无空格分词，改为子串匹配
6. **Kickstarter 时间过滤** → `launched_at` 是 UTC 时间戳，与 `1740787200`（2025-03-01 00:00 UTC）比较
