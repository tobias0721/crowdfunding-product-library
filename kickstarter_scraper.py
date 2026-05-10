#!/usr/bin/env python3
"""
Kickstarter 众筹项目抓取器（支持多页 + 时间过滤）
基于 playwright-scraper-skill 的 Stealth 模式
"""

import json
import re
import html
import subprocess
import os
import sys
from datetime import datetime

# 配置
STEALTH_SCRIPT = os.path.expanduser("~/.workbuddy/skills/playwright-scraper-skill/scripts/playwright-stealth.js")
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2025-03-01 00:00:00 UTC 时间戳
MARCH_1_2025_TS = 1740787200


def fetch_page(url, wait_time=10000):
    """使用 Playwright Stealth 抓取页面"""
    env = os.environ.copy()
    env["SAVE_HTML"] = "true"
    env["WAIT_TIME"] = str(wait_time)
    env["SCREENSHOT_PATH"] = os.path.join(OUTPUT_DIR, f"kickstarter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

    result = subprocess.run(
        ["node", STEALTH_SCRIPT, url],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(STEALTH_SCRIPT),
        env=env
    )

    # 从输出中提取 HTML 文件路径
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
    """从 HTML 中解析 Kickstarter 项目数据"""
    pattern = r'data-project="([^"]*)"'
    matches = re.findall(pattern, html_content)

    projects = []
    for match in matches:
        try:
            decoded = html.unescape(match)
            data = json.loads(decoded)

            launched_at = data.get('launched_at')
            # 过滤：只保留 2025-03-01 之后的项目
            if launched_at and launched_at < MARCH_1_2025_TS:
                continue

            project = {
                'id': data.get('id'),
                'name': data.get('name'),
                'slug': data.get('slug'),
                'creator': data.get('creator', {}).get('name'),
                'pledged': data.get('pledged'),
                'goal': data.get('goal'),
                'backers_count': data.get('backers_count'),
                'state': data.get('state'),
                'category': data.get('category', {}).get('name'),
                'sub_category': data.get('category', {}).get('parent_name'),
                'url': data.get('urls', {}).get('web', {}).get('project'),
                'photo': data.get('photo', {}).get('full'),
                'location': data.get('location', {}).get('displayable_name'),
                'launched_at': launched_at,
                'deadline': data.get('deadline'),
                'currency': data.get('currency'),
                'pledge_percent': round((data.get('pledged', 0) / data.get('goal', 1)) * 100, 1) if data.get('goal') else 0,
                'platform': 'Kickstarter',
            }
            projects.append(project)
        except Exception as e:
            print(f"解析项目时出错: {e}")
            continue

    return projects


def save_to_json(projects, filename=None):
    """保存到 JSON 文件"""
    if not filename:
        filename = os.path.join(OUTPUT_DIR, f"kickstarter_projects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(projects, f, indent=2, ensure_ascii=False)

    print(f"已保存 {len(projects)} 个项目到: {filename}")
    return filename


def deduplicate(projects):
    """按项目 ID 去重"""
    seen = set()
    unique = []
    for p in projects:
        pid = p.get('id')
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)
    return unique


def print_summary(projects):
    """打印项目摘要"""
    print(f"\n{'='*60}")
    print(f"共 {len(projects)} 个项目")
    print(f"{'='*60}\n")

    for i, p in enumerate(projects[:15], 1):
        launched = datetime.fromtimestamp(p['launched_at']).strftime('%Y-%m-%d') if p.get('launched_at') else 'N/A'
        print(f"{i}. {p['name']}")
        print(f"   创建者: {p['creator']} | 上线: {launched}")
        print(f"   类别: {p['category']} | ${p['pledged']:,.0f} / {p['backers_count']} backers")
        print(f"   链接: {p['url']}")
        print()

    if len(projects) > 15:
        print(f"... 还有 {len(projects) - 15} 个项目")


def main():
    """主函数：翻页抓取 3 月以来的成功项目"""
    all_projects = []

    # 翻页抓取，最多 10 页
    for page in range(1, 11):
        url = f"https://www.kickstarter.com/discover/advanced?launched_after={MARCH_1_2025_TS}&state=successful&sort=end_date&seed=1&page={page}"

        print(f"\n🚀 正在抓取第 {page} 页...")
        print(f"URL: {url}")

        html_file = fetch_page(url, wait_time=12000)

        if not html_file or not os.path.exists(html_file):
            print(f"❌ 第 {page} 页抓取失败")
            break

        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        projects = parse_projects(html_content)

        if not projects:
            print(f"⚠️ 第 {page} 页无项目，可能已到末尾")
            break

        print(f"✅ 第 {page} 页解析到 {len(projects)} 个项目")
        all_projects.extend(projects)

    # 去重
    all_projects = deduplicate(all_projects)

    if not all_projects:
        print("❌ 未抓取到任何项目")
        sys.exit(1)

    # 按众筹金额排序
    all_projects.sort(key=lambda x: x.get('pledged', 0), reverse=True)

    print_summary(all_projects)

    # 保存
    json_file = save_to_json(all_projects)
    print(f"\n✅ 完成！数据已保存到: {json_file}")

    return json_file


if __name__ == "__main__":
    main()
