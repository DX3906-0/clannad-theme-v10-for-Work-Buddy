# -*- coding: utf-8 -*-
r"""
WorkBuddy Clannad 皮肤自愈守护进程 (stdlib only, 完全独立于 WorkBuddy 运行)

职责:
  - 每 6 秒轮询 DevToolsActivePort (随机端口, 由 WORKBUDDY_REMOTE_DEBUGGING_PORT=0 产生)
  - 一旦发现 CDP 可用, 检查每个 page/iframe 是否已注入皮肤
  - 若皮肤缺失(刚重启/被清理), 自动重新注入 clannad-theme-console.js
  - 因此 WorkBuddy 无论怎么重启, 皮肤都会自己回来

日志: C:\Users\HP\.workbuddy\skin-watchdog.log
"""
import os
import sys
import time
import socket
import subprocess

ROOT = r"C:\Users\HP\.workbuddy"
SKILL_DIR = os.path.join(ROOT, "skills", "clannad-theme-v10")
SKIN = os.path.join(SKILL_DIR, "clannad-theme-console.js")

# 注入前的硬清理：按 id(wbx-theme-style) + data-wbx 属性 + 内容签名(wbx-ambient/#wbx-switcher) 移除所有皮肤残留，
# 避免历史多层样式叠加（经验证：IIFE 内部清理在 Runtime.evaluate 上下文下偶尔漏删旧样式，预清理可彻底解决）
CLEANUP_JS = (
    "(function(){try{"
    "Array.prototype.slice.call(document.querySelectorAll('style')).forEach(function(s){"
    "var t=s.textContent||'';"
    "if(s.id==='wbx-theme-style'||s.id==='wbx-blurwall-style'||s.hasAttribute('data-wbx')"
    "||t.indexOf('wbx-ambient')>=0||t.indexOf('#wbx-switcher')>=0||t.indexOf('#wbx-glass')>=0){s.remove();}"
    "});"
    "var els=document.querySelectorAll('#wbx-switcher,#wbx-ambient,#wbx-glass,#wbx-fx,#wbx-motifs,#wbx-bg,.wbx-bg-layer');"
    "for(var i=0;i<els.length;i++){els[i].remove();}"
    "try{window.__WBX_THEME__=undefined;}catch(e){}"
    "}catch(e){}return 'cleaned';})()"
)
PORT_FILE = os.path.join(ROOT, "app", "session", "DevToolsActivePort")
LOG = os.path.join(ROOT, "skin-watchdog.log")
# 轮询节奏: 主题已就位时用 IDLE_SLEEP(低开销); 需要关注(端口变化/皮肤缺失/文件更新)时用 FAST_SLEEP
IDLE_SLEEP = 15
FAST_SLEEP = 3
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

sys.path.insert(0, ROOT)
import importlib.util

_spec = importlib.util.spec_from_file_location("wb_cdp", os.path.join(ROOT, "wb-cdp.py"))
wb_cdp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wb_cdp)  # 复用零依赖 CDP 客户端 (connect / evaluate / WS)

_last_skin_mtime = 0
_skin_cache = None
_last_port = None
_skip_logged = set()
last_injected_mtime = 0


def log(*a):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s" % (ts, " ".join(str(x) for x in a))
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def read_port():
    try:
        with open(PORT_FILE, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(200)
        for ln in data.splitlines():
            ln = ln.strip()
            if ln.isdigit():
                return int(ln)
    except Exception:
        return None
    return None


def load_skin():
    global _last_skin_mtime, _skin_cache
    try:
        mtime = os.path.getmtime(SKIN)
    except Exception:
        mtime = 0
    if _skin_cache is None or mtime != _last_skin_mtime:
        with open(SKIN, "r", encoding="utf-8", errors="replace") as f:
            _skin_cache = f.read()
        _last_skin_mtime = mtime
    return _skin_cache


def cycle():
    """返回 True 表示一切就位(可低频轮询), False 表示需要快速关注。"""
    global last_injected_mtime, _last_port
    port = read_port()
    if port is None:
        return False
    if port != _last_port:
        if _last_port is not None:
            log("WB restarted? port %s -> %s" % (_last_port, port))
        _last_port = port
    wb_cdp.HOST = "127.0.0.1"
    wb_cdp.PORT = port
    # 探测 CDP 是否真的可用
    try:
        wb_cdp.http_json("/json/version")
    except Exception:
        return False  # 端口还没起来(刚重启/僵尸), 下一轮再试
    try:
        targets = wb_cdp.list_targets()
    except Exception as e:
        log("list_targets fail:", str(e)[:80])
        return False
    skin_mtime = 0
    try:
        skin_mtime = os.path.getmtime(SKIN)
    except Exception:
        pass
    idle = True
    for t in targets:
        typ = t.get("type")
        # 只处理顶层 page。iframe/webview 不注入：皮肤在 iframe 内命中环境守卫，
        # 只会执行清理后退出（要嵌需显式 __WBX_EMBED__），因此 present 永远为 false，
        # 会造成「每轮都判定缺失 → 反复注入 → iframe 内容被反复清理」的空转。
        if typ != "page":
            continue
        if "devtools" in t.get("url", ""):
            continue
        tid = t["id"]
        ws = None
        try:
            ws = wb_cdp.WS(t["webSocketDebuggerUrl"])
            ws.call("Runtime.enable")
            present = wb_cdp.evaluate(
                ws,
                "!!(window.__WBX_THEME__ && document.getElementById('wbx-ambient') "
                "&& document.body.style.getPropertyValue('--wbx-art'))",
            )
            # 仅当元素缺失「或」皮肤文件已更新(mtime 变化)时才重注；
            # 否则元素存在即认为已注入，跳过（避免无谓重注/叠加）
            # 用户主动还原（localStorage wbx-theme-state.active===false）时不自愈重注，保持原主题；
            # 无论皮肤当前是否还在，都先尊重该标记（放在最前，覆盖 present 分支）
            try:
                disabled = wb_cdp.evaluate(
                    ws,
                    "(function(){try{var s=JSON.parse(localStorage.getItem('wbx-theme-state')||'{}');"
                    "return s.active===false;}catch(e){return false;}})()",
                )
            except Exception:
                disabled = False
            if disabled:
                # 用户主动还原主题：尊重该状态；仅在首次发现时记一条日志，避免日志膨胀
                if tid not in _skip_logged:
                    _skip_logged.add(tid)
                    log("SKIP inject (user restored default) ->", tid[:14])
                continue
            if present and skin_mtime == last_injected_mtime:
                continue
            idle = False
            code = load_skin()
            try:
                wb_cdp.evaluate(ws, CLEANUP_JS)
            except Exception:
                pass
            wb_cdp.evaluate(ws, code)
            last_injected_mtime = skin_mtime
            log("INJECTED ->", tid[:14], "|", str(t.get("url", ""))[:55],
                "(reason: %s)" % ("missing" if not present else "skin-updated"))
        except Exception as e:
            log("inject fail ->", tid[:14], str(e)[:90])
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
    return idle


def main():
    # 单例锁：防止「开机自启」与「手动双击启动器」叠加出多个守护进程同时注入
    # （多实例并发注入会互相清理、造成界面闪烁）。用本地端口占用做互斥，
    # 进程退出时操作系统自动释放，无需清理残留状态。
    global _SINGLETON
    try:
        _SINGLETON = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _SINGLETON.bind(("127.0.0.1", 47311))
        _SINGLETON.listen(1)
    except OSError:
        print("another watchdog instance is already running; exit")
        return
    if "--detach" in sys.argv:
        # 以分离方式重启自身, 使其不依赖父 shell / WorkBuddy 会话
        # 关键: CREATE_BREAKAWAY_FROM_JOB —— 否则父进程(Bash/沙箱)退出时
        # 会把本进程当作 job 子进程一起杀掉(此前 watchdog 只能活 1 分钟的根因)。
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [sys.executable, "-X", "utf8", __file__]
        base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        for flags in (base | CREATE_BREAKAWAY_FROM_JOB, base):
            try:
                subprocess.Popen(
                    cmd,
                    cwd=ROOT,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    close_fds=True,
                )
                print("watchdog detached (flags=0x%x); log=%s" % (flags, LOG))
                return
            except OSError as exc:
                print("detach attempt failed (0x%x): %s" % (flags, exc))
        print("watchdog detach FAILED")
        return
    if "--once" in sys.argv:
        log("single-shot cycle")
        cycle()
        return
    log("=== skin watchdog started (pid %d) ===" % os.getpid())
    log("skin file: %s" % SKIN)
    log("port file: %s" % PORT_FILE)
    try:
        with open(os.path.join(ROOT, "skin-watchdog.pid"), "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    while True:
        idle = False
        try:
            idle = cycle()
        except Exception as e:
            log("cycle ERR:", str(e)[:120])
        time.sleep(IDLE_SLEEP if idle else FAST_SLEEP)


if __name__ == "__main__":
    main()
