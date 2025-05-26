# -*- coding: utf-8 -*-
"""
cron: 0 10 0 * * *
new Env('思源笔记签到');
"""

import requests
import re
import hashlib
import os
from loguru import logger
import urllib3
from notify import send  # 导入青龙后自动有这个文件

# 禁用 InsecureRequestWarning 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


paras = {
    "username": os.environ.get("SIYUAN_USERNAME", ""),
    "password": os.environ.get("SIYUAN_PASSWORD", ""),
}


# https://ld246.com/login?goto=https://ld246.com/settings/point
headers = {
    "authority": "ld246.com",
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://ld246.com",
    "pragma": "no-cache",
    "referer": "https://ld246.com/login?goto=https://ld246.com/settings/point",
    "sec-ch-ua": "^\\^Not_A",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "^\\^Windows^\\^",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36 "
        "Edg/109.0.1518.70"
    ),
    "x-requested-with": "XMLHttpRequest",
}


headersCheckIn = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,"
        "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Referer": "https://ld246.com/settings/point",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36 "
        "Edg/109.0.1518.70"
    ),
    "sec-ch-ua": "^\\^Not_A",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "^\\^Windows^\\^",
}


headersDayliCheck = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,"
        "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Referer": "https://ld246.com/activity/checkin",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36 "
        "Edg/109.0.1518.70"
    ),
    "sec-ch-ua": "^\\^Not_A",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "^\\^Windows^\\^",
}


def getPara(name):
    return paras[name]


def setPara(name, value):
    paras[name] = value
    logger.info(value)
    return value


log_messages = []


def appendLog(tempLog):
    log_messages.append(tempLog)
    logger.info(tempLog)


def printLog():
    final_log = "\n".join(log_messages)
    logger.info(final_log)
    send("思源笔记签到", final_log)


def getMsg(htmltext):
    try:
        scoreGet = re.search("(今日签到获得.*积分)", htmltext).group(1)
        scoreGet = re.sub("<[^<]*>", "", scoreGet)

        scoreTotal = re.search(r"(积分余额[\s0-9]*)", htmltext).group(1)
        appendLog(scoreGet + "\n" + scoreTotal)
        getTopic()
    except Exception as e:
        logger.error(f"获取排行信息失败: {str(e)}")


def getTopic():
    resp = session.get(
        "https://ld246.com/top/checkin/today",
        data=data,
        headers=headersDayliCheck,
        verify=False,
    )
    pattern = r"([0-9]+)\.\s+<a[^<]+aria-name=\""
    username_pattern = pattern + getPara("username")
    index = re.search(username_pattern, resp.text, re.S).group(1)
    count = len(re.findall(pattern, resp.text, re.S))
    percentage = str((1 - int(index) / count) * 100)
    appendLog(f"今日奖励排行第{index},超过了{percentage}%的人")


md5 = hashlib.md5(getPara("password").encode(encoding="utf-8")).hexdigest()
data = f'{{"nameOrEmail":{getPara("username")},"userPassword":{md5},' '"captcha":""}}'
session = requests.session()
response = session.post(
    "https://ld246.com/login?goto=https://ld246.com/settings/point",
    data=data,
    headers=headers,
    verify=False,
)

# 登录成功或失败
try:
    tokenName = response.json()["tokenName"]
    token = response.json()["token"]
    logger.info("登录成功")
except KeyError:
    logger.error("登录失败，未能获取 tokenName 或 token")
    exit(1)

cookie = {tokenName: token}

response = session.get(
    "https://ld246.com/activity/checkin",
    cookies=cookie,
    headers=headersCheckIn,
    verify=False,
)

if response.text.find("领取今日签到奖励") >= 0:
    res = re.findall(
        r"<a href=\"([^>^\"]*)\"[^>]*>领取今日签到奖励</a>", response.text, re.S
    )
    if len(res) > 0:
        logger.info(res[0])
        appendLog("开始签到")

        response = session.get(res[0], headers=headersDayliCheck, verify=False)
        if response.text.find("今日签到获得") >= 0:
            appendLog("签到成功")
            getMsg(response.text)
    else:
        appendLog("未找到签到链接")
elif response.text.find("今日签到获得") >= 0:
    appendLog("已经签到过了")
    getMsg(response.text)
else:
    logger.error(response.text)
    appendLog("签到异常")
printLog()