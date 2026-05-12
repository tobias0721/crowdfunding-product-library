#!/usr/bin/env python3
"""
Wadiz 韩国众筹项目抓取器
基于 playwright-scraper-skill 的 Stealth 模式
Wadiz是重度SPA，项目数据通过data-ec属性嵌入HTML
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
    env["SCREENSHOT_PATH"] = os.path.join(OUTPUT_DIR, f"wadiz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
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
    """从 HTML 中解析 Wadiz 项目数据
    Wadiz使用data-ec-id和data-ec-name属性存储项目信息
    """
    projects = []

    # 提取data-ec-id和data-ec-name
    project_data = re.findall(r'data-ec-id="(\d+)"[^>]*data-ec-name="([^"]+)"', html_content)

    for pid, name in project_data:
        pos = html_content.find(f'data-ec-id="{pid}"')
        if pos == -1:
            continue

        # 提取周围上下文
        context = html_content[max(0, pos-1500):min(len(html_content), pos+1500)]

        # 查找百分比（达成率）
        pct_matches = re.findall(r'(\d+)%', context)
        pct = int(pct_matches[0]) if pct_matches else 0

        # 查找图片
        img_match = re.search(r'src="(https://funding-cdn\.wadiz\.kr/[^"]+)"', context)
        img = img_match.group(1) if img_match else ''

        # Wadiz列表页没有显示金额和支持者数
        # 这些信息需要通过详情页API获取
        # 这里使用占位值

        project = {
            'id': pid,
            'name': name,
            'slug': pid,
            'creator': '',  # 需要从详情页获取
            'pledged': 0,  # 需要从详情页获取
            'goal': 0,  # 需要从详情页获取
            'backers_count': 0,  # 需要从详情页获取
            'state': 'successful' if pct >= 100 else 'live',
            'category': '',  # 需要从详情页获取
            'sub_category': '',
            'url': f"https://www.wadiz.kr/web/campaign/detail/{pid}",
            'photo': img,
            'location': 'Korea',
            'launched_at': None,  # 需要从详情页获取
            'deadline': None,
            'currency': 'KRW',
            'pledge_percent': pct,
            'platform': 'Wadiz',
        }
        projects.append(project)

    return projects


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


def save_to_json(projects, filename=None):
    """保存到 JSON 文件"""
    if not filename:
        filename = os.path.join(OUTPUT_DIR, f"wadiz_projects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(projects, f, indent=2, ensure_ascii=False)

    print(f"已保存 {len(projects)} 个项目到: {filename}")
    return filename


def print_summary(projects):
    """打印项目摘要"""
    print(f"\n{'='*60}")
    print(f"共 {len(projects)} 个 Wadiz 项目")
    print(f"{'='*60}\n")

    for i, p in enumerate(projects[:15], 1):
        print(f"{i}. {p['name']}")
        print(f"   达成率: {p['pledge_percent']}%")
        print(f"   链接: {p['url']}")
        print()

    if len(projects) > 15:
        print(f"... 还有 {len(projects) - 15} 个项目")


def main():
    """主函数
    Wadiz有反爬机制，多次快速请求会返回空页面
    只抓取一次首页，提取所有项目数据
    """
    url = "https://www.wadiz.kr/web/wreward/main?order=recent"

    print(f"\n🚀 正在抓取: {url}")
    print("⏳ Wadiz需要较长时间加载，请等待...")
    html_file = fetch_page(url, wait_time=20000)

    if not html_file or not os.path.exists(html_file):
        print(f"❌ 抓取失败")
        return None

    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 检查是否成功加载
    if len(html_content) < 500000:
        print(f"⚠️ 页面内容较少({len(html_content)}字节)，可能未完全加载")
        print("   尝试使用已缓存的HTML文件...")
        # 尝试使用之前成功抓取的HTML（按文件大小排序，找最大的）
        cached_files = [(f, os.path.getsize(os.path.join(OUTPUT_DIR, f))) 
                       for f in os.listdir(OUTPUT_DIR) 
                       if f.startswith('wadiz_') and f.endswith('.html')]
        cached_files.sort(key=lambda x: x[1], reverse=True)
        if cached_files:
            cached_file = os.path.join(OUTPUT_DIR, cached_files[0][0])
            with open(cached_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            print(f"   使用缓存文件: {cached_file} ({len(html_content)}字节)")

    projects = parse_projects(html_content)
    print(f"✅ 解析到 {len(projects)} 个项目")

    # 去重
    projects = deduplicate(projects)

    if not projects:
        print("\n❌ 未抓取到任何项目")
        return None

    # 按达成率排序
    projects.sort(key=lambda x: x.get('pledge_percent', 0), reverse=True)

    print_summary(projects)

    json_file = save_to_json(projects)
    print(f"\n✅ 完成！数据已保存到: {json_file}")
    return json_file


if __name__ == "__main__":
    main()
