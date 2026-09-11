#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 启动并注入 Clannad 主题（带日志 + 端口自动重读）"""
import os
import sys
import time
import json
import urllib.request

ROOT = r'C:\Users\HP\.workbuddy'
PYTHON = os.path.join(ROOT, 'binaries', 'python', 'versions', '3.13.12', 'python.exe')
CDP_SCRIPT = os.path.join(ROOT, 'wb-cdp.py')
THEME_FILE = os.path.join(ROOT, 'skills', 'clannad-theme-v10', 'clannad-theme-console.js')
PORT_FILE = os.path.join(ROOT, 'app', 'session', 'DevToolsActivePort')
WB_EXE = r'C:\Users\HP\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe'
LOG_FILE = os.path.join(ROOT, 'scripts', 'inject.log')

# 把 print 重定向到日志文件：pythonw 运行环境无控制台，直接 print 会抛
# AttributeError('NoneType' has no attribute 'write') 导致脚本崩溃。
try:
    _logf = open(LOG_FILE, 'a', encoding='utf-8')
    sys.stdout = _logf
    sys.stderr = _logf
except Exception:
    pass


def log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def get_cdp_port():
    """从 DevToolsActivePort 文件读取 CDP 端口（每次重新读，避免读到残留旧端口）"""
    try:
        if not os.path.exists(PORT_FILE):
            return None
        with open(PORT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    return int(line)
    except Exception as e:
        log(f'读取端口文件失败: {e}')
    return None


def check_wb_running(port):
    """检查指定端口的 CDP 是否有 WorkBuddy 页面"""
    if not port:
        return False
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json', timeout=1) as r:
            targets = json.load(r)
            for t in targets:
                if t.get('type') == 'page' and 'WorkBuddy' in t.get('title', ''):
                    return True
    except Exception:
        pass
    return False


def wait_for_wb(timeout=45):
    """等待 WorkBuddy 启动：每轮重新读取端口文件并用新端口探测"""
    log('等待 WorkBuddy CDP 就绪(每轮重读端口)...')
    for i in range(timeout):
        port = get_cdp_port()
        if port and check_wb_running(port):
            log(f'CDP 就绪，端口={port}（第 {i+1}s）')
            return port
        time.sleep(1)
    return None


def read_host_state(wb_cdp, t):
    """读主窗口当前主题 key 与激活状态，供内嵌 iframe 跟随（保持观感一致）"""
    try:
        ws, _ = wb_cdp.connect(t['id'])
        try:
            v = wb_cdp.evaluate(ws, """
(function(){
    var k = 'fuko';
    try { var st = JSON.parse(localStorage.getItem('wbx-theme-state') || '{}'); if (st.theme) k = st.theme; } catch(e) {}
    return JSON.stringify({ theme: k, active: document.body.classList.contains('wbx-active') });
})()""")
            d = json.loads(v) if isinstance(v, str) else {}
            return d.get('theme', 'fuko'), bool(d.get('active'))
        finally:
            ws.close()
    except Exception as e:
        log(f'读取主窗口主题状态失败: {e}')
    return 'fuko', True


def load_wb_cdp(port):
    os.environ['CDP_PORT'] = str(port)
    sys.path.insert(0, ROOT)
    import importlib.util
    spec = importlib.util.spec_from_file_location('wb_cdp', CDP_SCRIPT)
    wb_cdp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wb_cdp)
    return wb_cdp


def inject_target(wb_cdp, t, tag, theme_key='fuko', host_active=True):
    title = (t.get('title') or '')[:30]
    url = (t.get('url') or '')
    embed = t.get('type') == 'iframe'
    try:
        ws, target = wb_cdp.connect(t['id'])
    except Exception as e:
        log(f'[{"iframe" if embed else "page"}][{title}] 连接失败: {e}')
        return 'fail'
    try:
        ws.call('Runtime.enable')
        # 幂等：已注入且玻璃层仍在则跳过（页面导航后 glass 会消失，需重注）
        already = wb_cdp.evaluate(
            ws, f'!!(window.__WBX_INJECTED__ === {json.dumps(tag)} && document.getElementById("wbx-glass"))')
        if already:
            return 'skip'

        if embed:
            if not host_active:
                # 主窗口已还原默认主题 → iframe 同步还原，避免主窗无皮肤而内嵌页还有皮肤
                r = wb_cdp.evaluate(ws, "(function(){"
                                        "if(window.__WBX_RESTORED__) return 'skip';"
                                        "if(window.__wbxRestore){window.__wbxRestore();}"
                                        "window.__WBX_RESTORED__ = true; return 'restored';})()")
                log(f'[iframe][{title}] 主窗已还原，同步还原: {r}')
                return 'skip'
            # 远程网页 iframe（workbuddy.cn）：主文档 CSS 无法穿透，必须单独注入。
            # 置位嵌入标志（跳过切换器/粒子）并传入主窗口当前主题 key，保持一致观感
            wb_cdp.evaluate(
                ws, 'window.__WBX_EMBED__ = true; window.__WBX_RESTORED__ = false;'
                    ' window.__WBX_EMBED_THEME__ = %s;' % json.dumps(theme_key))
        else:
            # 清除主题禁用标记（用户若曾“恢复默认设置”，localStorage 会禁用主题）
            wb_cdp.evaluate(ws, """
(function(){
    try {
        var st = JSON.parse(localStorage.getItem('wbx-theme-state') || '{}');
        st.active = true;
        localStorage.setItem('wbx-theme-state', JSON.stringify(st));
        return 'cleared';
    } catch(e) { return 'error'; }
})()
""")

        with open(THEME_FILE, 'r', encoding='utf-8') as f:
            code = f.read()

        pre = 'window.__WBX_EMBED__ = true;' if embed else ''
        wrapped = ('(function(){' + pre + 'try{\n' + code +
                   '\n;window.__WBX_INJECTED__=' + json.dumps(tag) +
                   ';return "OK_INJECTED";}catch(e){return "THROW: "+(e && e.message ? e.message : String(e))}})()')
        result = wb_cdp.evaluate(ws, wrapped)
        log(f'[{"iframe" if embed else "page"}][{title}] 注入={result} url={url[:70]}')
        if isinstance(result, str) and result.startswith('OK'):
            return 'ok'
        return 'fail'
    except Exception as e:
        log(f'[{"iframe" if embed else "page"}][{title}] 注入异常: {e}')
        return 'fail'
    finally:
        try:
            ws.close()
        except Exception:
            pass


def inject_theme(port, watch_seconds=10800):
    """注入主题到主窗口 + 所有远程网页 iframe，并守护扫描新出现的 target。
    资料库/专家/技能/连接器/自动化/更多等页面都是懒创建的 iframe：用户点到才创建，
    单次注入必然漏掉，必须长时守护补注；否则这些页面永远是原生白底。
    守护空闲后自动降频（20s 一次轻量 HTTP 探测），开销可忽略。"""
    log(f'开始注入，端口={port}')
    try:
        wb_cdp = load_wb_cdp(port)
        tag = str(int(os.path.getmtime(THEME_FILE)))
        log(f'主题版本标记: {tag}')

        ok_count = 0

        def sweep():
            nonlocal ok_count
            try:
                ts = wb_cdp.list_targets()
            except Exception as e:
                log(f'扫描 target 失败: {e}')
                return False
            injected_any = False
            # 顺序要紧：先注入主窗口并读出其主题状态，再据此注入内嵌 iframe
            theme_key, host_active = 'fuko', True
            for t in ts:
                if t.get('type') != 'page':
                    continue
                if inject_target(wb_cdp, t, tag, theme_key, True) == 'ok':
                    ok_count += 1
                    injected_any = True
                theme_key, host_active = read_host_state(wb_cdp, t)
            for t in ts:
                if t.get('type') != 'iframe':
                    continue
                if inject_target(wb_cdp, t, tag, theme_key, host_active) == 'ok':
                    ok_count += 1
                    injected_any = True
            return injected_any

        sweep()

        log(f'进入守护扫描（最长 {watch_seconds}s，空闲后降频至 20s）...')
        deadline = time.time() + watch_seconds
        fast_until = time.time() + 90      # 启动后 90s 内高频扫描，覆盖连续切页操作
        while time.time() < deadline:
            time.sleep(4 if time.time() < fast_until else 20)
            if not check_wb_running(get_cdp_port()):
                log('WorkBuddy 已退出，守护结束')
                break
            try:
                if sweep():
                    fast_until = time.time() + 90   # 有新页面注入成功，回到高频档
            except Exception as e:
                log(f'守护扫描异常: {e}')
        log(f'守护结束，累计成功注入 {ok_count} 次')
        return ok_count > 0
    except Exception as e:
        log(f'注入异常: {e}')
        import traceback
        traceback.print_exc()
    return False


def main():
    log('=' * 40)
    log('WorkBuddy 启动并注入 Clannad 主题')
    log('=' * 40)

    port = get_cdp_port()
    log(f'初始端口: {port}')

    if port and check_wb_running(port):
        log('WorkBuddy 已在运行，直接注入')
    else:
        log('WorkBuddy 未运行，启动中...')
        try:
            os.startfile(WB_EXE)
        except Exception as e:
            log(f'启动 WorkBuddy 失败: {e}')
            return 1
        port = wait_for_wb()
        if not port:
            log('错误: 等待 WorkBuddy 启动超时（端口可能已变更）')
            return 1
        log(f'WorkBuddy 已启动，端口={port}')

    watch = int(os.environ.get('WB_GUARD_SECONDS', '10800'))
    ok = inject_theme(port, watch)
    if ok:
        log('✅ 主题已注入! 请查看 WorkBuddy 是否显示皮肤（必要时刷新页面）')
    else:
        log('❌ 主题注入失败，请检查 inject.log 与上方面板输出')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f'未捕获异常: {e}')
        sys.exit(1)
