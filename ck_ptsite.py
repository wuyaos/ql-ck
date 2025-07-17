# -*- coding: utf-8 -*-
"""
cron: 0 10,16,22 * * *
new Env('PT多站签到');

================================================================================
脚本使用说明:
本脚本通过单一环境变量 `PT_CHECKIN_CONFIG` 进行配置，该变量必须是一个有效的JSON字符串。

核心配置结构:
{
  "cookie_cloud": { ... }, // 可选，CookieCloud凭据
  "sites": { ... }        // 必需，要签到的站点
}

一、 `sites` 对象 (必需)
--------------------------------------------------------------------------------
`sites` 是一个JSON对象，"键" 是站点名称 (必须与脚本内置的SITES_CONFIG匹配)，
"值" 决定了如何获取该站点的Cookie:

1.  **使用 CookieCloud**:
    将站点的值设置为 `""` (空字符串) 或 `null`。
    脚本会自动从 CookieCloud 获取对应域名的 Cookie。

    示例: "GGPT": ""

2.  **直接提供 Cookie**:
    将站点的值设置为一个**非空字符串**，这个字符串就是该站点的Cookie。

    示例: "siqi": "uid=789; pass=xyz;"

二、 `cookie_cloud` 对象 (可选)
--------------------------------------------------------------------------------
如果 `sites` 对象中**至少有一个**站点配置为使用 CookieCloud，则此 `cookie_cloud`
键是必需的。

`cookie_cloud` 对象包含以下三个键:
- `url`: CookieCloud 服务的 URL (例如: "http://192.168.1.2:8088")
- `uuid`: 你的用户 UUID
- `password`: 你的加密密码

---
完整配置示例:
{
  "cookie_cloud": {
    "url": "http://your-cc-url.com",
    "uuid": "your-uuid",
    "password": "your-password"
  },
  "sites": {
    "GGPT": "",                // 此站点将使用 CookieCloud
    "HDtime": null,            // 此站点也将使用 CookieCloud
    "siqi": "uid=789; pass=xyz;" // 此站点使用直接提供的 Cookie
  }
}

如果所有站点都直接提供Cookie，`cookie_cloud` 键可以省略。
================================================================================
"""

import requests
import re
import os
import time
import json
import urllib3
from loguru import logger
import sys
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

# 数据库文件名
DB_FILE = "checkin_status.db"

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


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# CookieCloud 相关代码
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
try:
    from PyCookieCloud import PyCookieCloud
except ImportError:
    PyCookieCloud = None
    logger.warning("⚠️ PyCookieCloud 模块未安装，CookieCloud功能将不可用。")
    logger.warning("请执行 `pip install PyCookieCloud` 进行安装。")


class CookieCloud:
    def __init__(self, url: str, uuid: str, password: str):
        if PyCookieCloud is None:
            raise ImportError("PyCookieCloud 模块未安装，无法初始化 CookieCloud。")
        self.client = PyCookieCloud(url, uuid, password)
        self.cookies: dict | None = None

    def _fetch_all_cookies(self):
        logger.info('☁️ 从 CookieCloud 获取所有 cookies...')
        try:
            decrypted_data = self.client.get_decrypted_data()
            if not decrypted_data:
                logger.error('❌ 从 CookieCloud 解密数据失败。')
                self.cookies = {}
                return

            self.cookies = self._process_cookies(decrypted_data)
            logger.success('✅ 成功从 CookieCloud 获取所有 cookies。')
        except Exception as e:
            logger.error(f'❌ 从 CookieCloud 获取所有 cookies 时发生错误: {e}')
            self.cookies = {}

    def _process_cookies(self, decrypted_data: dict) -> dict:
        processed_cookies = {}
        for domain, content_list in decrypted_data.items():
            if not content_list or all(
                c.get("name") == "cf_clearance" for c in content_list
            ):
                continue

            cookie_list = [
                f"{c.get('name')}={c.get('value')}"
                for c in content_list if c.get("name") and c.get("value")
            ]

            if domain.startswith('.'):
                domain = domain[1:]
            processed_cookies[domain] = "; ".join(cookie_list)
        return processed_cookies

    def get_cookies(self, domain: str) -> str | None:
        """
        Get cookies from CookieCloud for a specific domain.
        :param domain: The domain to get cookies for.
        :return: A string of cookies, or None if not found.
        """
        if isinstance(domain, bytes):
            try:
                domain = domain.decode('utf-8')
            except UnicodeDecodeError:
                logger.warning('⚠️ 域名解码失败，无法获取 cookies。')
                return None

        if not domain:
            logger.warning('⚠️ 无效或空的域名，无法获取 cookies。')
            return None

        if self.cookies is None:
            self._fetch_all_cookies()

        if not self.cookies:
            logger.warning('⚠️ 在 CookieCloud 中未找到任何 cookies。')
            return None

        # Direct match
        if cookie := self.cookies.get(domain):
            logger.success(f'✅ 成功获取域名 {domain} 的 cookies。')
            return cookie

        # Subdomain match
        for d, c in self.cookies.items():
            if domain.endswith(d):
                logger.info(f"🔍 在 {domain} 未找到 cookie，但在 {d} 找到了。")
                return c

        logger.warning(f'⚠️ 未找到域名 {domain} 的 cookies。')
        return None


def load_configuration():
    """
    从环境变量 PT_CHECKIN_CONFIG 加载并解析统一的配置。
    :return: 一个元组 (cookie_manager, sites_to_checkin)。
             cookie_manager: CookieCloud实例或None。
             sites_to_checkin: 站点配置字典或None。
    """
    config_str = os.getenv("PT_CHECKIN_CONFIG")
    if not config_str:
        logger.error("❌ 环境变量 `PT_CHECKIN_CONFIG` 未设置！")
        return None, None

    try:
        config = json.loads(config_str)
    except json.JSONDecodeError:
        logger.error("❌ `PT_CHECKIN_CONFIG` 环境变量格式错误，不是有效的JSON。")
        return None, None

    if 'sites' not in config or not isinstance(config['sites'], dict):
        logger.error("❌ 配置中缺少 'sites' 键，或其值不是一个对象。")
        return None, None

    sites_to_checkin = config['sites']
    cookie_manager = None

    # 检查是否有站点需要使用CookieCloud
    needs_cc = any(
        not value for value in sites_to_checkin.values()
    )

    if needs_cc:
        logger.info("☁️ 检测到需要使用 CookieCloud 的站点。")
        if PyCookieCloud is None:
            logger.error("❌ 配置了使用CookieCloud，但PyCookieCloud模块未安装。")
            return None, None

        cc_config = config.get('cookie_cloud')
        if not cc_config:
            logger.error("❌ 配置了使用CookieCloud，但缺少 'cookie_cloud' 配置块。")
            return None, None

        url = cc_config.get('url')
        uuid = cc_config.get('uuid')
        password = cc_config.get('password')

        if not (url and uuid and password):
            logger.error("❌ CookieCloud 配置不完整 (需要 url, uuid, password)。")
            return None, None

        try:
            cookie_manager = CookieCloud(url, uuid, password)
            logger.info("✅ CookieCloud 管理器初始化成功。")
        except ImportError as e:
            logger.error(f"❌ 初始化 CookieCloud 失败: {e}")
            return None, None

    logger.info("✅ 配置加载成功。")
    return cookie_manager, sites_to_checkin


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# 数据库和签到逻辑
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++


def init_db():
    """初始化数据库和表"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS checkin_log (
                site_name TEXT PRIMARY KEY,
                last_checkin_date TEXT
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")


def check_if_signed_today(site_name):
    """检查今天是否已经签到过"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        sql = "SELECT last_checkin_date FROM checkin_log WHERE site_name = ?"
        cursor.execute(sql, (site_name,))
        result = cursor.fetchone()
        conn.close()
        if result:
            last_date_str = result[0]
            today_str = datetime.now().strftime('%Y-%m-%d')
            if last_date_str == today_str:
                return True
    except Exception as e:
        logger.error(f"❌ 查询签到状态失败 for {site_name}: {e}")
    return False


def record_signin(site_name):
    """记录签到成功"""
    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        sql = (
            "REPLACE INTO checkin_log (site_name, last_checkin_date) "
            "VALUES (?, ?)"
        )
        cursor.execute(sql, (site_name, today_str))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ 记录签到状态失败 for {site_name}: {e}")


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
    },
    {
        "name": "siqi",
        "sign_in_url": "https://si-qi.xyz/attendance.php",
        "magic_keyword": "魔力值",
        "headers": {
            'authority': 'si-qi.xyz',
            'referer': 'https://si-qi.xyz/attendance.php',
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
                record_signin(site_name)

                magic_keyword = site_config["magic_keyword"]
                magic_pattern = rf"{magic_keyword}.*?(\d+(?:,\d+)*(?:\.\d+)?)"
                magic_match = re.search(magic_pattern, rsp_text)
                if magic_match:
                    magic_value = magic_match.group(1).replace(',', '')
                    msg += f"当前{magic_keyword}为: {magic_value}。 "

                pattern = (
                    r'这是您的第 <b>(\d+)</b>[\s\S]*?'
                    r'今日签到排名：<b>(\d+)</b>'
                )
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
    格式化签到结果并发送通知
    :param results: 签到结果列表
    """
    if not results:
        logger.info("没有签到结果，无需发送通知。")
        return

    valid_results = [res for res in results if res is not None]
    if not valid_results:
        logger.info("所有任务均已跳过，无需发送通知。")
        return

    content_lines = []
    text = (
        f"📢 执行结果\n"
        f"🕐 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    content_lines.append(text)

    for res in valid_results:
        line = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{res['site']}:\t\t{res['status']}\n"
            f"📢{res['message']}"
        )
        content_lines.append(line)

    plain_text_content = "\n".join(content_lines)

    logger.info("准备发送汇总通知...")
    send("【PT多站签到报告】", plain_text_content)
    logger.info("汇总通知已发送。")


def main():
    logger.info("===== 开始执行PT站签到任务 =====")
    init_db()
    cookie_manager, sites_to_checkin = load_configuration()

    if not sites_to_checkin:
        logger.error("❌ 任务终止，无法获取任何有效的站点配置。")
        return

    # 将SITES_CONFIG转换为字典以便快速查找
    site_config_map = {s['name']: s for s in SITES_CONFIG}
    results = []

    for site_name, cookie_value in sites_to_checkin.items():
        if site_name not in site_config_map:
            logger.warning(f"⚠️ 发现未知站点配置 '{site_name}'，已跳过。")
            continue

        site_config = site_config_map[site_name]

        if check_if_signed_today(site_name):
            msg = "今日已成功签到，跳过。"
            logger.info(f"🟢 [{site_name}] {msg}")
            results.append({
                'site': site_name,
                'status': '🟢 跳过',
                'message': msg
            })
            continue

        cookie = None
        # 如果cookie_value是真值(非空字符串)，则直接使用
        if cookie_value:
            cookie = cookie_value
        # 否则，尝试从CookieCloud获取
        elif cookie_manager:
            domain = urlparse(site_config['sign_in_url']).netloc
            cookie = cookie_manager.get_cookies(domain)
            if not cookie:
                msg = f"未能从CookieCloud获取到 {domain} 的Cookie，跳过该站点。"
                logger.warning(f"⚠️ [{site_name}] {msg}")
                results.append({
                    'site': site_name,
                    'status': '🟡 跳过',
                    'message': msg
                })
                continue
        # 既没有直接提供cookie，也没有cookie_manager
        else:
            msg = f"站点 {site_name} 未提供直接的Cookie，且未配置CookieCloud，跳过。"
            logger.warning(f"⚠️ [{site_name}] {msg}")
            results.append({
                'site': site_name,
                'status': '🟡 跳过',
                'message': msg
            })
            continue

        if cookie:
            result = sign_in(site_config, cookie)
            results.append(result)

        time.sleep(2)

    format_and_send_notification(results)
    logger.info("===== 所有站点签到任务执行完毕 =====")


if __name__ == "__main__":
    main()