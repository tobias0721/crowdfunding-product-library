#!/usr/bin/env node
/**
 * Indiegogo 项目抓取器 (Playwright Stealth)
 */

const { chromium } = require('playwright');
const fs = require('fs');

const url = process.argv[2] || 'https://www.indiegogo.com/explore/technology?project_type=campaign&project_timing=all&sort=trending';
const waitTime = parseInt(process.env.WAIT_TIME || '8000');
const outputPath = process.env.OUTPUT_JSON || './indiegogo_data.json';

const defaultUA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36';

function parseNumber(text) {
    if (!text) return 0;
    text = text.replace(/,/g, '');
    if (text.endsWith('K') || text.endsWith('k')) return parseFloat(text) * 1000;
    if (text.endsWith('M') || text.endsWith('m')) return parseFloat(text) * 1000000;
    if (text.endsWith('B') || text.endsWith('b')) return parseFloat(text) * 1000000000;
    return parseFloat(text) || 0;
}

async function scrapePage(browser, url) {
    const context = await browser.newContext({
        userAgent: defaultUA,
        locale: 'en-US',
        viewport: { width: 1280, height: 800 },
        extraHTTPHeaders: { 'Accept-Language': 'en-US,en;q=0.9' },
    });

    await context.addInitScript(() => {
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        window.chrome = { runtime: {} };
    });

    const page = await context.newPage();

    try {
        const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
        console.log(`📡 HTTP ${response.status()}`);
    } catch (e) {
        console.error(`❌ 导航失败: ${e.message}`);
    }

    await page.waitForTimeout(waitTime);

    const cloudflare = await page.evaluate(() =>
        document.body.innerText.includes('Just a moment') ||
        document.querySelector('iframe[src*="challenges.cloudflare.com"]') !== null
    );
    if (cloudflare) {
        console.log('🛡️ Cloudflare detected, waiting...');
        await page.waitForTimeout(15000);
    }

    // 滚动
    for (let i = 0; i < 6; i++) {
        await page.evaluate(() => window.scrollBy(0, 1800));
        await page.waitForTimeout(2500);
    }

    // 提取
    const projects = await page.evaluate(() => {
        const results = [];
        const seen = new Set();

        const links = document.querySelectorAll('a[href*="/projects/"]');
        const containers = new Set();

        links.forEach(l => {
            let el = l.parentElement;
            for (let i = 0; i < 6 && el; i++) {
                const txt = el.textContent || '';
                if (el.querySelector('img') && (txt.includes('$') || txt.includes('HK$') || txt.includes('£') || txt.includes('€'))) {
                    containers.add(el);
                    break;
                }
                el = el.parentElement;
            }
        });

        containers.forEach(card => {
            try {
                const linkEl = card.querySelector('a[href*="/projects/"]');
                if (!linkEl) return;
                const href = linkEl.href;
                const slugMatch = href.match(/\/projects\/([^/?]+)/);
                const slug = slugMatch ? slugMatch[1] : '';
                if (!slug || seen.has(slug)) return;

                const text = card.innerText || '';
                // 过滤非项目卡片
                if (!text.includes('goal') && !text.includes('funded') && !text.includes('days left') && !text.includes('CROWDFUNDING') && !text.includes('InDemand')) {
                    return;
                }

                seen.add(slug);

                const titleEl = card.querySelector('h3, h4');
                const title = titleEl ? titleEl.innerText.trim() : linkEl.innerText.trim();
                const img = card.querySelector('img');
                const photo = img ? img.src : '';

                // 金额
                let fundsText = '';
                const fundsMatch = text.match(/[\$£€¥HK$]+\s?([\d,.]+[KMB]?)/);
                if (fundsMatch) fundsText = fundsMatch[1];

                // backers
                let backersText = '';
                const backersMatch = text.match(/(\d+[\d,.]*[KMB]?)\s*(backer|supporter|funder)/i);
                if (backersMatch) backersText = backersMatch[1];

                // percent
                let percent = 0;
                const pm = text.match(/(\d+)%\s*funded/i);
                if (pm) percent = parseInt(pm[1]);

                // creator
                let creator = '';
                const cm = text.match(/by\s+(.+?)(?:\n|$)/);
                if (cm) creator = cm[1].trim();

                results.push({
                    id: slug,
                    name: title,
                    slug: slug,
                    url: href,
                    photo: photo,
                    creator: creator,
                    pledged_text: fundsText,
                    backers_text: backersText,
                    pledge_percent: percent,
                    raw_text: text.substring(0, 250),
                });
            } catch (e) {}
        });

        return results;
    });

    await context.close();
    return projects;
}

(async () => {
    console.log('🕷️ 启动 Indiegogo Stealth 抓取器...');
    const startTime = Date.now();

    const browser = await chromium.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled'],
    });

    const urls = [
        'https://www.indiegogo.com/explore/technology?project_type=campaign&project_timing=all&sort=trending',
        'https://www.indiegogo.com/explore/home?project_type=campaign&project_timing=all&sort=trending',
        'https://www.indiegogo.com/explore/design?project_type=campaign&project_timing=all&sort=trending',
        'https://www.indiegogo.com/explore/outdoor?project_type=campaign&project_timing=all&sort=trending',
    ];

    const allProjects = [];
    const seenSlugs = new Set();

    for (const u of urls) {
        console.log(`\n📱 抓取: ${u}`);
        try {
            const projects = await scrapePage(browser, u);
            console.log(`✅ 提取到 ${projects.length} 个项目`);
            for (const p of projects) {
                if (!seenSlugs.has(p.slug)) {
                    seenSlugs.add(p.slug);
                    allProjects.push(p);
                }
            }
        } catch (e) {
            console.error(`❌ 失败: ${e.message}`);
        }
    }

    await browser.close();

    console.log(`\n📊 去重后共 ${allProjects.length} 个项目`);

    for (const p of allProjects) {
        p.pledged = parseNumber(p.pledged_text);
        p.backers_count = parseNumber(p.backers_text);
        p.platform = 'Indiegogo';
    }

    allProjects.sort((a, b) => (b.pledged || 0) - (a.pledged || 0));

    fs.writeFileSync(outputPath, JSON.stringify(allProjects, null, 2));
    console.log(`💾 已保存: ${outputPath}`);

    console.log(`⏱️ 耗时: ${((Date.now() - startTime)/1000).toFixed(2)}s`);
})();
