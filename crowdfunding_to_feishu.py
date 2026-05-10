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


def write_to_feishu(project):
    """写入单条记录到飞书"""
    category = map_category(project)
    platform = project.get("platform", "Unknown")
    pledged = project.get("pledged", 0)
    backers = project.get("backers_count", 0)
    now = datetime.now(timezone.utc).astimezone()

    record = {
        "项目名": project.get("name", "")[:200],
        "平台": platform,
        "项目链接": project.get("url", ""),
        "众筹金额": int(pledged),
        "支持者数": int(backers),
        "品类": category,
        "状态": "待分析",
        "更新时间": format_datetime(now),
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


def run_kickstarter_scraper():
    """运行 Kickstarter 抓取"""
    print("\n🚀 [1/3] 抓取 Kickstarter...")
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
    print("\n🚀 [2/3] 抓取 Indiegogo...")
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

    # 2. 加载数据
    print("\n🚀 [3/3] 合并数据并写入飞书...")
    ks = load_kickstarter()
    ig = load_indiegogo()
    print(f"📦 Kickstarter: {len(ks)} 个项目")
    print(f"📦 Indiegogo: {len(ig)} 个项目")

    all_projects = ks + ig
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

    # 4. 写入
    success = 0
    failed = 0
    for project in new_projects:
        if write_to_feishu(project):
            success += 1
        else:
            failed += 1

    print(f"\n{'='*50}")
    print(f"✅ 成功: {success}")
    print(f"❌ 失败: {failed}")
    print(f"{'='*50}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-scrape", action="store_true", help="跳过抓取，直接加载本地 JSON 写入")
    args = parser.parse_args()
    main(skip_scrape=args.skip_scrape)
