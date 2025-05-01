"""
cron: 0 */6 * * *
new Env("Linux.Do 签到")
"""
import os
import random
import time
import functools
import sys
import requests
import re
from loguru import logger
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from tabulate import tabulate
from notify import send  # 导入青龙后自动有这个文件

def retry_decorator(retries=3):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:  # 最后一次尝试
                        logger.error(f"函数 {func.__name__} 最终执行失败: {str(e)}")
                    logger.warning(f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}")
                    time.sleep(1)
            return None

        return wrapper

    return decorator


os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

USERNAME = os.environ.get("LINUXDO_USERNAME")
PASSWORD = os.environ.get("LINUXDO_PASSWORD")
BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in ['false', '0', 'off']
if not USERNAME:
    USERNAME = os.environ.get('USERNAME')
if not PASSWORD:
    PASSWORD = os.environ.get('PASSWORD')

HOME_URL = "https://linux.do/"
LOGIN_URL = "https://linux.do/login"


class LinuxDoBrowser:
    def __init__(self) -> None:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_window_size(1920, 1080)
        self.driver.get(HOME_URL)
        self.wait = WebDriverWait(self.driver, 10)

    def login(self):
        logger.info("开始登录")
        self.driver.get(LOGIN_URL)
        time.sleep(2)
        
        try:
            username_input = self.wait.until(EC.presence_of_element_located((By.ID, "login-account-name")))
            username_input.send_keys(USERNAME)
            time.sleep(2)
            
            password_input = self.driver.find_element(By.ID, "login-account-password")
            password_input.send_keys(PASSWORD)
            time.sleep(2)
            
            login_button = self.driver.find_element(By.ID, "login-button")
            login_button.click()
            time.sleep(10)
            
            user_ele = self.driver.find_element(By.ID, "current-user")
            if user_ele:
                logger.info("登录成功")
                return True
        except (TimeoutException, NoSuchElementException) as e:
            logger.error(f"登录失败: {str(e)}")
            return False
            
        logger.error("登录失败")
        return False

    def click_topic(self):
        topic_list = self.driver.find_elements(By.CSS_SELECTOR, "#list-area .title")
        logger.info(f"发现 {len(topic_list)} 个主题帖")
        for topic in topic_list:
            self.click_one_topic(topic.get_attribute("href"))

    @retry_decorator()
    def click_one_topic(self, topic_url):
        self.driver.execute_script("window.open(arguments[0]);", topic_url)
        self.driver.switch_to.window(self.driver.window_handles[-1])
        
        if random.random() < 0.3:  # 0.3 * 30 = 9
            self.click_like(self.driver)
        self.browse_post()
        
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])

    def browse_post(self):
        prev_scroll_pos = None
        # 开始自动滚动，最多滚动10次
        for _ in range(10):
            # 随机滚动一段距离
            scroll_distance = random.randint(550, 650)  # 随机滚动 550-650 像素
            logger.info(f"向下滚动 {scroll_distance} 像素...")
            self.driver.execute_script(f"window.scrollBy(0, {scroll_distance})")
            logger.info(f"已加载页面: {self.driver.current_url}")

            if random.random() < 0.03:  # 33 * 4 = 132
                logger.success("随机退出浏览")
                break

            # 检查是否到达页面底部
            current_scroll_pos = self.driver.execute_script("return window.scrollY;")
            scroll_height = self.driver.execute_script("return document.documentElement.scrollHeight;")
            window_height = self.driver.execute_script("return window.innerHeight;")
            at_bottom = current_scroll_pos + window_height >= scroll_height
            
            if current_scroll_pos == prev_scroll_pos and at_bottom:
                logger.success("已到达页面底部，退出浏览")
                break
                
            prev_scroll_pos = current_scroll_pos

            # 动态随机等待
            wait_time = random.uniform(2, 4)  # 随机等待 2-4 秒
            logger.info(f"等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)

    def run(self):
        if not self.login(): # 登录
            logger.error("登录失败，程序终止")
            self.driver.quit()
            sys.exit(1)  # 使用非零退出码终止整个程序
        
        if BROWSE_ENABLED:
            self.click_topic() # 点击主题
            logger.info("完成浏览任务")
            
        self.print_connect_info() # 打印连接信息
        self.send_notifications(BROWSE_ENABLED) # 发送通知
        self.driver.quit()

    def click_like(self, driver):
        try:
            # 专门查找未点赞的按钮
            like_buttons = driver.find_elements(By.CSS_SELECTOR, '.discourse-reactions-reaction-button[title="点赞此帖子"]')
            if like_buttons:
                logger.info("找到未点赞的帖子，准备点赞")
                like_buttons[0].click()
                logger.info("点赞成功")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info("帖子可能已经点过赞了")
        except Exception as e:
            logger.error(f"点赞失败: {str(e)}")

    def print_connect_info(self):
        logger.info("获取连接信息")
        self.driver.execute_script("window.open('https://connect.linux.do/');")
        self.driver.switch_to.window(self.driver.window_handles[-1])
        
        rows = self.driver.find_elements(By.CSS_SELECTOR, "table tr")
        info = []

        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 3:
                project = cells[0].text.strip()
                current = cells[1].text.strip()
                requirement = cells[2].text.strip()
                info.append([project, current, requirement])

        print("--------------Connect Info-----------------")
        print(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))

        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])

    def send_notifications(self, browse_enabled):
        status_msg = "✅每日登录成功"
        if browse_enabled:
            status_msg += " + 浏览任务完成"
        send("Linux.Do 签到结果", status_msg)


if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("Please set USERNAME and PASSWORD")
        exit(1)
    l = LinuxDoBrowser()
    l.run()
