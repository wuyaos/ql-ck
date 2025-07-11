# -*- coding: utf-8 -*-
"""
cron: 0 10 0 * * *
new Env('PT多站签到');
"""

import requests
import re
import os
import time
import json
import urllib3
from loguru import logger
import sys

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置 loguru
logger.remove()
log_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<level>{message}</level>"
)
logger.add(sys.stdout, format=log_format)


# 通知服务
try:
    from notify import send
except ImportError:
    logger.warning("⚠️ `notify.py` not found, notifications will be skipped.")

    def send(title, content):
        logger.info(f"Notification -> Title: {title}, Content: {content}")


# PT站点配置
SITES_CONFIG = [
    {
        "name": "GGPT",
        "sign_in_url": "https://www.gamegamept.com/attendance.php",
        "magic_keyword": "G值",
        "headers": {
            'authority': 'www.gamegamept.com',
            'referer': 'https://www.gamegamept.com/attendance.php',
        }
    },
    {
        "name": "HDtime",
        "sign_in_url": "https://hdtime.org/attendance.php",
        "magic_keyword": "魔力值",
        "headers": {
            'authority': 'hdtime.org',
            'referer': 'https://hdtime.org/attendance.php',
        }
    }
]

# 通用請求頭
COMMON_HEADERS = {
    'accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,'
        'image/webp,image/apng,*/*;q=0.8,'
        'application/signed-exchange;v=b3;q=0.7'
    ),
    'accept-language': 'zh-CN,zh;q=0.9,und;q=0.8',
    'sec-ch-ua': (
        '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"'
    ),
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    "sec-fetch-user": '?1',
    "sec-gpc": '1',
    "upgrade-insecure-requests": '1',
    'user-agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
}


def get_cookies_from_env():
    """从环境变量 PT_COOKIES 中获取 cookies"""
    cookies_str = os.getenv("PT_COOKIES")
    if not cookies_str:
        logger.error("❌ 环境变量 `PT_COOKIES` 未设置！")
        return None
    try:
        return json.loads(cookies_str)
    except json.JSONDecodeError:
        logger.error("❌ `PT_COOKIES` 环境变量格式错误，不是有效的JSON。")
        return None


def sign_in(site_config, cookie):
    """
    通用的签到函数
    :param site_config: 站点配置字典
    :param cookie: 对应站点的cookie字符串
    :return: 包含签到结果的字典
    """
    site_name = site_config["name"]
    logger.info(f"开始为站点 [{site_name}] 执行签到...")

    max_retries = 3
    retries = 0

    headers = COMMON_HEADERS.copy()
    headers.update(site_config["headers"])
    headers['Cookie'] = cookie

    while retries < max_retries:
        try:
            logger.info(f"[{site_name}] 第 {retries + 1} 次尝试签到...")

            response = requests.get(
                url=site_config["sign_in_url"],
                headers=headers,
                timeout=15,
                verify=False
            )
            response.raise_for_status()

            rsp_text = response.text
            msg = ""

            if "这是您的第" in rsp_text:
                msg += '🎉 签到成功! '

                magic_keyword = site_config["magic_keyword"]
                magic_pattern = rf"{magic_keyword}.*?(\d+(?:,\d+)*(?:\.\d+)?)"
                magic_match = re.search(magic_pattern, rsp_text)
                if magic_match:
                    magic_value = magic_match.group(1).replace(',', '')
                    msg += f"当前{magic_keyword}为: {magic_value}。 "

                pattern = r'这是您的第 <b>(\d+)</b>[\s\S]*?今日签到排名：<b>(\d+)</b>'
                result_match = re.search(pattern, rsp_text)
                if result_match:
                    result = result_match.group(0)
                    result = result.replace("<b>", "").replace("</b>", "")
                    result = result.replace(
                        "点击白色背景的圆点进行补签。", ""
                    ).replace('<span style="float:right">', "")
                    msg += result

                logger.info(f"✅ [{site_name}] {msg.strip()}")
                return {
                    'site': site_name,
                    'status': '✅ 成功',
                    'message': msg.strip()
                }

            elif "https://www.gov.cn/" in rsp_text:
                msg = "Cookie值错误! 响应跳转到第三方网站, 请检查网站cookie值"
                logger.error(f"❌ [{site_name}] {msg}")
                return {
                    'site': site_name,
                    'status': '🍪 Cookie失效',
                    'message': msg
                }

            elif ("503 Service Temporarily" in rsp_text or
                  "502 Bad Gateway" in rsp_text):
                msg = "服务器异常 (50x)！"
                logger.warning(f"⚠️ [{site_name}] {msg}")

            else:
                msg = "未知异常!"
                logger.error(f"❌ [{site_name}] {msg}\n响应内容: {rsp_text[:200]}")

        except requests.exceptions.RequestException as e:
            msg = f"请求失败，原因: {e}"
            logger.error(f"❌ [{site_name}] {msg}")

        retries += 1
        if retries < max_retries:
            logger.info(f"[{site_name}] 等待20秒后进行重试...")
            time.sleep(20)

    final_msg = f"达到最大重试次数({max_retries}次)，签到失败。"
    logger.error(f"❌ [{site_name}] {final_msg}")
    return {
        'site': site_name,
        'status': '❌ 失败',
        'message': final_msg
    }


def format_and_send_notification(results):
    """
    格式化签到结果为Markdown表格并发送通知
    :param results: 签到结果列表
    """
    if not results:
        logger.info("没有签到结果，无需发送通知。")
        return

    markdown_content = "| 站点 | 状态 | 详情 |\n| :--- | :--- | :--- |\n"
    for res in results:
        markdown_content += (
            f"| {res['site']} | {res['status']} | {res['message']} |\n"
        )

    logger.info("准备发送汇总通知...")
    send("PT多站签到报告", markdown_content)
    logger.info("汇总通知已发送。")


def main():
    logger.info("===== 开始执行PT站签到任务 =====")
    all_cookies = get_cookies_from_env()

    if not all_cookies:
        logger.error("❌ 任务终止，无法获取Cookies。")
        return

    results = []
    for site in SITES_CONFIG:
        site_name = site["name"]
        if site_name in all_cookies:
            cookie = all_cookies[site_name]
            result = sign_in(site, cookie)
            results.append(result)
        else:
            msg = "未在环境变量中找到Cookie配置，跳过该站点。"
            logger.warning(f"⚠️ [{site_name}] {msg}")
            results.append({
                'site': site_name,
                'status': '🟡 跳过',
                'message': msg
            })

        time.sleep(2)

    format_and_send_notification(results)
    logger.info("===== 所有站点签到任务执行完毕 =====")


if __name__ == "__main__":
    main()