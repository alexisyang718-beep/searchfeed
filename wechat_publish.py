#!/usr/bin/env python3
"""
微信公众号日报推送模板脚本
用法: python3 wechat_publish.py [YYYY-MM-DD]
不传日期参数则使用今天的日期
"""

import sys
import os
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# ============ 配置 ============
APPID = "wxc0acff84c3ba27b0"
APPSECRET = "7af6a2678e804ecbe3425f0889c1d28d"
THUMB_MEDIA_ID = "mP2QZYM3NVFzRFt1maN2wiJ9OFpFwmlVzVSLivsm_VG_TvWs6QKP6sgGPqS9X8hJ"
GITHUB_PAGES_BASE = "https://alexisyang718-beep.github.io/ai-daily-brief/brief"
BRIEF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brief")

# ============ 样式常量（赤陶色主题，纯内联样式，微信兼容） ============
STYLES = {
    # 颜色
    "accent": "#C96442",
    "accent_soft_bg": "rgba(201,100,66,0.06)",
    "text": "#1A1A1A",
    "text_secondary": "#6B6560",
    "text_tertiary": "#9B9590",
    "bg_warm": "#F5F0E8",
    "border": "#E8E2D9",
    "border_light": "#F0EBE3",
    "card_bg": "#FFFFFF",
    # tag 颜色
    "tag_red": "#C96442",
    "tag_red_bg": "rgba(201,100,66,0.08)",
    "tag_green": "#5A8F6B",
    "tag_green_bg": "rgba(90,143,107,0.08)",
    "tag_blue": "#4A7B9D",
    "tag_blue_bg": "rgba(74,123,157,0.08)",
    "tag_purple": "#7B6B9D",
    "tag_purple_bg": "rgba(123,107,157,0.08)",
    "tag_orange": "#B8863B",
    "tag_orange_bg": "rgba(184,134,59,0.08)",
    "tag_teal": "#4A8F8F",
    "tag_teal_bg": "rgba(74,143,143,0.08)",
}

TAG_STYLE_MAP = {
    "tag-hot": f"background:{STYLES['tag_red_bg']};color:{STYLES['tag_red']}",
    "tag-new": f"background:{STYLES['tag_green_bg']};color:{STYLES['tag_green']}",
    "tag-money": f"background:{STYLES['tag_orange_bg']};color:{STYLES['tag_orange']}",
    "tag-chip": f"background:{STYLES['tag_purple_bg']};color:{STYLES['tag_purple']}",
    "tag-agent": f"background:{STYLES['tag_blue_bg']};color:{STYLES['tag_blue']}",
    "tag-phone": f"background:{STYLES['tag_teal_bg']};color:{STYLES['tag_teal']}",
    "tag-policy": f"background:{STYLES['tag_green_bg']};color:{STYLES['tag_green']}",
}


def get_access_token():
    """获取微信 access_token"""
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={APPID}&secret={APPSECRET}"
    r = requests.get(url)
    data = r.json()
    if "access_token" not in data:
        raise Exception(f"获取 access_token 失败: {data}")
    return data["access_token"]


def parse_brief_html(filepath):
    """解析 brief HTML 文件，提取结构化内容"""
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    return soup


def convert_tag(tag_el):
    """将 tag 元素转为微信内联样式"""
    classes = tag_el.get("class", [])
    tag_style = ""
    for cls in classes:
        if cls in TAG_STYLE_MAP:
            tag_style = TAG_STYLE_MAP[cls]
            break
    text = tag_el.get_text(strip=True)
    return (
        f'<span style="display:inline-block;font-size:11px;padding:2px 8px;'
        f'border-radius:20px;font-weight:500;white-space:nowrap;letter-spacing:0.3px;{tag_style}">'
        f'{text}</span>'
    )


def convert_stat_row(stat_row_el):
    """将 stat-row 转为微信内联样式"""
    stats = stat_row_el.find_all(class_="stat")
    parts = []
    for stat in stats:
        em = stat.find("em")
        if em:
            em_text = em.get_text(strip=True)
            # 获取 em 之前的文本
            label = stat.get_text(strip=True).replace(em_text, "").strip()
            parts.append(
                f'<span style="display:inline-block;background:{STYLES["bg_warm"]};'
                f'padding:4px 10px;border-radius:20px;font-size:12px;color:{STYLES["text_secondary"]};'
                f'border:1px solid {STYLES["border_light"]};margin:3px 4px 3px 0;">'
                f'{label} <strong style="color:{STYLES["accent"]};font-weight:600;">{em_text}</strong></span>'
            )
        else:
            parts.append(
                f'<span style="display:inline-block;background:{STYLES["bg_warm"]};'
                f'padding:4px 10px;border-radius:20px;font-size:12px;color:{STYLES["text_secondary"]};'
                f'border:1px solid {STYLES["border_light"]};margin:3px 4px 3px 0;">'
                f'{stat.get_text(strip=True)}</span>'
            )
    return f'<p style="margin:8px 0;">{"".join(parts)}</p>'


def convert_item_source(source_el):
    """将 item-source 转为微信内联样式（微信不支持外链，用纯文本+强调色）"""
    # 将 <a> 标签替换为纯文本（微信会过滤外链）
    for a in source_el.find_all("a"):
        text = a.get_text(strip=True)
        a.replace_with(BeautifulSoup(
            f'<span style="color:{STYLES["accent"]};font-weight:500;">{text}</span>',
            "html.parser"
        ))
    inner = source_el.decode_contents()
    return (
        f'<p style="font-size:12px;color:{STYLES["text_tertiary"]};padding-top:8px;'
        f'border-top:1px solid {STYLES["border_light"]};margin-top:8px;">{inner}</p>'
    )


def convert_item_body(body_el):
    """将 item-body 转为微信内联样式，保留 strong 和 br"""
    for strong in body_el.find_all("strong"):
        text = strong.get_text(strip=True)
        strong.replace_with(BeautifulSoup(
            f'<strong style="color:{STYLES["text"]};font-weight:600;">{text}</strong>',
            "html.parser"
        ))
    inner = body_el.decode_contents()
    return (
        f'<p style="font-size:14px;color:{STYLES["text_secondary"]};line-height:1.85;margin-bottom:8px;">'
        f'{inner}</p>'
    )


def convert_section(section_el):
    """将一个 section 转为微信内联样式 HTML"""
    parts = []

    # Section header
    header = section_el.find(class_="section-header")
    if header:
        icon = header.find(class_="icon")
        h2 = header.find("h2")
        icon_text = icon.get_text(strip=True) if icon else ""
        h2_text = h2.get_text(strip=True) if h2 else ""
        parts.append(
            f'<section style="margin-bottom:28px;">'
            f'<p style="font-size:18px;font-weight:700;color:{STYLES["text"]};'
            f'padding-bottom:10px;border-bottom:1px solid {STYLES["border"]};margin-bottom:16px;">'
            f'{icon_text} {h2_text}</p>'
        )

    # Items
    for item in section_el.find_all(class_="item"):
        parts.append(
            f'<section style="background:{STYLES["card_bg"]};border:1px solid {STYLES["border_light"]};'
            f'border-radius:12px;padding:16px 18px;margin-bottom:12px;">'
        )

        # Title with tag
        title_el = item.find(class_="item-title")
        if title_el:
            tag = title_el.find(class_="tag")
            tag_html = convert_tag(tag) + " " if tag else ""
            # 获取标题文本（去掉 tag 的文本）
            title_text = title_el.get_text(strip=True)
            if tag:
                tag_text = tag.get_text(strip=True)
                title_text = title_text.replace(tag_text, "", 1).strip()
            parts.append(
                f'<p style="font-size:15px;font-weight:600;color:{STYLES["text"]};'
                f'line-height:1.5;margin-bottom:6px;">{tag_html}{title_text}</p>'
            )

        # Body
        body_el = item.find(class_="item-body")
        if body_el:
            parts.append(convert_item_body(body_el))

        # Stat row
        stat_row = item.find(class_="stat-row")
        if stat_row:
            parts.append(convert_stat_row(stat_row))

        # Source
        source_el = item.find(class_="item-source")
        if source_el:
            parts.append(convert_item_source(source_el))

        parts.append("</section>")

    # GitHub grid（微信不支持外链，项目名用纯文本加粗+赤陶色）
    gh_grid = section_el.find(class_="github-grid")
    if gh_grid:
        for gh_item in gh_grid.find_all(class_="gh-item"):
            parts.append(
                f'<section style="background:{STYLES["card_bg"]};border:1px solid {STYLES["border_light"]};'
                f'border-radius:10px;padding:14px 16px;margin-bottom:10px;">'
            )
            name_el = gh_item.find(class_="gh-name")
            if name_el:
                a = name_el.find("a")
                if a:
                    text = a.get_text(strip=True)
                    parts.append(
                        f'<p style="font-weight:600;font-size:13px;margin-bottom:4px;'
                        f'color:{STYLES["accent"]};">{text}</p>'
                    )
            desc_el = gh_item.find(class_="gh-desc")
            if desc_el:
                parts.append(
                    f'<p style="font-size:12px;color:{STYLES["text_secondary"]};line-height:1.6;margin-bottom:6px;">'
                    f'{desc_el.get_text(strip=True)}</p>'
                )
            star_el = gh_item.find(class_="gh-star")
            if star_el:
                parts.append(
                    f'<p style="font-size:12px;color:{STYLES["tag_orange"]};font-weight:500;">'
                    f'{star_el.get_text(strip=True)}</p>'
                )
            parts.append("</section>")

    parts.append("</section>")
    return "\n".join(parts)


def build_wechat_html(soup, date_str):
    """从解析后的 soup 构建完整的微信公众号 HTML"""
    parts = []

    # 外层容器
    parts.append(
        f'<section style="max-width:600px;margin:0 auto;padding:0 8px;'
        f'font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Noto Sans SC\',sans-serif;'
        f'color:{STYLES["text"]};line-height:1.8;font-size:14px;">'
    )

    # Header
    parts.append(
        f'<section style="text-align:center;padding:24px 0 16px;">'
        f'<p style="font-size:24px;font-weight:700;color:{STYLES["text"]};letter-spacing:-0.5px;margin-bottom:4px;">'
        f'AI Daily Brief</p>'
        f'<p style="color:{STYLES["text_tertiary"]};font-size:13px;letter-spacing:0.3px;">'
    )

    # 提取日期
    date_el = soup.find(class_="date")
    if date_el:
        parts.append(date_el.get_text(strip=True))
    else:
        parts.append(date_str)
    parts.append("</p>")

    # 分隔线
    parts.append(
        f'<p style="width:40px;height:2px;background:{STYLES["accent"]};'
        f'margin:16px auto;border-radius:1px;"></p>'
    )

    # Summary card
    summary = soup.find(class_="summary-card")
    if summary:
        for strong in summary.find_all("strong"):
            text = strong.get_text(strip=True)
            strong.replace_with(BeautifulSoup(
                f'<strong style="color:{STYLES["text"]};font-weight:600;">{text}</strong>',
                "html.parser"
            ))
        inner = summary.decode_contents()
        parts.append(
            f'<section style="background:{STYLES["bg_warm"]};border:1px solid {STYLES["border"]};'
            f'border-radius:12px;padding:16px 18px;text-align:left;font-size:14px;'
            f'line-height:1.85;color:{STYLES["text_secondary"]};">{inner}</section>'
        )

    parts.append("</section>")  # close header

    # TOC (目录)
    toc = soup.find(class_="toc")
    if toc:
        parts.append(
            f'<section style="background:{STYLES["card_bg"]};border:1px solid {STYLES["border"]};'
            f'border-radius:12px;padding:16px 18px;margin:16px 0;">'
            f'<p style="font-size:11px;font-weight:600;color:{STYLES["text_tertiary"]};'
            f'text-transform:uppercase;letter-spacing:1.5px;margin-bottom:10px;">目录</p>'
        )
        for li in toc.find_all("li"):
            a = li.find("a")
            if a:
                icon_span = a.find(class_="toc-icon")
                icon = icon_span.get_text(strip=True) if icon_span else ""
                text = a.get_text(strip=True)
                if icon:
                    text = text.replace(icon, "", 1).strip()
                parts.append(
                    f'<p style="font-size:13px;color:{STYLES["text_secondary"]};margin:4px 0;">'
                    f'{icon} {text}</p>'
                )
        parts.append("</section>")

    # Sections
    for section in soup.find_all("section", class_="section"):
        parts.append(convert_section(section))

    # Footer
    footer = soup.find("footer", class_="footer")
    if footer:
        parts.append(
            f'<section style="text-align:center;padding:24px 0 8px;'
            f'border-top:1px solid {STYLES["border"]};margin-top:20px;">'
        )
        brand = footer.find(class_="footer-brand")
        if brand:
            parts.append(
                f'<p style="font-size:14px;font-weight:600;color:{STYLES["text_secondary"]};margin-bottom:4px;">'
                f'{brand.get_text(strip=True)}</p>'
            )
        for p in footer.find_all("p"):
            if "footer-brand" not in (p.get("class") or []):
                parts.append(
                    f'<p style="color:{STYLES["text_tertiary"]};font-size:11px;line-height:2;">'
                    f'{p.get_text(strip=True)}</p>'
                )
        parts.append("</section>")

    # 阅读原文引导
    parts.append(
        f'<section style="text-align:center;padding:16px 0 24px;">'
        f'<p style="font-size:13px;color:{STYLES["text_tertiary"]};line-height:1.8;">'
        f'👆 点击「阅读原文」查看完整网页版</p>'
        f'</section>'
    )

    # 关闭外层容器
    parts.append("</section>")

    # mp-style-type（微信编辑器兼容标记）
    parts.append('<mp-style-type data-value="3"></mp-style-type>')

    return "\n".join(parts)


def delete_existing_drafts(token):
    """删除现有草稿（可选）"""
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/batchget?access_token={token}",
        json={"offset": 0, "count": 20, "no_content": 1}
    )
    data = r.json()
    deleted = 0
    for item in data.get("item", []):
        media_id = item.get("media_id")
        if media_id:
            r2 = requests.post(
                f"https://api.weixin.qq.com/cgi-bin/draft/delete?access_token={token}",
                json={"media_id": media_id}
            )
            if r2.json().get("errcode", 0) == 0:
                deleted += 1
    return deleted


def push_draft(token, title, content, digest, content_source_url):
    """推送草稿到微信公众号"""
    article = {
        "title": title,
        "author": "AI Daily Brief",
        "digest": digest,
        "content": content,
        "thumb_media_id": THUMB_MEDIA_ID,
        "show_cover_pic": 0,
        "content_source_url": content_source_url,
        "need_open_comment": 0,
    }

    payload = {"articles": [article]}
    data_str = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}",
        data=data_str,
        headers={"Content-Type": "application/json; charset=utf-8"}
    )
    return r.json()


def verify_draft(token):
    """验证最新草稿的完整性"""
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/batchget?access_token={token}",
        json={"offset": 0, "count": 1, "no_content": 0}
    )
    r.encoding = "utf-8"
    data = r.json()
    results = {}
    for item in data.get("item", []):
        for art in item.get("content", {}).get("news_item", []):
            content = art.get("content", "")
            results["title"] = art.get("title", "")
            results["content_length"] = len(content)
            results["chinese_chars"] = len(re.findall(r'[\u4e00-\u9fff]', content))
            results["has_github"] = "GitHub" in content and "今日" in content
            # 统计 GitHub 卡片：查找 "⭐ 今日" 作为标记
            results["github_items"] = content.count("⭐ 今日")
            results["has_read_original"] = "阅读原文" in content
            results["has_footer"] = "AI Daily Brief" in content and "数据来源" in content
            results["has_mp_style"] = "mp-style-type" in content
            results["content_source_url"] = art.get("content_source_url", "")
    return results


def main():
    # 确定日期
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 解析月日用于标题
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        title_date = f"{dt.month}月{dt.day}日"
    except ValueError:
        print(f"❌ 日期格式错误: {date_str}，应为 YYYY-MM-DD")
        sys.exit(1)

    # 检查文件
    brief_path = os.path.join(BRIEF_DIR, f"{date_str}.html")
    if not os.path.exists(brief_path):
        print(f"❌ 日报文件不存在: {brief_path}")
        sys.exit(1)

    print(f"📰 正在处理 {date_str} 日报...")
    print(f"📄 源文件: {brief_path}")

    # 解析 HTML
    soup = parse_brief_html(brief_path)

    # 构建微信 HTML
    wechat_html = build_wechat_html(soup, date_str)
    print(f"✅ 微信 HTML 生成完成，长度: {len(wechat_html)} 字符")

    # 获取 token
    print("🔑 获取 access_token...")
    token = get_access_token()

    # 删除旧草稿
    print("🗑️  清理旧草稿...")
    deleted = delete_existing_drafts(token)
    print(f"   已删除 {deleted} 个旧草稿")

    # 推送
    title = f"AI资讯日报｜{title_date}"
    digest = "AI日报"
    content_source_url = f"{GITHUB_PAGES_BASE}/{date_str}.html"

    print(f"📤 推送草稿: {title}")
    result = push_draft(token, title, wechat_html, digest, content_source_url)

    if "media_id" in result:
        print(f"✅ 推送成功! media_id: {result['media_id']}")
    else:
        print(f"❌ 推送失败: {result}")
        sys.exit(1)

    # 验证
    print("🔍 验证草稿完整性...")
    # 重新获取 token（避免过期）
    token = get_access_token()
    verify = verify_draft(token)

    print(f"\n{'='*50}")
    print(f"📋 验证结果:")
    print(f"   标题: {verify.get('title', 'N/A')}")
    print(f"   内容长度: {verify.get('content_length', 0)} 字符")
    print(f"   中文字符: {verify.get('chinese_chars', 0)} 个")
    print(f"   GitHub 链接: {'✅' if verify.get('has_github') else '❌'}")
    print(f"   阅读原文引导: {'✅' if verify.get('has_read_original') else '❌'}")
    print(f"   Footer: {'✅' if verify.get('has_footer') else '❌'}")
    print(f"   mp-style-type: {'✅' if verify.get('has_mp_style') else '❌'}")
    print(f"   content_source_url: {verify.get('content_source_url', 'N/A')}")
    print(f"{'='*50}")

    all_ok = all([
        verify.get("has_github"),
        verify.get("has_read_original"),
        verify.get("has_footer"),
        verify.get("has_mp_style"),
    ])

    if all_ok:
        print("🎉 全部验证通过！去公众号草稿箱查看吧。")
    else:
        print("⚠️  部分验证未通过，请检查草稿箱。")


if __name__ == "__main__":
    main()
