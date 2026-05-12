#!/usr/bin/env python3
"""
Indiegogo 众筹项目抓取器
基于 playwright-scraper-skill 的 Stealth 模式
"""

import json
import re
import html
import subprocess
import os
import sys
from datetime import datetime

STEALTH_SCRIPT = os.path.expanduser("~/.workbuddy/skills/playwright-scraper-skill/scripts/playwright-stealth.js")
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2025-03-01 00:00:00 UTC
MARCH_1_2025_TS = 1740787200


def fetch_page(url, wait_time=12000):
    """使用 Playwright Stealth 抓取页面"""
    env = os.environ.copy()
    env["SAVE_HTML"] = "true"
    env["WAIT_TIME"] = str(wait_time)
    env["SCREENSHOT_PATH"] = os.path.join(OUTPUT_DIR, f"indiegogo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

    result = subprocess.run(
        ["node", STEALTH_SCRIPT, url],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(STEALTH_SCRIPT),
        env=env
    )

    html_file = None
    for line in result.stdout.split('\n'):
        if 'HTML 已儲存:' in line or 'HTML saved:' in line:
            html_file = line.split(': ')[-1].strip()
            break

    if not html_file:
        screenshot_path = env["SCREENSHOT_PATH"]
        html_file = screenshot_path.replace('.png', '.html')

    return html_file


def parse_projects(html_content):
    """从 HTML 中解析 Indiegogo 项目数据"""
    projects = []

    # 方法1: 尝试从 script 标签中的 JSON 提取 (SSR/ hydration 数据)
    # Indiegogo 通常把项目数据放在 window.IGOG ... 或 __INITIAL_STATE__ 里
    patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
        r'window\.__BOOTSTRAP__\s*=\s*({.+?});',
        r'"campaigns":\s*(\[.+?\])',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, html_content, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                # 递归查找 campaigns 数组
                def find_campaigns(obj):
                    if isinstance(obj, list):
                        for item in obj:
                            if isinstance(item, dict) and 'title' in item and 'funds_raised_amount' in item:
                                return obj
                            result = find_campaigns(item)
                            if result:
                                return result
                    elif isinstance(obj, dict):
                        for k, v in obj.items():
                            if k in ('campaigns', 'explore_campaigns', 'items', 'results') and isinstance(v, list):
                                for item in v:
                                    if isinstance(item, dict) and ('title' in item or 'name' in item):
                                        return v
                            result = find_campaigns(v)
                            if result:
                                return result
                    return None

                campaigns = find_campaigns(data)
                if campaigns:
                    for c in campaigns:
                        if not isinstance(c, dict):
                            continue
                        title = c.get('title') or c.get('name', '')
                        if not title:
                            continue

                        # 金额处理
                        pledged = c.get('funds_raised_amount', 0) or c.get('collected_funds', 0) or 0
                        goal = c.get('funding_goal', 0) or c.get('goal', 0) or 1
                        backers = c.get('contributions_count', 0) or c.get('backers_count', 0) or 0

                        # 时间
                        launched = c.get('funding_started_at') or c.get('created_at') or c.get('launch_date')
                        launched_ts = None
                        if launched:
                            try:
                                if isinstance(launched, (int, float)):
                                    launched_ts = int(launched)
                                elif isinstance(launched, str):
                                    # 尝试解析 ISO 格式
                                    dt = datetime.fromisoformat(launched.replace('Z', '+00:00'))
                                    launched_ts = int(dt.timestamp())
                            except:
                                pass

                        # 过滤 3 月以前的
                        if launched_ts and launched_ts < MARCH_1_2025_TS:
                            continue

                        project = {
                            'id': c.get('id') or c.get('campaign_id'),
                            'name': title,
                            'slug': c.get('slug', ''),
                            'creator': c.get('account', {}).get('name') if isinstance(c.get('account'), dict) else c.get('owner_name', ''),
                            'pledged': pledged,
                            'goal': goal,
                            'backers_count': backers,
                            'state': 'successful' if c.get('percent_funded', 0) >= 100 else 'live',
                            'category': c.get('category_name') or c.get('category', ''),
                            'sub_category': '',
                            'url': c.get('clickthrough_url') or c.get('web_url') or f"https://www.indiegogo.com/projects/{c.get('slug', '')}",
                            'photo': c.get('image_url') or c.get('hero_image_url', ''),
                            'location': c.get('region') or c.get('location', ''),
                            'launched_at': launched_ts,
                            'deadline': None,
                            'currency': c.get('currency_code', 'USD'),
                            'pledge_percent': c.get('percent_funded', 0),
                            'platform': 'Indiegogo',
                        }
                        projects.append(project)
                    if projects:
                        return projects
            except Exception as e:
                continue

    # 方法2: 从 HTML 卡片中解析 (fallback)
    if not projects:
        card_pattern = r'<div[^>]*class="[^"]*campaign-card[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>'
        # Indiegogo 的卡片结构更复杂，使用更通用的模式
        card_pattern = r'"campaignId":\s*"([^"]+)".*?"title":\s*"([^"]+)".*?"funds_raised_amount":\s*([\d.]+)'
        matches = re.findall(card_pattern, html_content, re.DOTALL)
        for m in matches:
            try:
                campaign_id, title, pledged = m
                projects.append({
                    'id': campaign_id,
                    'name': html.unescape(title),
                    'pledged': float(pledged),
                    'platform': 'Indiegogo',
                })
            except:
                continue

    return projects


def deduplicate(projects):
    """按项目 ID 去重"""
    seen = set()
    unique = []
    for p in projects:
        pid = p.get('id') or p.get('name')
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)
    return unique


def save_to_json(projects, filename=None):
    """保存到 JSON 文件"""
    if not filename:
        filename = os.path.join(OUTPUT_DIR, f"indiegogo_projects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(projects, f, indent=2, ensure_ascii=False)

    print(f"已保存 {len(projects)} 个项目到: {filename}")
    return filename


def main():
    """主函数"""
    # 尝试几个分类页面
    urls = [
        "https://www.indiegogo.com/explore/technology?project_type=campaign&project_timing=all&sort=trending",
        "https://www.indiegogo.com/explore/home?project_type=campaign&project_timing=all&sort=trending",
        "https://www.indiegogo.com/explore/all?project_type=campaign&project_timing=finished&sort=trending",
    ]

    all_projects = []

    for url in urls:
        print(f"\n🚀 正在抓取: {url}")
        html_file = fetch_page(url, wait_time=15000)

        if not html_file or not os.path.exists(html_file):
            print(f"❌ 抓取失败")
            continue

        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        projects = parse_projects(html_content)
        print(f"✅ 解析到 {len(projects)} 个项目")
        all_projects.extend(projects)

    # 去重
    all_projects = deduplicate(all_projects)

    if not all_projects:
        print("\n❌ 未抓取到任何项目，尝试从 HTML 结构分析...")
        # 保存一份 HTML 用于调试
        return None

    # 按金额排序
    all_projects.sort(key=lambda x: x.get('pledged', 0), reverse=True)

    print(f"\n{'='*60}")
    print(f"共 {len(all_projects)} 个 Indiegogo 项目")
    print(f"{'='*60}\n")

    for i, p in enumerate(all_projects[:15], 1):
        print(f"{i}. {p['name']}")
        print(f"   金额: ${p['pledged']:,.0f} | {p['backers_count']} backers | 类别: {p.get('category', 'N/A')}")
        print(f"   链接: {p.get('url', 'N/A')}")
        print()

    json_file = save_to_json(all_projects)
    return json_file


if __name__ == "__main__":
    main()
