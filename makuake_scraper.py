#!/usr/bin/env python3
"""
Makuake 日本众筹项目抓取器
基于 playwright-scraper-skill 的 Stealth 模式
"""

import json
import re
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
    env["SCREENSHOT_PATH"] = os.path.join(OUTPUT_DIR, f"makuake_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    env["USER_AGENT"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"

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
    """从 HTML 中解析 Makuake 项目数据"""
    projects = []

    # 提取所有项目slug
    project_slugs = list(set(re.findall(r'https://www\.makuake\.com/project/([^/"]+)/?', html_content)))

    for slug in project_slugs:
        link_pattern = f'href="https://www\\.makuake\\.com/project/{slug}/"'
        match = re.search(link_pattern, html_content)
        if not match:
            continue

        pos = match.start()
        # 向前查找卡片开始
        start = html_content.rfind('<li', max(0, pos-2000), pos)
        if start == -1:
            start = html_content.rfind('<div', max(0, pos-2000), pos)
        if start == -1:
            start = max(0, pos-1000)

        # 向后查找卡片结束
        end = html_content.find('</li>', pos)
        if end == -1:
            end = html_content.find('</div>', pos)
        if end == -1:
            end = min(len(html_content), pos+1000)
        else:
            end += len('</li>')

        card_html = html_content[start:end]
        text = re.sub(r'<[^>]+>', ' ', card_html)
        text = re.sub(r'\s+', ' ', text).strip()

        # 提取标题（在金额￥之前）
        title_match = re.search(r'([^￥]+)￥', text)
        title = title_match.group(1).strip() if title_match else slug

        # 清理标题中的常见前缀
        title = re.sub(r'^推奨実行者マーク\s*', '', title)
        title = title.strip()

        # 提取金额
        amount_match = re.search(r'￥([\d,]+)', text)
        amount = int(amount_match.group(1).replace(',', '')) if amount_match else 0

        # 提取天数
        days_match = re.search(r'(\d+)\s*日', text)
        days = int(days_match.group(1)) if days_match else 0

        # 提取达成率
        pct_match = re.search(r'(\d+)%', text)
        pct = int(pct_match.group(1)) if pct_match else 0

        # 提取图片
        img_match = re.search(r'src="(https://static\.makuake[^"]+)"', card_html)
        img = img_match.group(1) if img_match else ''

        # 检查是否是NEW项目
        is_new = 'NEW' in text

        # Makuake页面没有 backers 数量，只有达成率和金额
        # 估算 backers（假设平均支持金额约5000日元）
        estimated_backers = max(1, amount // 5000)

        project = {
            'id': slug,
            'name': title,
            'slug': slug,
            'creator': '',  # Makuake列表页不显示创建者
            'pledged': amount,
            'goal': int(amount / (pct / 100)) if pct > 0 else 0,
            'backers_count': estimated_backers,
            'state': 'successful' if pct >= 100 else 'live',
            'category': '',  # 需要从详情页获取
            'sub_category': '',
            'url': f"https://www.makuake.com/project/{slug}/",
            'photo': img,
            'location': 'Japan',
            'launched_at': None,  # Makuake列表页没有创建时间
            'deadline': None,
            'currency': 'JPY',
            'pledge_percent': pct,
            'platform': 'Makuake',
            'days_left': days,
            'is_new': is_new,
        }
        projects.append(project)

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
        filename = os.path.join(OUTPUT_DIR, f"makuake_projects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(projects, f, indent=2, ensure_ascii=False)

    print(f"已保存 {len(projects)} 个项目到: {filename}")
    return filename


def print_summary(projects):
    """打印项目摘要"""
    print(f"\n{'='*60}")
    print(f"共 {len(projects)} 个 Makuake 项目")
    print(f"{'='*60}\n")

    for i, p in enumerate(projects[:15], 1):
        print(f"{i}. {p['name']}")
        print(f"   ￥{p['pledged']:,.0f} | {p['pledge_percent']}% | {p['days_left']}日")
        print(f"   链接: {p['url']}")
        print()

    if len(projects) > 15:
        print(f"... 还有 {len(projects) - 15} 个项目")


def main():
    """主函数"""
    # Makuake 的发现页面
    urls = [
        "https://www.makuake.com/discover/all",
        "https://www.makuake.com/discover/technology",
        "https://www.makuake.com/discover/home",
        "https://www.makuake.com/discover/fashion",
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
        print("\n❌ 未抓取到任何项目")
        return None

    # 按众筹金额排序
    all_projects.sort(key=lambda x: x.get('pledged', 0), reverse=True)

    print_summary(all_projects)

    json_file = save_to_json(all_projects)
    print(f"\n✅ 完成！数据已保存到: {json_file}")
    return json_file


if __name__ == "__main__":
    main()
