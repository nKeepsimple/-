import requests
import time
from bs4 import BeautifulSoup
import pandas as pd
import os
import re
from datetime import datetime

# ---------- 配置 ----------
REQUEST_TIMEOUT = 30  # 秒
MAX_SEARCH_PAGES = 100  # 最多搜索100页
BASE_URL = "https://www.diis.dk"  # DIIS 网站基础URL

# 浏览器请求头
HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "priority": "u=0, i",
    "sec-ch-ua": "\"Microsoft Edge\";v=\"147\", \"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"147\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0"
}

SEARCH_QUERY = ""  # 全局搜索关键词

# 丹麦语月份映射
DANISH_MONTHS = {
    'januar': '01',
    'februar': '02',
    'marts': '03',
    'april': '04',
    'maj': '05',
    'juni': '06',
    'juli': '07',
    'august': '08',
    'september': '09',
    'oktober': '10',
    'november': '11',
    'december': '12'
}


def convert_date_format(date_str):
    """将丹麦语日期格式转换为 YYYY-MM-DD"""
    if not date_str:
        return ""

    date_str = date_str.strip()

    # 处理丹麦语格式: "13. september 2021"
    danish_pattern = r'(\d{1,2})\.\s*([a-zA-Z]+)\s+(\d{4})'
    match = re.search(danish_pattern, date_str, re.IGNORECASE)
    if match:
        day = match.group(1).zfill(2)
        month_name = match.group(2).lower()
        year = match.group(3)
        if month_name in DANISH_MONTHS:
            month = DANISH_MONTHS[month_name]
            return f"{year}-{month}-{day}"

    # 处理格式: "2021-09-13"
    iso_pattern = r'(\d{4})-(\d{2})-(\d{2})'
    match = re.search(iso_pattern, date_str)
    if match:
        return date_str

    return date_str


def fetch_page_with_requests(url):
    """使用 requests 获取页面 HTML"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        response.encoding = 'utf-8'
        return response.text
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None


def parse_diis_html(html, url):
    """解析 DIIS 文章页面的 HTML"""
    soup = BeautifulSoup(html, 'html.parser')

    # 1. 标题 - 查找 h1 标签
    title_tag = soup.find('h1')
    title = title_tag.get_text(strip=True) if title_tag else ""

    # 2. 发布日期 - 查找并转换格式
    pub_date_raw = ""

    # 方法1: 查找 .field-date time 标签
    date_tag = soup.select_one('.field-date time')
    if date_tag:
        pub_date_raw = date_tag.get_text(strip=True)
        if not pub_date_raw and date_tag.has_attr('datetime'):
            pub_date_raw = date_tag['datetime']

    # 方法2: 如果没找到，查找其他常见的日期选择器
    if not pub_date_raw:
        date_selectors = [
            '.date',
            '.published',
            '.post-date',
            'time',
            '.meta-date',
            '.article-date'
        ]
        for selector in date_selectors:
            date_tag = soup.select_one(selector)
            if date_tag:
                pub_date_raw = date_tag.get_text(strip=True)
                break

    # 方法3: 如果还没找到，尝试查找丹麦语日期格式的文本
    if not pub_date_raw:
        text = soup.get_text()
        date_patterns = [
            r'\d{1,2}\.\s+(januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)\s+\d{4}',
            r'\d{1,2}\.\d{1,2}\.\d{4}',
            r'\d{4}-\d{2}-\d{2}'
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                pub_date_raw = match.group(0)
                break

    # 转换日期格式为 YYYY-MM-DD
    pub_date = convert_date_format(pub_date_raw)

    # 3. 作者 - 根据你提供的 HTML 结构
    authors = []

    # 方法1: 查找 .node-title.view-mode-contact 中的 a 标签
    author_links = soup.select('.node-title.view-mode-contact a')
    for a in author_links:
        name = a.get_text(strip=True)
        if name and name not in authors:
            authors.append(name)

    # 方法2: 如果没找到，查找作者相关的选择器
    if not authors:
        author_selectors = [
            '.author',
            '.byline',
            '.writer',
            '[rel="author"]',
            '.meta-author',
            '.field-name-author',
            '.node-title a'
        ]
        for selector in author_selectors:
            for elem in soup.select(selector):
                name = elem.get_text(strip=True)
                if name and name not in authors:
                    name = re.sub(r'^(By|Af)\s+', '', name, flags=re.IGNORECASE)
                    authors.append(name)

    # 方法3: 检查是否有 "Forfatter:" 或 "Author:" 标签
    if not authors:
        for label in soup.find_all(['strong', 'span', 'div'],
                                   string=re.compile(r'(Forfatter|Author|Af)', re.IGNORECASE)):
            parent = label.find_parent()
            if parent:
                name = parent.get_text(strip=True)
                name = re.sub(r'^(Forfatter|Author|Af):\s*', '', name, flags=re.IGNORECASE)
                if name and name not in authors:
                    authors.append(name)

    authors_str = ", ".join(authors) if authors else "Unknown"

    # 4. 文章类型判断
    article_type = "Article"
    if '/publikationer/' in url or '/publication/' in url:
        article_type = "Publication"
    elif '/event/' in url:
        article_type = "Event"
    elif '/projekt/' in url:
        article_type = "Project"
    elif '/person/' in url or '/eksperter/' in url:
        article_type = "Person / Expert"

    # 5. 正文 - 查找 .field-content 或文章主体
    body_text = ""
    content_selectors = [
        '.field-content',
        '.field-name-body',
        '.article-content',
        '.content',
        'article',
        '.main-content'
    ]

    for selector in content_selectors:
        body_div = soup.select_one(selector)
        if body_div:
            paragraphs = body_div.find_all('p')
            body_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs)
            if body_text:
                break

    # 如果还没找到，获取所有段落
    if not body_text:
        paragraphs = soup.find_all('p')
        body_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs)

    # 清理正文
    if body_text:
        body_text = re.sub(r'\[\d+\]', '', body_text)  # 去除引用标记
        body_text = re.sub(r'\n{3,}', '\n\n', body_text)  # 去除多余换行

    # 如果正文太长，截取前 50000 字符
    if len(body_text) > 50000:
        body_text = body_text[:50000] + "...(内容过长，已截断)"

    # 按指定顺序返回字段
    return {
        "类型": article_type,
        "发布日期": pub_date,
        "作者": authors_str,
        "链接": url,
        "正文内容": body_text,
        "搜索关键词": SEARCH_QUERY,
        "来源网站": "diis.dk",
        "标题": title
    }


def search_diis_all_pages(query, max_pages=MAX_SEARCH_PAGES):
    """修正：DIIS 网站分页从 page=0 开始"""
    all_links = []
    current_page = 0

    print(f"开始搜索关键词 '{query}'...")

    while current_page < max_pages:
        search_url = f"{BASE_URL}/search"
        params = {
            "s": query,
            "page": str(current_page)
        }

        print(f"正在获取第 {current_page + 1} 页 (page={current_page}): {search_url}?s={query}&page={current_page}")

        try:
            response = requests.get(search_url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')

            page_links = []
            for title_div in soup.select('.views-field-title'):
                a_tag = title_div.find('a')
                if a_tag and a_tag.get('href'):
                    href = a_tag['href']
                    if href.startswith('/'):
                        href = BASE_URL + href
                    if href not in all_links and 'search' not in href:
                        page_links.append(href)

            if page_links:
                all_links.extend(page_links)
                print(f"第 {current_page + 1} 页找到 {len(page_links)} 个链接")
            else:
                print(f"第 {current_page + 1} 页未找到链接，这可能是最后一页。")
                break

            current_page += 1
            time.sleep(1)

        except Exception as e:
            print(f"获取第 {current_page + 1} 页失败: {e}")
            break

    print(f"\n共获取到 {len(all_links)} 个文章链接")
    return all_links


def process_one_link(link):
    """处理单个链接：获取页面并解析"""
    print(f"开始处理: {link}")
    try:
        html = fetch_page_with_requests(link)
        if not html:
            return None
        detail = parse_diis_html(html, link)
        return detail
    except Exception as e:
        print(f"处理 {link} 时出错: {e}")
        return None
    finally:
        time.sleep(0.5)


def main():
    global SEARCH_QUERY

    # 用户输入关键词
    keyword = input("请输入要搜索的关键词（例如 Risici）：").strip()
    if not keyword:
        print("关键词不能为空，使用默认关键词 'Risici'")
        keyword = "Risici"
    SEARCH_QUERY = keyword

    # 询问页数
    try:
        pages_input = input(f"请输入要爬取的页数（默认 {MAX_SEARCH_PAGES} 页，输入0表示全部）：").strip()
        if pages_input == "0":
            max_pages = 999
        elif pages_input:
            max_pages = int(pages_input)
        else:
            max_pages = MAX_SEARCH_PAGES
    except:
        max_pages = MAX_SEARCH_PAGES

    # 1. 获取所有链接
    print(f"\n正在搜索关键词 '{SEARCH_QUERY}'（最多 {max_pages if max_pages < 999 else '全部'} 页）...")
    all_links = search_diis_all_pages(SEARCH_QUERY, max_pages)
    print(f"共获取到 {len(all_links)} 个文章链接。")

    if not all_links:
        print("没有链接可处理，退出。")
        return

    # 2. 逐个处理文章
    print(f"\n开始逐个抓取文章内容...")
    results = []
    for i, link in enumerate(all_links, 1):
        print(f"\n[{i}/{len(all_links)}] 处理: {link}")
        result = process_one_link(link)
        if result:
            results.append(result)
            print(f"成功: {link[:80]}...")
        else:
            print(f"失败: {link[:80]}...")

    # 3. 保存结果到 Excel（列的顺序已经在返回字典中定义好了）
    if results:
        df = pd.DataFrame(results)

        # 确保列的顺序正确
        column_order = ["类型", "发布日期", "作者", "链接", "正文内容", "搜索关键词", "来源网站", "标题"]
        df = df[column_order]

        safe_keyword = "".join(c for c in SEARCH_QUERY if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not safe_keyword:
            safe_keyword = "result"
        filename = f"diis_results_{safe_keyword}.xlsx"

        counter = 1
        original = filename
        while os.path.exists(filename):
            name, ext = os.path.splitext(original)
            filename = f"{name}_{counter}{ext}"
            counter += 1

        df.to_excel(filename, index=False, engine='openpyxl')
        print(f"\n成功抓取 {len(results)} 条结果，已保存至 {filename}")

        # 打印统计信息
        print("\n统计信息:")
        print(f"  - 总文章数: {len(results)}")
        print(f"  - 有标题: {sum(1 for r in results if r['标题'])}")
        print(f"  - 有日期: {sum(1 for r in results if r['发布日期'])}")
        print(f"  - 有正文: {sum(1 for r in results if len(r['正文内容']) > 100)}")

        # 打印日期格式示例
        if results and results[0]['发布日期']:
            print(f"\n日期格式示例: {results[0]['发布日期']}")
    else:
        print("\n未获取到任何有效结果。")


if __name__ == "__main__":
    main()