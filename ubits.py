# -*- coding: utf-8 -*-
"""
cron: 0 10 0 * * *
new Env('piggo');
"""

import json
import os
import re
import sys
import time

# from notify import send  # 导入青龙后自动有这个文件
import requests

requests.packages.urllib3.disable_warnings()
import cloudscraper


def send(a,b):
    pass

def start(cookie):
    max_retries = 3
    retries = 0
    msg = ""
    while retries < max_retries:
        try:
            msg += "第{}次执行签到\n".format(str(retries+1))
            sign_in_url = "https://piggo.me/attendance.php?id=18145"
            headers = {
                'Cookie': cookie,
                'authority': 'piggo.me',
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'zh-CN,zh;q=0.9,und;q=0.8',
                'referer': 'https://piggo.me/attendance.php',
                'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'same-origin',
                "sec-fetch-user": '?1',
                "sec-gpc": '1',
                "upgrade-insecure-requests": '1',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            # 请求url
            scraper = cloudscraper.create_scraper()
            # 请求url
            rsp = scraper.get(url=sign_in_url, headers=headers, timeout=15, verify=True)
            
            # rsp = requests.get(url=sign_in_url, headers=headers, timeout=15, verify=True)
            
            rsp_text = rsp.text
            print(rsp_text)
            success = False
            if "这是您的第" in rsp_text:
                msg += '签到成功!\n'
                # 先匹配当前魔力值信息
                magic_value = re.search(r"魔力值.*?(\d+(\,\d+)?(\.\d+)?)", rsp_text).group(1).replace(',', '')
                msg = msg + "当前魔力值为: " + magic_value + " 。"
                # 匹配当前签到提示
                pattern = r'这是您的第 <b>(\d+)</b>[\s\S]*?今日签到排名：<b>(\d+)</b>'
                result = re.search(pattern, rsp_text)
                result = result.group()
                # 剔除多余字符
                result = result.replace("<b>", "")
                result = result.replace("</b>", "")
                result = result.replace("点击白色背景的圆点进行补签。", "")
                result = result.replace('<span style="float:right">', "")
                msg += result
                success = True
            elif "https://www.gov.cn/" in rsp_text:
                msg += "Cookie值错误!响应跳转到第三方网站,请检查网站cookie值"
            elif "503 Service Temporarily" in rsp_text or "502 Bad Gateway" in rsp_text:
                msg += "服务器异常！\n"
            else:
                msg += "未知异常!\n"
                msg += rsp_text + '\n'
            
            if success:
                print("签到结果: ",msg)
                send("Piggo 签到结果", msg)
                break  # 成功执行签到，跳出循环
            elif retries >= max_retries:
                print("达到最大重试次数，签到失败。")
                send("Piggo 签到结果", msg)
                break
            else:
                retries += 1
                print("等待20秒后进行重试...")
                time.sleep(20)
        except Exception as e:
            print("签到失败，失败原因:"+str(e))
            send("Piggo 签到结果", str(e))
            retries += 1
            if retries >= max_retries:
                print("达到最大重试次数，签到失败。")
                break
            else:
                print("等待20秒后进行重试...")
                time.sleep(20)

if __name__ == "__main__":
    os.environ["Piggo_COOKIE"] = "c_secure_uid=MTgxNDU%3D;c_secure_pass=1ffd47650243d81eb1d47066c7c6faf2;c_secure_token=TPu3uodXI6aO294gFBt1Ugvknrs;c_secure_ssl=eWVhaA%3D%3D;c_secure_tracker_ssl=eWVhaA%3D%3D;c_secure_login=bm9wZQ%3D%3D;sl-session=G7K2XBBVZma7CKyVOkOVoA=="
    cookie = os.getenv("Piggo_COOKIE")
    start(cookie)
