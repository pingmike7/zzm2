#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, time, platform, requests, re, signal
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from seleniumbase import SB

AUTH_URL = "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl"
DASHBOARD_URL = "https://dash.zampto.net/homepage"
OVERVIEW_URL = "https://dash.zampto.net/overview"
SERVER_URL = "https://dash.zampto.net/server?id={}"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CN_TZ = timezone(timedelta(hours=8))

class ClickTimeout(Exception):
    pass

def _timeout_handler(signum, frame):
    raise ClickTimeout()

def cn_now() -> datetime:
    return datetime.now(CN_TZ)

def calc_expiry_time(renewal_time_str: str, minutes: int = 2880) -> str:
    if not renewal_time_str:
        return "未知"
    try:
        dt = datetime.strptime(renewal_time_str, "%b %d, %Y %I:%M %p")
        expiry = dt.replace(tzinfo=timezone.utc) + timedelta(minutes=minutes)
        return expiry.astimezone(CN_TZ).strftime("%Y年%m月%d日 %H时%M分")
    except:
        return "未知"

def parse_renewal_datetime(time_str: str) -> Optional[datetime]:
    if not time_str:
        return None
    try:
        return datetime.strptime(time_str.strip(), "%b %d, %Y %I:%M %p")
    except:
        return None

def mask(s: str, show: int = 1) -> str:
    if not s: return "***"
    return s[:show] + "***" if len(s) > show else s[0] + "***"

def mask_id(sid: str) -> str:
    return str(sid)[0] + "***" if sid else "****"

def safe_sid_for_filename(sid: str) -> str:
    s = str(sid)
    if len(s) <= 3:
        return s
    return f"{s[0]}x{s[-2:]}"

def is_linux():
    return platform.system().lower() == "linux"

def setup_display():
    if is_linux() and not os.environ.get("DISPLAY"):
        try:
            from pyvirtualdisplay import Display
            d = Display(visible=False, size=(1920, 1080))
            d.start()
            os.environ["DISPLAY"] = d.new_display_var
            print("[INFO] 虚拟显示已启动")
            return d
        except Exception as e:
            print(f"[ERROR] 虚拟显示失败: {e}")
            sys.exit(1)
    return None

def shot(idx: int, name: str) -> str:
    return str(OUTPUT_DIR / f"acc{idx}-{cn_now().strftime('%H%M%S')}-{name}.png")

def safe_screenshot(sb, path: str):
    try:
        sb.save_screenshot(path)
        print(f"  📸 截图 → {Path(path).name}")
    except Exception as e:
        print(f"  [WARN] 截图失败: {e}")

def notify(ok: bool, username: str, server_id: str, expiry_info: str, img: str = None):
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not token or not chat: return
    try:
        status = "✅ 续期成功" if ok else "❌ 续期失败"
        text = f"{status}\n\n账号：{username}\n服务器: {server_id}\n到期: {expiry_info}\n\nZampto Auto Renew"
        if img and Path(img).exists():
            with open(img, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat, "caption": text}, files={"photo": f}, timeout=60)
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text}, timeout=30)
        print("  ✅ TG推送成功")
    except Exception as e:
        print(f"  [WARN] TG推送失败: {e}")

def notify_login_fail(username: str, img: str = None):
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not token or not chat: return
    try:
        text = f"❌ 登录失败\n\n账号：{username}\n\nZampto Auto Renew"
        if img and Path(img).exists():
            with open(img, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat, "caption": text}, files={"photo": f}, timeout=60)
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text}, timeout=30)
    except: pass

def parse_accounts(s: str) -> List[Tuple[str, str]]:
    return [(p[0].strip(), p[1].strip()) for line in s.strip().split('\n')
            if '----' in line and len(p := line.strip().split('----', 1)) == 2 and p[0].strip() and p[1].strip()]

def inject_ad_guard(sb):
    try:
        sb.execute_script('''
        (function() {
            if (window._adGuardActive) return;
            window._adGuardActive = true;

            const adSelectors = [
                'ins.adsbygoogle', 'iframe[id^="aswift"]', '#google_ads_iframe',
                'div[id^="google_ads_lib"]', 'iframe[src*="googleads"]',
                '.ad-container', '.ads-wrapper', 'div[class*="ad-box"]',
                'div[id^="ad-"]', '#bottom-anchor-container',
                'div[class*="fixed-bottom"]', '.fc-ab-root', '.ad-placement'
            ];

            const clean = () => {
                adSelectors.forEach(s => {
                    document.querySelectorAll(s).forEach(el => el.remove());
                });
                document.querySelectorAll(
                    '.modal-backdrop, div[class*="backdrop"]'
                ).forEach(el => {
                    if (el.querySelector('#turnstileContainer') ||
                        el.querySelector('#renewForm') ||
                        el.querySelector('iframe[src*="challenges.cloudflare.com"]') ||
                        (el.innerText && el.innerText.includes('Renew Server'))) {
                        return;
                    }
                    el.remove();
                });
                const modal = document.getElementById('renewModal');
                const modalVisible = modal &&
                    window.getComputedStyle(modal).display !== 'none';
                if (!modalVisible && document.body.style.overflow === 'hidden') {
                    document.body.style.setProperty('overflow', 'auto', 'important');
                }
            };

            clean();
            window._adGuardObserver = new MutationObserver(clean);
            window._adGuardObserver.observe(document.documentElement, {
                childList: true, subtree: true
            });
        })();
        ''')
    except: pass

def dismiss_cookie_only(sb) -> bool:
    try:
        result = sb.execute_script('''
            (function() {
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    var text = buttons[i].textContent.trim();
                    if (text === 'Consent' || text === 'Accept' || text === 'Accept All' ||
                        text === 'Do not consent' || text === 'Reject') {
                        buttons[i].click();
                        return text;
                    }
                }
                return '';
            })()
        ''')
        if result:
            print(f"  [INFO] 已关闭Cookie弹窗 ({result})")
            time.sleep(1)
            return True
    except: pass
    return False

def check_renew_modal_open(sb) -> bool:
    try:
        return bool(sb.execute_script('''
            (function() {
                var modal = document.getElementById('renewModal');
                if (modal) {
                    var style = window.getComputedStyle(modal);
                    if (style.display !== 'none' && style.visibility !== 'hidden') return true;
                }
                var iframes = document.querySelectorAll(
                    'iframe[src*="turnstile"], iframe[src*="challenges.cloudflare"]'
                );
                if (iframes.length > 0) return true;
                var cf = document.querySelector('.cf-turnstile, #turnstileContainer');
                if (cf && cf.offsetWidth > 0) return true;
                return false;
            })()
        '''))
    except:
        return False

def check_turnstile_done(sb) -> bool:
    try:
        return bool(sb.execute_script('''
            var cf = document.querySelector("input[name='cf-turnstile-response']");
            return cf && cf.value && cf.value.length > 20;
        '''))
    except:
        return False

def uc_click_with_timeout(sb, timeout: int = 20) -> bool:
    if not is_linux():
        try:
            sb.uc_gui_click_captcha()
            return True
        except:
            return False

    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout)
    try:
        sb.uc_gui_click_captcha()
        signal.alarm(0)
        print(f"  ✅ 坐标点击成功")
        return True
    except ClickTimeout:
        print(f"  [WARN] 点击超时 ({timeout}s)")
        return False
    except Exception as e:
        print(f"  [WARN] 点击异常: {e}")
        return False
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

def handle_turnstile(sb, idx: int, sid_f: str) -> bool:
    print("  ⏳ 等待 Turnstile...")
    time.sleep(2)

    dismiss_cookie_only(sb)
    safe_screenshot(sb, shot(idx, f"server_{sid_f}_after_click"))

    modal_open = check_renew_modal_open(sb)
    print(f"  [INFO] 续期弹窗: {'已打开' if modal_open else '未检测到'}")

    if check_turnstile_done(sb):
        print("  ✅ Turnstile 已完成")
        return True

    print("  🔄 处理 Turnstile 验证...")
    for attempt in range(3):
        print(f"  🖱️ 坐标计算完成 (第{attempt+1}次)")
        clicked = uc_click_with_timeout(sb, timeout=20)
        time.sleep(3)

        if check_turnstile_done(sb):
            print(f"  ✅ Turnstile 通过 (第{attempt+1}次)")
            return True

        if not check_renew_modal_open(sb):
            print(f"  [INFO] 弹窗已关闭，续期已提交")
            return True

        if not clicked:
            time.sleep(5)

    print("  ⏳ 等待续期结果...")
    start = time.time()
    while time.time() - start < 30:
        if check_turnstile_done(sb):
            print(f"  ✅ 检测到续期结果！")
            return True
        if not check_renew_modal_open(sb):
            print(f"  [INFO] 弹窗已关闭")
            return True
        time.sleep(2)

    print("  [WARN] Turnstile 超时")
    return False

def precheck_cf_turnstile(sb, idx: int) -> bool:
    print(f"\n{'─'*40}")
    print("  🛡️ 预处理 Cloudflare 验证 (首页盾)")
    print(f"{'─'*40}")

    try:
        sb.uc_open_with_reconnect("https://zampto.net", reconnect_time=10)
        time.sleep(5)

        safe_screenshot(sb, shot(idx, "cf_homepage"))

        # 检测是否进入 CF 验证页
        is_cf_page = sb.execute_script('''
            var body = document.body ? document.body.innerText : '';
            if (body.includes('正在进行安全验证') ||
                body.includes('Verify you are human') ||
                body.includes('security check')) {
                return true;
            }

            var cf = document.querySelector("input[name='cf-turnstile-response']");
            return !!cf;
        ''')

        if not is_cf_page:
            print("  ✅ 未检测到 CF 验证")
            return True

        print("  ⚠️ 检测到 CF 验证，开始处理...")

        for attempt in range(5):
            print(f"  🖱️ 点击验证 (第{attempt+1}次)...")

            clicked = uc_click_with_timeout(sb, timeout=25)
            time.sleep(4)

            # 判断是否通过
            passed = sb.execute_script('''
                var cf = document.querySelector("input[name='cf-turnstile-response']");
                if (cf && cf.value && cf.value.length > 20) return true;

                var body = document.body ? document.body.innerText : '';
                if (body.includes('验证成功') ||
                    body.includes('success') ||
                    body.includes('正在等待 zampto.net 响应')) {
                    return true;
                }
                return false;
            ''')

            if passed:
                print(f"  ✅ CF 验证通过 (第{attempt+1}次)")
                time.sleep(3)
                return True

            if not clicked:
                time.sleep(5)

        print("  [WARN] CF 验证未通过")
        return False

    except Exception as e:
        print(f"  [WARN] CF 预处理异常: {e}")
        return False

def scroll_and_get_renewal_info(sb) -> Tuple[str, str]:
    try:
        sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
    except: pass

    renewal_time, remain_time = "", ""
    try:
        renewal_time = sb.execute_script('''
            var el = document.getElementById("lastRenewalTime");
            return el ? el.textContent.trim() : "";
        ''') or ""
        remain_time = sb.execute_script('''
            var el = document.getElementById("nextRenewalTime");
            return el ? el.textContent.trim() : "";
        ''') or ""
    except: pass

    return renewal_time, remain_time

def login(sb, user: str, pwd: str, idx: int) -> Tuple[bool, Optional[str]]:
    print(f"\n{'─'*40}")
    print(f"  🔐 验证出口 IP...")
    try:
        proxy = os.environ.get("PROXY_SOCKS5", "")
        proxies = {"http": proxy, "https": proxy} if proxy else None
        ip_info = requests.get(
            "https://api.ipify.org?format=json",
            proxies=proxies,
            timeout=10
        ).json()
        print(f"  ✅ 出口IP确认: {ip_info}")
    except Exception as e:
        print(f"  [WARN] IP检测失败: {e}")

    print(f"\n{'─'*40}")
    print(f"  🌐 访问登录页...")
    last_shot = None

    for attempt in range(3):
        try:
            sb.uc_open_with_reconnect(AUTH_URL, reconnect_time=10)
            time.sleep(5)

            if "dash.zampto.net" in sb.get_current_url():
                print("  ✅ 登录成功!")
                return True, None

            last_shot = shot(idx, f"login-{attempt}")
            safe_screenshot(sb, last_shot)

            print("  ✏️ 填写账号密码...")
            for _ in range(10):
                if "identifier" in sb.get_page_source(): break
                time.sleep(2)

            typed_user = False
            for sel in ['input[name="identifier"]', 'input[type="email"]', 'input[type="text"]']:
                try:
                    sb.wait_for_element(sel, timeout=5)
                    sb.type(sel, user)
                    typed_user = True
                    break
                except: continue

            if not typed_user:
                if attempt < 2: time.sleep(5); continue
                return False, last_shot

            time.sleep(1)
            try: sb.click('button[type="submit"]')
            except: sb.click("button")

            print("  ⏳ 等待密码页面...")
            for _ in range(15):
                try:
                    if sb.is_element_visible('input[name="password"]') or sb.is_element_visible('input[type="password"]'):
                        break
                except: pass
                time.sleep(1)

            time.sleep(2)

            typed_pwd = False
            for _ in range(15):
                for sel in ['input[name="password"]', 'input[type="password"]']:
                    try:
                        if sb.is_element_visible(sel):
                            sb.type(sel, pwd)
                            typed_pwd = True
                            break
                    except: continue
                if typed_pwd: break
                time.sleep(1)

            if not typed_pwd:
                print("  [WARN] 未能填写密码")
                if attempt < 2: time.sleep(5); continue
                return False, last_shot

            time.sleep(1)

            # 检测密码页面是否已有 Turnstile（页面加载时就存在）
            has_turnstile_before = sb.execute_script('''
                var frames = document.querySelectorAll('iframe');
                for (var i = 0; i < frames.length; i++) {
                    var src = frames[i].src || '';
                    if (src.indexOf('challenges.cloudflare') !== -1 ||
                        src.indexOf('turnstile') !== -1) {
                        return true;
                    }
                }
                return !!(document.querySelector('.cf-turnstile') ||
                          document.querySelector('[data-sitekey]') ||
                          document.querySelector('.jeFng_captchaBox'));
            ''')
            print(f"  [INFO] 密码页面 Turnstile 预检: {'存在' if has_turnstile_before else '未检测到'}")

            # 点击继续触发 Turnstile（如果还没出现）或提交
            print("  🖱️ 点击继续...")
            try: sb.click('button[type="submit"]')
            except:
                try: sb.click("button")
                except: pass

            # 等待 Turnstile 出现（点击前已有或点击后出现）
            print("  ⏳ 等待 Turnstile 加载...")
            turnstile_appeared = False
            for _ in range(20):
                if "dash.zampto.net" in sb.get_current_url():
                    print("  ✅ 登录成功!")
                    return True, None

                has_turnstile = sb.execute_script('''
                    // 检测 iframe
                    var frames = document.querySelectorAll('iframe');
                    for (var i = 0; i < frames.length; i++) {
                        var src = frames[i].src || '';
                        if (src.indexOf('challenges.cloudflare') !== -1 ||
                            src.indexOf('turnstile') !== -1) {
                            return true;
                        }
                    }
                    // 检测容器
                    if (document.querySelector('.cf-turnstile') ||
                        document.querySelector('[data-sitekey]') ||
                        document.querySelector('.jeFng_captchaBox')) {
                        return true;
                    }
                    // 检测页面文字
                    var body = document.body ? document.body.innerText : '';
                    if (body.indexOf('Verify you are human') !== -1 ||
                        body.indexOf('确认您是真人') !== -1) {
                        return true;
                    }
                    return false;
                ''')
                if has_turnstile:
                    turnstile_appeared = True
                    print("  ✅ Turnstile 已检测到")
                    break
                time.sleep(1)

            if turnstile_appeared:
                print("  🔄 处理登录页 Turnstile 验证...")
                time.sleep(3)

                # 先检查是否已经自动通过
                already_done = sb.execute_script('''
                    var cf = document.querySelector("input[name='cf-turnstile-response']");
                    return cf && cf.value && cf.value.length > 20;
                ''')
                if already_done:
                    print("  ✅ Turnstile 已自动完成")
                else:
                    for t_attempt in range(4):
                        print(f"  🖱️ 点击 Turnstile (第{t_attempt+1}次)...")
                        clicked = uc_click_with_timeout(sb, timeout=25)
                        time.sleep(4)

                        if "dash.zampto.net" in sb.get_current_url():
                            print("  ✅ 登录成功!")
                            return True, None

                        done = sb.execute_script('''
                            var cf = document.querySelector("input[name='cf-turnstile-response']");
                            if (cf && cf.value && cf.value.length > 20) return true;
                            var body = document.body ? document.body.innerText : '';
                            if (body.indexOf('Success') !== -1) return true;
                            return false;
                        ''')
                        if done:
                            print(f"  ✅ Turnstile 通过 (第{t_attempt+1}次)")
                            break
                        if not clicked:
                            time.sleep(5)
                    else:
                        # 最后等待自动完成
                        print("  ⏳ 等待 Turnstile 自动完成 (30s)...")
                        for _ in range(30):
                            if "dash.zampto.net" in sb.get_current_url():
                                print("  ✅ 登录成功!")
                                return True, None
                            done = sb.execute_script('''
                                var cf = document.querySelector("input[name='cf-turnstile-response']");
                                return cf && cf.value && cf.value.length > 20;
                            ''')
                            if done:
                                print("  ✅ Turnstile 已完成")
                                break
                            time.sleep(1)

            print("  ⏳ 等待登录跳转...")
            time.sleep(8)

            last_shot = shot(idx, "login_result")
            safe_screenshot(sb, last_shot)

            if "dash.zampto.net" in sb.get_current_url() or "sign-in" not in sb.get_current_url():
                print("  ✅ 登录成功!")
                return True, last_shot

        except Exception as e:
            print(f"  [WARN] 尝试 {attempt + 1} 异常: {e}")
            if attempt < 2: time.sleep(5)

    return False, last_shot

def logout(sb):
    try:
        sb.delete_all_cookies()
        sb.open("about:blank")
        time.sleep(1)
        print("  [INFO] 已退出登录")
    except: pass

def get_servers(sb, idx: int) -> Tuple[List[Dict[str, str]], str, Optional[str]]:
    servers, seen = [], set()

    sb.open(DASHBOARD_URL)
    time.sleep(5)
    inject_ad_guard(sb)
    dismiss_cookie_only(sb)

    screenshot = shot(idx, "dashboard")
    safe_screenshot(sb, screenshot)

    src = sb.get_page_source()
    if "Access Blocked" in src or "VPN or Proxy" in src:
        return [], "⚠️ 访问被阻止", screenshot

    try:
        api_servers = sb.execute_async_script('''
            var done = arguments[0];
            fetch("https://dash.zampto.net/api/sidebar", {
                method: "GET",
                credentials: "include"
            })
            .then(r => r.json())
            .then(data => {
                var list = (data.serverSelector && data.serverSelector.servers) || [];
                done(list);
            })
            .catch(() => done([]));
        ''')

        if api_servers:
            for srv in api_servers:
                sid = str(srv.get("id", ""))
                name = srv.get("name", sid)
                if sid and sid not in seen:
                    seen.add(sid)
                    servers.append({"id": sid, "name": name})
            print(f"  [INFO] API 返回 {len(servers)} 个活跃服务器")

    except Exception as e:
        print(f"  [WARN] API 获取失败: {e}，回退到页面解析")

    if not servers:
        print("  [INFO] 回退到页面解析...")
        sb.open(OVERVIEW_URL)
        time.sleep(3)
        inject_ad_guard(sb)
        dismiss_cookie_only(sb)
        for sid in re.findall(r"/server\?id=(\d+)", sb.get_page_source()):
            if sid not in seen:
                seen.add(sid)
                servers.append({"id": sid})

    if not servers:
        return [], "⚠️ 未找到服务器", screenshot

    return servers, "", screenshot

def renew(sb, sid: str, idx: int, username: str) -> Dict[str, Any]:
    result = {
        "server_id": sid, "success": False, "message": "", "screenshot": None,
        "old_expiry_cn": "", "new_expiry_cn": "", "expiry_info": "",
    }

    sid_m = mask_id(sid)
    sid_f = safe_sid_for_filename(sid)

    print(f"\n{'─'*40}")
    print(f"  🔄 续期: 🖥️ Zampto (id={sid_m})")
    print(f"\n{'─'*40}")
    print(f"  🌐 访问: https://dash.zampto.net/server?id={sid_m}")

    sb.open(SERVER_URL.format(sid))
    time.sleep(4)
    inject_ad_guard(sb)
    dismiss_cookie_only(sb)

    if "Access Blocked" in sb.get_page_source():
        result["message"] = "访问被阻止"
        result["expiry_info"] = "访问被阻止"
        notify(False, username, sid, result["expiry_info"])
        return result

    safe_screenshot(sb, shot(idx, f"server_{sid_f}_loaded"))

    old_renewal, old_remain = scroll_and_get_renewal_info(sb)
    old_expiry_cn = calc_expiry_time(old_renewal)
    old_dt = parse_renewal_datetime(old_renewal)
    result["old_expiry_cn"] = old_expiry_cn
    print(f"  ⏱️ 当前剩余时间: {old_remain}")

    print("  🔍 查找续期按钮...")
    try:
        clicked = sb.execute_script(f'''
            (function() {{
                var links = document.querySelectorAll('a[onclick*="handleServerRenewal"]');
                for (var i = 0; i < links.length; i++) {{
                    if (links[i].getAttribute('onclick').includes('{sid}')) {{
                        links[i].click();
                        return "handleServerRenewal";
                    }}
                }}
                var btns = document.querySelectorAll('a.action-button, button, a');
                for (var i = 0; i < btns.length; i++) {{
                    var text = btns[i].textContent.trim();
                    if (text.includes('Renew') && !text.includes('Last') && !text.includes('Next')) {{
                        btns[i].click();
                        return "span:" + text;
                    }}
                }}
                return "";
            }})()
        ''')

        if not clicked:
            result["message"] = "未找到续期按钮"
            result["expiry_info"] = f"未找到按钮 | {old_expiry_cn}"
            safe_screenshot(sb, shot(idx, f"server_{sid_f}_nobtn"))
            notify(False, username, sid, result["expiry_info"])
            return result

        print(f"  ✅ 已点击续期按钮 (方式: {clicked})")
    except Exception as e:
        result["message"] = f"点击失败: {e}"
        return result

    time.sleep(3)

    handle_turnstile(sb, idx, sid_f)
    time.sleep(5)

    safe_screenshot(sb, shot(idx, f"server_{sid_f}_result"))
    result["screenshot"] = shot(idx, f"server_{sid_f}_result")

    print("  🔄 刷新页面确认续期时间...")
    sb.open(SERVER_URL.format(sid))
    time.sleep(4)
    inject_ad_guard(sb)
    dismiss_cookie_only(sb)

    new_renewal, new_remain = scroll_and_get_renewal_info(sb)
    new_expiry_cn = calc_expiry_time(new_renewal)
    new_dt = parse_renewal_datetime(new_renewal)
    result["new_expiry_cn"] = new_expiry_cn
    print(f"  ⏱️ 续期后剩余时间: {new_remain}")

    final_shot = shot(idx, f"server_{sid_f}_final")
    safe_screenshot(sb, final_shot)
    result["screenshot"] = final_shot

    today_utc = datetime.utcnow().strftime("%b %d, %Y")
    today_utc2 = datetime.utcnow().strftime("%b %-d, %Y") if not sys.platform.startswith("win") else today_utc

    renewed = False
    if old_dt and new_dt and new_dt > old_dt:
        renewed = True
    elif new_renewal and old_renewal and new_renewal != old_renewal:
        renewed = True
    elif new_renewal:
        is_today = today_utc in new_renewal or today_utc2 in new_renewal
        was_today = old_renewal and (today_utc in old_renewal or today_utc2 in old_renewal)
        if is_today and not was_today:
            renewed = True

    if renewed:
        result["success"] = True
        result["expiry_info"] = f"{old_expiry_cn} -> {new_expiry_cn}"
        result["message"] = "续期成功！"
    else:
        result["success"] = False
        result["expiry_info"] = f"{old_expiry_cn} (未更新)"
        result["message"] = "续期失败：时间未变化" if old_renewal == new_renewal else "续期失败：无法确认"

    notify(result["success"], username, sid, result["expiry_info"], final_shot)
    print(f"  {'✅' if result['success'] else '❌'} {result['message']}")
    return result

def process(sb, user: str, pwd: str, idx: int) -> Dict[str, Any]:
    result = {"username": user, "success": False, "message": "", "servers": []}

    login_ok, login_shot = login(sb, user, pwd, idx)
    if not login_ok:
        result["message"] = "登录失败"
        notify_login_fail(user, login_shot)
        return result

    servers, error, dash_shot = get_servers(sb, idx)
    if error:
        result["message"] = error
        notify_login_fail(user, dash_shot)
        logout(sb)
        return result

    print(f"\n  [INFO] 找到 {len(servers)} 个活跃服务器")
    for s in servers:
        print(f"    - ID: {mask_id(s['id'])}")

    for srv in servers:
        r = renew(sb, srv["id"], idx, user)
        result["servers"].append(r)
        time.sleep(3)

    ok = sum(1 for s in result["servers"] if s.get("success"))
    result["success"] = ok > 0
    result["message"] = f"{ok}/{len(result['servers'])} 成功"

    logout(sb)
    return result

def main():
    acc_str = os.environ.get("ZAMPTO_ACCOUNT", "")
    if not acc_str:
        print("[ERROR] 缺少 ZAMPTO_ACCOUNT"); sys.exit(1)

    accounts = parse_accounts(acc_str)
    if not accounts:
        print("[ERROR] 无有效账号"); sys.exit(1)

    print("=" * 40)
    print("  Zampto Auto Renew")
    print("=" * 40)

    proxy = os.environ.get("PROXY_SOCKS5", "")
    if proxy:
        try:
            proxies = {"http": proxy, "https": proxy}
            ip_info = requests.get(
                "https://api.ipify.org?format=json",
                proxies=proxies,
                timeout=10
            ).json()
            print(f"[INFO] 代理连接正常，出口IP: {ip_info}")
        except Exception as e:
            print(f"[WARN] 代理测试失败: {e}")

    display = setup_display()
    results = []

    try:
        try:
            import nest_asyncio
            nest_asyncio.apply()
            print("[INFO] nest_asyncio 已应用")
        except ImportError:
            pass

        opts = {"uc": True, "test": True, "locale": "en", "headed": not is_linux()}
        if proxy:
            opts["proxy"] = proxy
            print("[INFO] 使用代理")

        with SB(**opts) as sb:
            if not precheck_cf_turnstile(sb, 0):
                print("[WARN] CF 首页验证失败，继续尝试登录...")
            for i, (u, p) in enumerate(accounts, 1):
                r = process(sb, u, p, i)
                results.append(r)

    except Exception as e:
        print(f"[ERROR] 脚本异常: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        if display:
            display.stop()

    ok_acc = sum(1 for r in results if r.get("success"))
    total_srv = sum(len(r.get("servers", [])) for r in results)
    ok_srv = sum(sum(1 for s in r.get("servers", []) if s.get("success")) for r in results)

    print(f"\n{'='*40}")
    print(f"📊 账号: {ok_acc}/{len(results)} | 服务器: {ok_srv}/{total_srv}")
    for r in results:
        print(f"{'✅' if r.get('success') else '❌'} {mask(r['username'])}: {r.get('message', '')}")
        for s in r.get("servers", []):
            print(f"  {'✓' if s.get('success') else '✗'} {mask_id(s['server_id'])}: {s.get('message', '')}")
    print(f"{'='*40}")

    sys.exit(0 if ok_srv > 0 else 1)

if __name__ == "__main__":
    main()