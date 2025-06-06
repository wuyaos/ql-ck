#!/usr/bin/env python3
# coding: utf-8
'''
项目名称: Ukenn2112 / qinglong_Task_Delete
Author: Ukenn2112
功能：批量删除qinglong任务及其脚本
Date: 2022/02/20 下午21:45
cron: 0
new Env('qinglong 批量删除任务');
'''
import json
import logging
import os
import shutil
import sys
import time

import requests

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

rootdirs = ["/ql/data/scripts",
            "/ql/data/repo"]

DELETENAME = str(os.getenv("DELETE_NAME"))
if not DELETENAME:
    logger.info('未检测到删除变量,请设置 DELETE_NAME\n')
    sys.exit(1)
else:
    delete_names = DELETENAME.split("&")
    logger.info(f'您选择删除的任务前缀为 {delete_names}')

ipport = os.getenv("IPPORT")
if not ipport:
    logger.info(
        "如果青龙登录失败请在环境变量中添加你的真实 IP:端口\n变量名：IPPORT\t值：127.0.0.1:5700\n或在 config.sh 中添加 export IPPORT='127.0.0.1:5700'\n"
    )
    ipport = "localhost:5700"
else:
    ipport = ipport.lstrip("http://").rstrip("/")


def delete_file():
    """删除文件"""
    logger.info("⚠️ 开始删除任务脚本文件")
    for rootdir in rootdirs:
        file_list = os.listdir(rootdir)
        for files in file_list:
            for delete_name in delete_names:
                if delete_name in files:
                    try:
                        shutil.rmtree(rootdir+'/'+files)
                        logger.info(f"❌ 已删除 {rootdir}/{files} 目录及其目录下的脚本文件")
                    except NotADirectoryError:
                        os.remove(rootdir+'/'+files)
                        logger.info(f"❌ 已删除脚本文件 {rootdir}/{files}")


def ql_login():
    """返回青龙 Token"""
    path = '/ql/data/config/auth.json'
    if os.path.isfile(path):
        with open(path, "r") as file:
            auth = file.read()
            file.close()
        auth = json.loads(auth)
        username = auth["username"]
        password = auth["password"]
        token = auth["token"]
        if token == '':
            return get_qltoken(username, password)
        else:
            url = f"http://{ipport}/api/user"
            headers = {
                'Authorization': f'Bearer {token}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.71 Safari/537.36 Edg/94.0.992.38'
            }
            res = requests.get(url=url, headers=headers)
            if res.status_code == 200:
                return token
            else:
                return get_qltoken(username, password)
    else:
        logger.info("没有发现auth文件, 你这是青龙吗???")
        sys.exit(1)


def get_qltoken(username, password):
    """登录青龙 返回值 token"""
    logger.info("Token失效, 新登陆\n")
    url = f"http://{ipport}/api/user/login"
    payload = {
        'username': username,
        'password': password
    }
    payload = json.dumps(payload)
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    try:
        res = requests.post(url=url, headers=headers, data=payload)
        token = json.loads(res.text)["data"]['token']
    except Exception as err:
        logger.debug(str(err))
        logger.info("青龙登录失败, 请检查面板状态!")
        sys.exit(1)
    else:
        return token


def get_tasklist(token) -> list:
    """获取青龙任务"""
    tasklist = []
    t = round(time.time() * 1000)
    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {token}'}
    url = f"http://{ipport}/api/crons?searchValue=&t={t}"
    response = requests.get(url=url, headers=headers)
    datas = json.loads(response.content.decode("utf-8"))
    if datas.get("code") == 200:
        tasklist = datas.get("data")
    return tasklist['data']


def filter_delete(tasklist: list):
    """筛选任务 删除"""
    logger.info("\n正在筛选需要删除的任务...")
    delete_id_list = []
    for task in tasklist:
        for delete_name in delete_names:
            if task.get("command").find(delete_name) != -1:
                logger.info(f"【❌ 删除任务】{task.get('command')}")
                if task.get("id") is not None:
                    delete_id_list.append(task.get("id"))
                else:
                    delete_id_list.append(task.get("_id"))
    return delete_id_list


def delete_tasks(ids, token):
    """开始删除"""
    logger.info("\n开始删除任务...")
    t = round(time.time() * 1000)
    url = f"http://{ipport}/api/crons?t={t}"
    data = json.dumps(ids)
    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {token}'}
    response = requests.delete(url=url, headers=headers, data=data)
    datas = json.loads(response.content.decode("utf-8"))
    if datas.get("code") != 200:
        logger.info(f"❌ 出错!!!错误信息为：{datas}")
    else:
        logger.info("🎉 成功删除任务~")


if __name__ == "__main__":
    logger.info("===> 删除任务脚本开始 <===\n")
    delete_file()
    token = ql_login()
    tasklist = get_tasklist(token)
    delete_id_list = filter_delete(tasklist)
    if delete_id_list:
        delete_tasks(delete_id_list, token)
    else:
        logger.info("❌ 未找到需要删除的任务")
    logger.info("===> 删除任务脚本结束 <===\n")
    sys.exit(0)
