import os
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 全局配置 ---
# 从环境变量读取机密信息
# 优先使用的 Cookie
HIDENCLOUD_COOKIE = os.environ.get('HIDENCLOUD_COOKIE')
# 备用登录方案的邮箱和密码
HIDENCLOUD_EMAIL = os.environ.get('HIDENCLOUD_EMAIL')
HIDENCLOUD_PASSWORD = os.environ.get('HIDENCLOUD_PASSWORD')

# 目标网页 URL
BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"
SERVICE_URL = f"{BASE_URL}/service/62037/manage"

# Cookie 名称
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"

def log(message):
    """打印带时间戳的日志"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def login(page):
    """
    处理登录逻辑。
    1. 优先尝试使用 Cookie 登录。
    2. 如果 Cookie 失效或不存在，则使用账号密码进行登录。
    """
    log("开始登录流程...")

    # --- 方案一：Cookie 登录 ---
    if HIDENCLOUD_COOKIE:
        log("检测到 HIDENCLOUD_COOKIE，尝试使用 Cookie 登录。")
        try:
            # 设置 Cookie
            cookie = {
                'name': COOKIE_NAME,
                'value': HIDENCLOUD_COOKIE,
                'domain': 'dash.hidencloud.com',
                'path': '/',
                'expires': int(time.time()) + 3600 * 24 * 365, # 设置一年有效期
                'httpOnly': True,
                'secure': True,
                'sameSite': 'Lax'
            }
            page.context.add_cookies([cookie])
            log("Cookie 已设置。正在访问服务管理页面...")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)

            # 验证登录是否成功
            # 如果页面 URL 包含 "auth/login"，说明 Cookie 失效，需要重新登录
            if "auth/login" in page.url:
                log("Cookie 登录失败或会话已过期，将回退到账号密码登录。")
                page.context.clear_cookies() # 清除无效的 Cookie
            else:
                log("✅ Cookie 登录成功！")
                return True
        except Exception as e:
            log(f"使用 Cookie 访问时发生错误: {e}")
            log("将回退到账号密码登录。")
            page.context.clear_cookies()
    else:
        log("未提供 HIDENCLOUD_COOKIE，直接使用账号密码登录。")

    # --- 方案二：账号密码登录 ---
    if not HIDENCLOUD_EMAIL or not HIDENCLOUD_PASSWORD:
        log("❌ 错误: Cookie 无效/未提供，且未提供邮箱和密码。无法继续登录。")
        return False

    log("正在尝试使用邮箱和密码登录...")
    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        log("登录页面已加载。")

        # 填写邮箱和密码
        page.fill('input[name="email"]', HIDENCLOUD_EMAIL)
        log("邮箱已填写。")
        page.fill('input[name="password"]', HIDENCLOUD_PASSWORD)
        log("密码已填写。")

        # 处理 Cloudflare Turnstile 人机验证
        log("正在处理 Cloudflare Turnstile 人机验证...")
        turnstile_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        checkbox = turnstile_frame.locator('input[type="checkbox"]')
        
        # 等待复选框可见并点击
        checkbox.wait_for(state="visible", timeout=30000)
        checkbox.click()
        
        log("已点击人机验证复选框，等待验证结果...")
        
        # 等待验证成功，Cloudflare 会添加一个 'cf-turnstile-response'
        page.wait_for_function("""
            () => document.querySelector('[name="cf-turnstile-response"]') && document.querySelector('[name="cf-turnstile-response"]').value
        """, timeout=60000)
        log("✅ 人机验证成功！")

        # 点击登录按钮
        page.click('button[type="submit"]:has-text("Sign in to your account")')
        log("已点击登录按钮，等待页面跳转...")

        # 等待导航完成
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=60000)

        if "auth/login" in page.url:
            log("❌ 账号密码登录失败，请检查凭据是否正确。")
            page.screenshot(path="login_failure.png")
            return False

        log("✅ 账号密码登录成功！")
        return True

    except PlaywrightTimeoutError as e:
        log(f"❌ 登录过程中超时: {e}")
        page.screenshot(path="login_timeout_error.png")
        return False
    except Exception as e:
        log(f"❌ 登录过程中发生未知错误: {e}")
        page.screenshot(path="login_general_error.png")
        return False

def renew_service(page):
    """
    执行续费流程：
    1. 访问服务管理页面
    2. 点击 Renew
    3. 点击 Create Invoice
    4. 等待 Cloudflare 验证通过
    5. 点击 Pay
    """
    try:
        log("开始执行续费任务...")
        # 确保在正确的服务页面
        if page.url != SERVICE_URL:
            log(f"当前不在目标页面，正在导航至: {SERVICE_URL}")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)
        
        log("服务管理页面已加载。")

        # --- 步骤 1: 点击 Renew 按钮 ---
        log("步骤 1: 正在查找并点击 'Renew' 按钮...")
        renew_button = page.locator('button:has-text("Renew")')
        renew_button.wait_for(state="visible", timeout=30000)
        renew_button.click()
        log("✅ 'Renew' 按钮已点击。")

        # --- 步骤 2: 点击 Create Invoice 按钮 ---
        log("步骤 2: 正在查找并点击 'Create Invoice' 按钮...")
        create_invoice_button = page.locator('button:has-text("Create Invoice")')
        create_invoice_button.wait_for(state="visible", timeout=30000)
        create_invoice_button.click()
        log("✅ 'Create Invoice' 按钮已点击。")

        # --- 步骤 3: 点击 Pay 按钮 ---
        # 在点击 "Create Invoice" 后，网站可能会弹出 Cloudflare 安全验证，需要等待其完成。
        # 我们通过延长查找 "Pay" 按钮的超时时间来给验证过程留出足够时间。
        log("步骤 3: 正在等待发票页面加载（可能会有安全验证），并查找 'Pay' 按钮...")
        
        # 将超时时间从 30 秒增加到 90 秒
        pay_button = page.locator('a:has-text("Pay"), button:has-text("Pay")').first
        pay_button.wait_for(state="visible", timeout=90000) # <--- 【关键修改点】
        
        log("✅ 'Pay' 按钮已找到，正在点击...")
        pay_button.click()
        log("✅ 'Pay' 按钮已点击。")
        
        # 等待一小段时间，确保支付请求已发出
        time.sleep(5)
        log("续费流程似乎已成功触发。请登录网站确认续费状态。")
        page.screenshot(path="renew_success.png")
        return True

    except PlaywrightTimeoutError as e:
        log(f"❌ 续费任务超时: 未在规定时间内找到元素。请检查选择器或页面是否已更改。错误: {e}")
        page.screenshot(path="renew_timeout_error.png")
        return False
    except Exception as e:
        log(f"❌ 续费任务执行过程中发生未知错误: {e}")
        page.screenshot(path="renew_general_error.png")
        return False

def main():
    """主函数，编排整个自动化流程"""
    if not HIDENCLOUD_COOKIE and not (HIDENCLOUD_EMAIL and HIDENCLOUD_PASSWORD):
        log("❌ 致命错误: 必须提供 HIDENCLOUD_COOKIE 或 (HIDENCLOUD_EMAIL 和 HIDENCLOUD_PASSWORD) 环境变量。")
        sys.exit(1)

    with sync_playwright() as p:
        log("启动浏览器...")
        browser = p.chromium.launch(headless=True) # 在 GitHub Actions 中必须使用 headless 模式
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        log("浏览器启动成功。")

        try:
            # 步骤 1: 登录
            if not login(page):
                log("登录失败，程序终止。")
                sys.exit(1) # 登录失败则退出

            # 步骤 2: 执行续费
            if not renew_service(page):
                log("续费失败，程序终止。")
                sys.exit(1) # 续费失败则退出
            
            log("🎉🎉🎉 自动化续费任务成功完成！ 🎉🎉🎉")

        except Exception as e:
            log(f"💥 主程序发生严重错误: {e}")
            page.screenshot(path="main_critical_error.png")
            sys.exit(1)
        finally:
            log("关闭浏览器。")
            browser.close()

if __name__ == "__main__":
    main()
