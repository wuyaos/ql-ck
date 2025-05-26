#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cron: 0 10 0 * * *
new Env('思源笔记签到');
"""

import requests
import re
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from notify import send


@dataclass
class SiyuanConfig:
    username: str
    password: str
    base_url: str = "https://ld246.com"
    timeout: int = 30
    max_retries: int = 3
    verify_ssl: bool = True
    
    def __post_init__(self):
        self.validate()
        
    def validate(self):
        """验证配置参数"""
        if not self.username or not self.password:
            raise ValueError("用户名和密码不能为空")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("无效的base_url")


class SiyuanLogger:
    """日志处理类"""
    def __init__(self, name: str = "siyuan_checkin"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)


class SiyuanCheckin:
    """思源笔记签到类"""
    def __init__(self, config: SiyuanConfig):
        self.config = config
        self.logger = SiyuanLogger().logger
        self.session = self._init_session()
        self.cookies: Dict[str, str] = {}
        self.message: str = ""
    
    def _init_session(self) -> requests.Session:
        """初始化会话"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def _get_headers(self, header_type: str = "default") -> Dict[str, str]:
        """获取请求头"""
        common_headers = {
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Cache-Control': 'no-cache',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/109.0.0.0 Safari/537.36'
            ),
            'sec-ch-ua': '^\\^Not_A',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '^\\^Windows^\\^'
        }
        
        headers_map = {
            "login": {
                **common_headers,
                'authority': 'ld246.com',
                'content-type': (
                    'application/x-www-form-urlencoded; '
                    'charset=UTF-8'
                ),
                'origin': self.config.base_url,
                'x-requested-with': 'XMLHttpRequest'
            },
            "checkin": {
                **common_headers,
                'Accept': (
                    'text/html,application/xhtml+xml,application/xml;'
                    'q=0.9,image/webp,image/apng,*/*;q=0.8'
                ),
                'Referer': f'{self.config.base_url}/settings/point',
                'Upgrade-Insecure-Requests': '1'
            },
            "default": common_headers
        }
        
        return headers_map.get(header_type, common_headers)
    
    def _append_message(self, msg: str):
        """添加消息到通知内容"""
        self.message += f"{msg}\n"
    
    def login(self) -> bool:
        """登录"""
        try:
            password_md5 = hashlib.md5(
                self.config.password.encode('utf-8')
            ).hexdigest()
            
            data = {
                'nameOrEmail': self.config.username,
                'userPassword': password_md5,
                'captcha': ''
            }
            
            response = self.session.post(
                f'{self.config.base_url}/login',
                data=json.dumps(data),
                headers=self._get_headers("login"),
                timeout=self.config.timeout,
                verify=self.config.verify_ssl
            )
            
            if response.status_code != 200:
                error_msg = f"登录请求失败: HTTP {response.status_code}"
                self.logger.error(error_msg)
                self._append_message(error_msg)
                return False
            
            result = response.json()
            if 'tokenName' not in result or 'token' not in result:
                error_msg = "登录响应格式错误"
                self.logger.error(error_msg)
                self._append_message(error_msg)
                return False
            
            self.cookies = {result['tokenName']: result['token']}
            success_msg = "登录成功"
            self.logger.info(success_msg)
            self._append_message(success_msg)
            return True
            
        except requests.exceptions.RequestException as e:
            error_msg = f"登录请求异常: {str(e)}"
            self.logger.error(error_msg)
            self._append_message(error_msg)
            return False
        except json.JSONDecodeError as e:
            error_msg = f"登录响应解析失败: {str(e)}"
            self.logger.error(error_msg)
            self._append_message(error_msg)
            return False
        except Exception as e:
            error_msg = f"登录过程发生未知错误: {str(e)}"
            self.logger.error(error_msg)
            self._append_message(error_msg)
            return False
    
    def get_checkin_status(self) -> Optional[str]:
        """获取签到状态"""
        try:
            response = self.session.get(
                f'{self.config.base_url}/activity/checkin',
                headers=self._get_headers("checkin"),
                cookies=self.cookies,
                timeout=self.config.timeout,
                verify=self.config.verify_ssl
            )
            
            if response.status_code != 200:
                error_msg = f"获取签到状态失败: HTTP {response.status_code}"
                self.logger.error(error_msg)
                self._append_message(error_msg)
                return None
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            error_msg = f"获取签到状态请求异常: {str(e)}"
            self.logger.error(error_msg)
            self._append_message(error_msg)
            return None
    
    def parse_checkin_result(self, html_text: str) -> Dict[str, Any]:
        """解析签到结果"""
        result = {
            'status': 'unknown',
            'score_get': None,
            'score_total': None,
            'rank_info': None
        }
        
        try:
            if "领取今日签到奖励" in html_text:
                result['status'] = 'not_checked'
                checkin_links = re.findall(
                    r"<a href=\"([^>^\"]*)\"[^>]*>领取今日签到奖励</a>",
                    html_text,
                    re.S
                )
                if checkin_links:
                    result['checkin_link'] = checkin_links[0]
            elif "今日签到获得" in html_text:
                result['status'] = 'checked'
                score_get = re.search(
                    "(今日签到获得.*积分)",
                    html_text
                )
                if score_get:
                    result['score_get'] = re.sub(
                        "<[^<]*>",
                        "",
                        score_get.group(1)
                    )
                score_total = re.search("(积分余额[\s0-9]*)", html_text)
                if score_total:
                    result['score_total'] = score_total.group(1)
            
            return result
            
        except Exception as e:
            error_msg = f"解析签到结果异常: {str(e)}"
            self.logger.error(error_msg)
            self._append_message(error_msg)
            return result
    
    def get_rank_info(self) -> Optional[str]:
        """获取排名信息"""
        try:
            response = self.session.get(
                f'{self.config.base_url}/top/checkin/today',
                headers=self._get_headers("checkin"),
                cookies=self.cookies,
                timeout=self.config.timeout,
                verify=self.config.verify_ssl
            )
            
            if response.status_code != 200:
                error_msg = f"获取排名信息失败: HTTP {response.status_code}"
                self.logger.error(error_msg)
                self._append_message(error_msg)
                return None
            
            text = response.text
            pattern = (
                f"([0-9]+)\.\s+<a[^<]+aria-name=\"{self.config.username}"
            )
            index_match = re.search(pattern, text, re.S)
            if not index_match:
                return None
            
            index = index_match.group(1)
            total_count = len(
                re.findall("([0-9]+)\.\s+<a[^<]+aria-name=\"", text, re.S)
            )
            
            if total_count > 0:
                percentage = (1 - int(index) / total_count) * 100
                rank_msg = f"今日奖励排行第{index},超过了{percentage:.2f}%的人"
                self._append_message(rank_msg)
                return rank_msg
            
            return None
            
        except Exception as e:
            error_msg = f"获取排名信息异常: {str(e)}"
            self.logger.error(error_msg)
            self._append_message(error_msg)
            return None
    
    def do_checkin(self) -> bool:
        """执行签到"""
        try:
            html_text = self.get_checkin_status()
            if not html_text:
                return False
            
            result = self.parse_checkin_result(html_text)
            
            if result['status'] == 'checked':
                msg = "已经签到过了"
                self.logger.info(msg)
                self._append_message(msg)
                if result['score_get']:
                    self.logger.info(result['score_get'])
                    self._append_message(result['score_get'])
                if result['score_total']:
                    self.logger.info(result['score_total'])
                    self._append_message(result['score_total'])
                
                rank_info = self.get_rank_info()
                if rank_info:
                    self.logger.info(rank_info)
                return True
            
            if (result['status'] == 'not_checked' and
                    'checkin_link' in result):
                msg = "开始签到"
                self.logger.info(msg)
                self._append_message(msg)
                response = self.session.get(
                    result['checkin_link'],
                    headers=self._get_headers("checkin"),
                    cookies=self.cookies,
                    timeout=self.config.timeout,
                    verify=self.config.verify_ssl
                )
                
                if "今日签到获得" in response.text:
                    msg = "签到成功"
                    self.logger.info(msg)
                    self._append_message(msg)
                    new_result = self.parse_checkin_result(response.text)
                    if new_result['score_get']:
                        self.logger.info(new_result['score_get'])
                        self._append_message(new_result['score_get'])
                    if new_result['score_total']:
                        self.logger.info(new_result['score_total'])
                        self._append_message(new_result['score_total'])
                    
                    rank_info = self.get_rank_info()
                    if rank_info:
                        self.logger.info(rank_info)
                    return True
                
                error_msg = "签到失败"
                self.logger.error(error_msg)
                self._append_message(error_msg)
                return False
            
            error_msg = "签到状态异常"
            self.logger.error(error_msg)
            self._append_message(error_msg)
            return False
                
        except Exception as e:
            error_msg = f"签到过程发生异常: {str(e)}"
            self.logger.error(error_msg)
            self._append_message(error_msg)
            return False


def get_env_config() -> Optional[SiyuanConfig]:
    """从环境变量获取配置"""
    username = os.getenv('SIYUAN_USERNAME')
    password = os.getenv('SIYUAN_PASSWORD')
    
    if not username or not password:
        print("请设置环境变量: SIYUAN_USERNAME 和 SIYUAN_PASSWORD")
        return None
        
    return SiyuanConfig(
        username=username,
        password=password
    )


def main():
    """主函数"""
    config = get_env_config()
    if not config:
        return
    
    checkin = SiyuanCheckin(config)
    title = "思源笔记签到"
    
    if not checkin.login():
        send(title, checkin.message)
        return
    
    success = checkin.do_checkin()
    send(title, checkin.message)
    
    if success:
        print("✅ 签到成功")
    else:
        print("❌ 签到失败")


if __name__ == "__main__":
    main()