# Crowdfunding Scraper — 众筹平台选品抓取

抓取 Kickstarter、Indiegogo、Makuake（日本）、Wadiz（韩国）四个众筹平台的项目数据，过滤掉与电商无关的品类，写入飞书多维表格。

---

## 依赖

- **playwright-scraper-skill** — 已安装的 Stealth 模式浏览器抓取
- **lark-cli** — 飞书多维表格操作（base +record-list / +record-upsert）
- Python 3.9+，Node.js（用于 Playwright）

---

## 支持的4个平台

| 平台 | 国家 | 页面类型 | 数据完整度 | 反爬强度 |
|------|------|---------|-----------|---------|
| Kickstarter | 美国 | SSR | ⭐⭐⭐ 金额/支持者/创建时间/品类全有 | 中等 |
| Indiegogo | 美国 | SSR + JS Hydration | ⭐⭐ 金额/达成率/品类有，支持者/创建时间不全 | 中等 |
| Makuake | 日本 | SSR | ⭐⭐ 金额/达成率/剩余天数有，支持者/创建时间需估算 | 低 |
| Wadiz | 韩国 | SPA（重度） | ⭐ 仅达成率 + 链接，金额/支持者需进详情页 | 高 |

### 各平台抓取要点

**Kickstarter**
- 翻页抓取（page=1~10），每页 `data-project="..."` 属性嵌入 JSON
- 过滤：只保留 2025-03-01 之后上线的项目（`launched_after` 参数 + 时间戳校验）
- 字段最完整，直接解析 JSON 即可获得所有数据

**Indiegogo**
- 从 `window.__INITIAL_STATE__` 或 `__BOOTSTRAP__` 中递归提取 `campaigns` 数组
- 多 URL 抓取：technology / home / all（finished）
- 金额字段可能是 `funds_raised_amount` 或 `collected_funds`

**Makuake**
- 列表页为纯 SSR，从 `<li>` 卡片中提取标题、金额（`￥`）、天数（`日`）、达成率（`%`）
- 抓取多个分类：`/discover/all`, `/technology`, `/home`, `/fashion`
- 无支持者数，按 `amount / 5000` 估算

**Wadiz**
- 重度 SPA，初始 HTML 只有 `data-ec-id` + `data-ec-name` + 达成率
- 反爬强，多次请求返回空页。策略：
  1. Playwright 渲染 20 秒等 JS 加载
  2. 如果 HTML < 500KB，fallback 到本地缓存的最大 HTML 文件
- 金额/支持者/创建时间 **列表页拿不到**，需进详情页或接受缺失

---

## 过滤规则

### 不需要的品类（与电商选品无关）

```python
FILTERED_CATEGORIES = {
    # 书籍/文学/漫画
    "book", "books", "comic", "comics", "novel", "literature", "magazine",
    "manga", "graphic novel", "photobook", "art book", "photo book",
    # App/软件/平台
    "app", "application", "software", "platform",
    # 音乐/专辑/唱片
    "music", "album", "ep", "single", "record", "vinyl", "soundtrack", "lp",
    # 电影/视频/短片
    "film", "movie", "short film", "documentary", "podcast", "video",
    # 食物/餐饮
    "food", "cooking", "recipe", "restaurant", "bakery", "cookie", "pastry", "cuisine",
    # 3D打印模型
    "stl files", "3d printable", "miniature", "terrain",
    # 中文关键词
    "书籍", "漫画", "小说", "摄影集", "绘画", "艺术书",
    "音乐", "专辑", "电影",
    "食物", "食谱", "饼干", "糕点", "餐厅",
}
```

**注意**：
- 卡牌/桌游/塔罗/骰子/RPG **不过滤**（保留进表）
- 英文单词用**完整单词匹配**（避免 "art" 误杀 "smart"）
- 中文关键词用**子串匹配**（中文无空格分词）
- 多词关键词（含空格）用**子串匹配**

### 匹配逻辑

```python
def should_filter(project):
    name = project.get("name", "").lower()
    cat = (project.get("category", "") or "").lower()
    url = project.get("url", "").lower()
    name_words = re.findall(r'[a-zA-Z]+', name)  # 仅用于英文完整单词匹配

    for keyword in FILTERED_CATEGORIES:
        kw = keyword.lower()

        # 多词关键词：子串匹配
        if ' ' in kw:
            if kw in name or kw in cat or kw in url:
                return True, keyword
            continue

        # 中文关键词：子串匹配
        if re.search(r'[\u4e00-\u9fff]', kw):
            if kw in name or kw in cat:
                return True, keyword
            continue

        # 英文单词：完整单词匹配
        if kw in name_words:
            return True, keyword
        if kw in cat:
            return True, keyword
        if f'/{kw}/' in url:
            return True, keyword

    return False, None
```

---

## 品类映射

```python
CATEGORY_MAP = {
    "產品設計": "科技", "設計": "科技", "科技": "科技",
    "小工具": "科技", "DIY": "科技",
    "家居": "家居",
    "服飾": "其他",
    # URL 关键词映射
    # technology / design → 科技
    # home / outdoor → 家居
    # 其余 → 其他
}
```

---

## 飞书写入

### 配置

```python
BASE_TOKEN = "YVvgbBsyVaMFz0sbOFhcO9Jln7g"
TABLE_ID = "tblmUS3FqJBwvOUd"
```

### 流程

1. **抓取4个平台** → 生成各自 JSON
2. **加载合并** → `ks + ig + mk + wz`
3. **查询飞书已有链接** → 去重
4. **过滤不需要的品类** → `should_filter()`
5. **品类映射** → `map_category()`
6. **写入飞书** → `lark-cli base +record-upsert`

### 写入字段

| 飞书字段 | 来源 |
|---------|------|
| 项目名 | `project['name']` |
| 平台 | `project['platform']` |
| 项目链接 | `project['url']` |
| 众筹金额 | `project['pledged']` |
| 支持者数 | `project['backers_count']` |
| 目标达成率 | `project['pledge_percent']` |
| 品类 | `map_category(project)` |
| 状态 | "待分析" |
| 项目创建时间 | Kickstarter 用 `launched_at`，其他 fallback 当天 |

### 运行命令

```bash
# 完整流程：抓取 + 写入
python3 crowdfunding_to_feishu.py

# 跳过抓取，只用本地已有 JSON 写入
python3 crowdfunding_to_feishu.py --skip-scrape
```

---

## 关键设计决策

### 1. 时间过滤

- Kickstarter/Indiegogo：只保留 **2025-03-01 之后**上线的项目（避免老旧项目）
- Makuake/Wadiz：列表页无创建时间，不过滤

### 2. Wadiz 反爬策略

```python
if len(html_content) < 500000:
    # 页面未完全加载，fallback 到缓存的最大 HTML
    cached_files = [(f, os.path.getsize(f)) for f in os.listdir(OUTPUT_DIR)
                    if f.startswith('wadiz_') and f.endswith('.html')]
    cached_files.sort(key=lambda x: x[1], reverse=True)
    if cached_files:
        html_content = open(cached_files[0][0]).read()
```

### 3. 数据缺失处理

| 平台 | 缺失字段 | 处理方式 |
|------|---------|---------|
| Makuake | backers_count | `amount // 5000` 估算 |
| Makuake/Wadiz | launched_at / deadline | `None`（飞书存当天日期） |
| Wadiz | pledged / goal / backers | `0`（列表页拿不到） |
| Indiegogo | launched_at | 当天日期 fallback |

---

## 文件结构

```
workspace/
├── kickstarter_scraper.py      # Kickstarter 抓取
├── indiegogo_scraper.py        # Indiegogo 抓取（备用，JS 版更可靠）
├── indiegogo-stealth.js        # Indiegogo 抓取（主用）
├── makuake_scraper.py          # Makuake 抓取
├── wadiz_scraper.py            # Wadiz 抓取
├── crowdfunding_to_feishu.py   # 合并 + 过滤 + 飞书写入（主入口）
└── *.json / *.html             # 抓取缓存文件
```

---

## 使用示例

```python
# 单独运行某个平台
python3 kickstarter_scraper.py
python3 makuake_scraper.py
python3 wadiz_scraper.py

# 完整流程：抓取全部 + 写入飞书
python3 crowdfunding_to_feishu.py

# 只写入（不重新抓取）
python3 crowdfunding_to_feishu.py --skip-scrape
```

---

## 常见问题

**Q: Wadiz 为什么金额和支持者都是 0？**  
A: Wadiz 列表页是 SPA，金额和支持者由 JS 动态渲染，初始 HTML 里没有。解决方案：进详情页抓取（需 288 次请求，建议加缓存）。

**Q: "更新时间"字段为什么有些是当天日期？**  
A: 只有 Kickstarter 返回 `launched_at` 时间戳，其他平台列表页没有这个字段，fallback 到当天日期。如果要准确时间，需要进详情页抓取。

**Q: 过滤规则里为什么没有卡牌/桌游？**  
A: 用户明确保留卡牌/桌游/塔罗/骰子/RPG 类，不过滤。

**Q: 3D 打印模型为什么保留了？**  
A: 过滤词是 `stl files`（多词）和 `miniature`（英文），中文 "3D打印模型" 没被命中。如需过滤，需添加中文关键词。
