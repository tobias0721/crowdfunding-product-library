#!/usr/bin/env python3
"""
众筹选品库 - 合并 Kickstarter + Indiegogo 数据写入飞书
支持：去重（只写新项目）、自动添加更新时间
"""

import json
import subprocess
import os
import glob
from datetime import datetime, timezone

BASE_TOKEN = "YVvgbBsyVaMFz0sbOFhcO9Jln7g"
TABLE_ID = "tblmUS3FqJBwvOUd"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# 需要过滤掉的品类（与电商相关度低）
# 规则：
#   - 多词关键词（含空格）使用子串匹配
#   - 单词关键词使用完整单词匹配（避免 "art" 误杀 "smart"）
#   - URL路径使用 /keyword/ 匹配
#   - 【2026-05-11】卡牌/桌游/塔罗/骰子/RPG 类暂不过滤，保留进表
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
    # 艺术/绘画（仅匹配完整短语，避免误杀）
    "painting collection", "art book", "photo book", "photobook",
    # 3D打印模型
    "stl files", "3d printable", "miniature", "terrain",
    # 中文关键词
    "书籍", "漫画", "小说", "摄影集", "绘画", "艺术书",
    "音乐", "专辑", "电影",
    "食物", "食谱", "饼干", "糕点", "餐厅",
}

CATEGORY_MAP = {
    "產品設計": "科技",
    "設計": "科技",
    "科技": "科技",
    "小工具": "科技",
    "DIY": "科技",
    "家居": "家居",
    "食品": "其他",
    "飲料": "其他",
    "遊戲": "其他",
    "桌上遊戲": "其他",
    "撲克牌": "其他",
    "圖畫小說": "其他",
    "文學空間": "其他",
    "美食車": "其他",
    "STL": "其他",
    "服飾": "其他",
    "繪畫": "其他",
    "電玩": "其他",
    "聲音": "其他",
}


def run_lark_cli(args):
    """运行 lark-cli 并返回解析后的 JSON"""
    cmd = ["lark-cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"lark-cli 输出解析失败: {result.stdout[:200]}")
        return {"ok": False, "error": result.stderr[:200]}


def get_existing_urls():
    """获取飞书表格中已有的所有项目链接"""
    existing = set()
    has_more = True
    offset = 0
    limit = 500

    print("🔍 查询飞书已有项目...")

    while has_more:
        resp = run_lark_cli([
            "base", "+record-list",
            "--base-token", BASE_TOKEN,
            "--table-id", TABLE_ID,
            "--limit", str(limit),
            "--offset", str(offset),
        ])

        if not resp.get("ok"):
            print(f"⚠️ 查询失败: {resp}")
            break

        data = resp.get("data", {}).get("data", [])
        if not data:
            break

        # field_id_list 中项目链接的索引
        field_ids = resp.get("data", {}).get("field_id_list", [])
        url_idx = None
        for i, fid in enumerate(field_ids):
            if fid == "fldZRBnwFo":
                url_idx = i
                break

        if url_idx is None:
            print("⚠️ 找不到项目链接字段")
            break

        for record in data:
            url_val = record[url_idx]
            if isinstance(url_val, str):
                existing.add(url_val.strip())

        offset += len(data)
        has_more = len(data) == limit

    print(f"📋 已有项目: {len(existing)} 个")
    return existing


def should_filter(project):
    """判断项目是否应该被过滤（与电商相关度低）
    规则：
      - 多词关键词（含空格）使用子串匹配（名称/品类/URL）
      - 英文单词关键词使用完整单词匹配（避免 "art" 误杀 "smart"）
      - 中文关键词使用子串匹配（中文无空格分词）
      - URL路径使用 /keyword/ 匹配
    """
    import re

    name = project.get("name", "").lower()
    cat = (project.get("category", "") or project.get("sub_category", "")).lower()
    url = project.get("url", "").lower()

    # 将名称拆分为单词（仅用于英文完整单词匹配）
    name_words = re.findall(r'[a-zA-Z]+', name)

    for keyword in FILTERED_CATEGORIES:
        kw_lower = keyword.lower()

        # 多词关键词（含空格）使用子串匹配
        if ' ' in kw_lower:
            if kw_lower in name or kw_lower in cat or kw_lower in url:
                return True, keyword
            continue

        # 中文关键词：子串匹配
        if re.search(r'[\u4e00-\u9fff]', kw_lower):
            if kw_lower in name or kw_lower in cat:
                return True, keyword
            continue

        # 英文单词：完整单词匹配（名称分词）
        if kw_lower in name_words:
            return True, keyword
        # 品类匹配
        if kw_lower in cat:
            return True, keyword
        # URL路径匹配
        if f'/{kw_lower}/' in url:
            return True, keyword

    return False, None


def map_category(project):
    """映射品类"""
    platform = project.get("platform", "")
    cat = project.get("category", "") or project.get("sub_category", "")

    if platform == "Kickstarter":
        return CATEGORY_MAP.get(cat, "其他")

    url = project.get("url", "")
    if "technology" in url or "design" in url:
        return "科技"
    if "home" in url or "outdoor" in url:
        return "家居"
    return "其他"


def format_datetime(dt):
    """格式化为飞书 datetime 接受的格式"""
    return dt.strftime("%Y/%m/%d %H:%M")


def get_project_created_date(project):
    """获取项目创建时间
    Kickstarter: 使用 launched_at 时间戳
    Indiegogo: 使用当前日期（无创建时间字段）
    """
    platform = project.get("platform", "")
    launched_at = project.get("launched_at")

    if platform == "Kickstarter" and launched_at:
        try:
            dt = datetime.fromtimestamp(launched_at)
            return dt.strftime("%Y/%m/%d")
        except (TypeError, ValueError, OSError):
            pass

    # Indiegogo 或无法解析时，使用当前日期
    return datetime.now(timezone.utc).astimezone().strftime("%Y/%m/%d")


def write_to_feishu(project):
    """写入单条记录到飞书"""
    # 先检查是否需要过滤
    should_skip, keyword = should_filter(project)
    if should_skip:
        print(f"  🚫 已过滤 [{project.get('platform', 'Unknown')}] {project['name'][:50]}... (原因: {keyword})")
        return "filtered"

    category = map_category(project)
    platform = project.get("platform", "Unknown")
    pledged = project.get("pledged", 0)
    backers = project.get("backers_count", 0)
    created_date = get_project_created_date(project)

    record = {
        "项目名": project.get("name", "")[:200],
        "平台": platform,
        "项目链接": project.get("url", ""),
        "众筹金额": int(pledged),
        "支持者数": int(backers),
        "品类": category,
        "状态": "待分析",
        "更新时间": created_date,
    }

    cmd = [
        "lark-cli", "base", "+record-upsert",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--json", json.dumps(record, ensure_ascii=False),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"  ✅ [{platform}] {project['name'][:50]}")
        return True
    else:
        err = result.stderr[:150]
        print(f"  ❌ [{platform}] {project['name'][:50]} | {err}")
        return False


# 兼容旧调用：返回布尔值时过滤的项目也算"成功"（未写入但已处理）
def write_to_feishu_compat(project):
    """兼容旧接口，过滤的项目返回 True（表示已处理）"""
    result = write_to_feishu(project)
    return result if isinstance(result, bool) else True


def load_kickstarter():
    """加载最新的 Kickstarter 数据"""
    files = glob.glob(os.path.join(OUTPUT_DIR, "kickstarter_projects_*.json"))
    if not files:
        return []
    latest = max(files)
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)


def load_indiegogo():
    """加载 Indiegogo 数据"""
    path = os.path.join(OUTPUT_DIR, "indiegogo_data.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_makuake():
    """加载最新的 Makuake 数据"""
    files = glob.glob(os.path.join(OUTPUT_DIR, "makuake_projects_*.json"))
    if not files:
        return []
    latest = max(files)
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)


def load_wadiz():
    """加载最新的 Wadiz 数据"""
    files = glob.glob(os.path.join(OUTPUT_DIR, "wadiz_projects_*.json"))
    if not files:
        return []
    latest = max(files)
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)


def run_kickstarter_scraper():
    """运行 Kickstarter 抓取"""
    print("\n🚀 [1/5] 抓取 Kickstarter...")
    script = os.path.join(OUTPUT_DIR, "kickstarter_scraper.py")
    result = subprocess.run(
        ["python3", script],
        capture_output=True,
        text=True,
        cwd=OUTPUT_DIR,
    )
    print(result.stdout[-800:] if len(result.stdout) > 800 else result.stdout)
    if result.returncode != 0:
        print(f"⚠️ Kickstarter 抓取异常: {result.stderr[-300:]}")
        return False
    return True


def run_indiegogo_scraper():
    """运行 Indiegogo 抓取"""
    print("\n🚀 [2/5] 抓取 Indiegogo...")
    script = os.path.join(OUTPUT_DIR, "indiegogo-stealth.js")
    result = subprocess.run(
        ["node", script],
        capture_output=True,
        text=True,
        cwd=OUTPUT_DIR,
        env={**os.environ, "OUTPUT_JSON": os.path.join(OUTPUT_DIR, "indiegogo_data.json")},
    )
    print(result.stdout[-800:] if len(result.stdout) > 800 else result.stdout)
    if result.returncode != 0:
        print(f"⚠️ Indiegogo 抓取异常: {result.stderr[-300:]}")
        return False
    return True


def run_makuake_scraper():
    """运行 Makuake 抓取"""
    print("\n🚀 [3/5] 抓取 Makuake...")
    script = os.path.join(OUTPUT_DIR, "makuake_scraper.py")
    result = subprocess.run(
        ["python3", script],
        capture_output=True,
        text=True,
        cwd=OUTPUT_DIR,
    )
    print(result.stdout[-800:] if len(result.stdout) > 800 else result.stdout)
    if result.returncode != 0:
        print(f"⚠️ Makuake 抓取异常: {result.stderr[-300:]}")
        return False
    return True


def run_wadiz_scraper():
    """运行 Wadiz 抓取"""
    print("\n🚀 [4/5] 抓取 Wadiz...")
    script = os.path.join(OUTPUT_DIR, "wadiz_scraper.py")
    result = subprocess.run(
        ["python3", script],
        capture_output=True,
        text=True,
        cwd=OUTPUT_DIR,
    )
    print(result.stdout[-800:] if len(result.stdout) > 800 else result.stdout)
    if result.returncode != 0:
        print(f"⚠️ Wadiz 抓取异常: {result.stderr[-300:]}")
        return False
    return True


def main(skip_scrape=False):
    """
    主入口
    skip_scrape: 如果为 True，跳过抓取步骤，直接加载本地已有 JSON 写入
    """
    print(f"\n{'='*60}")
    print(f"📦 众筹选品库自动更新")
    print(f"{'='*60}")

    # 1. 抓取
    if not skip_scrape:
        run_kickstarter_scraper()
        run_indiegogo_scraper()
        run_makuake_scraper()
        run_wadiz_scraper()

    # 2. 加载数据
    print("\n🚀 [5/5] 合并数据并写入飞书...")
    ks = load_kickstarter()
    ig = load_indiegogo()
    mk = load_makuake()
    wz = load_wadiz()
    print(f"📦 Kickstarter: {len(ks)} 个项目")
    print(f"📦 Indiegogo: {len(ig)} 个项目")
    print(f"📦 Makuake: {len(mk)} 个项目")
    print(f"📦 Wadiz: {len(wz)} 个项目")

    all_projects = ks + ig + mk + wz
    if not all_projects:
        print("❌ 没有数据可写入")
        return

    # 3. 去重（飞书已有）
    existing_urls = get_existing_urls()
    new_projects = []
    seen_urls = set()

    for p in all_projects:
        url = p.get("url", "").strip()
        if not url:
            continue
        if url in existing_urls or url in seen_urls:
            continue
        seen_urls.add(url)
        new_projects.append(p)

    print(f"🆕 新项目: {len(new_projects)} 个")

    if not new_projects:
        print("✅ 没有新项目，无需更新")
        return

    # 按金额排序
    new_projects.sort(key=lambda x: x.get("pledged", 0), reverse=True)

    # 4. 写入（带过滤）
    success = 0
    failed = 0
    filtered = 0
    for project in new_projects:
        result = write_to_feishu(project)
        if result == True:
            success += 1
        elif result == "filtered":
            filtered += 1
        else:
            failed += 1

    print(f"\n{'='*50}")
    print(f"✅ 成功写入: {success}")
    print(f"🚫 已过滤: {filtered}")
    print(f"❌ 失败: {failed}")
    print(f"{'='*50}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-scrape", action="store_true", help="跳过抓取，直接加载本地 JSON 写入")
    args = parser.parse_args()
    main(skip_scrape=args.skip_scrape)
