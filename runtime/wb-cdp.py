"""
零依赖 CDP 客户端 (stdlib only) - 用于向 WorkBuddy 注入脚本。
用法:
  python wb-cdp.py probe                      列出 targets 并探测 DOM
  python wb-cdp.py eval <target-id> <expr>    求值表达式
  python wb-cdp.py inject <target-id> <file>  注入 JS 文件
  python wb-cdp.py inject-all <file>          注入到所有 page/iframe
"""
import base64
import json
import os
import socket
import struct
import sys
import urllib.request

HOST = "127.0.0.1"
PORT = int(os.environ.get("CDP_PORT", "9222"))


# ---------------------------------------------------------------- http
def http_json(path):
    url = "http://%s:%d%s" % (HOST, PORT, path)
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def list_targets():
    return http_json("/json/list")


# ---------------------------------------------------------------- websocket
class WS:
    def __init__(self, url):
        assert url.startswith("ws://")
        rest = url[5:]
        hostport, path = rest.split("/", 1)
        path = "/" + path
        host, _, port = hostport.partition(":")
        port = int(port or 80)
        self.sock = socket.create_connection((host, port), timeout=30)
        self.sock.settimeout(60)
        key = base64.b64encode(os.urandom(16)).decode()
        # NOTE: do NOT send an Origin header. Chrome/Edge 111+ reject CDP
        # websocket handshakes that carry an Origin unless it is explicitly
        # allowlisted via --remote-allow-origins, and respond with 403.
        # Omitting Origin (as a non-browser client) is accepted.
        req = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s:%d\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host, port, key)
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("handshake failed: connection closed")
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        status = head.split(b"\r\n")[0].decode(errors="replace")
        if "101" not in status:
            raise RuntimeError("handshake failed: %s" % status)
        self.buf = rest

    # ---- low level recv
    def _recv_exact(self, n):
        out = b""
        while len(out) < n:
            chunk = self.sock.recv(min(65536, n - len(out)))
            if not chunk:
                raise RuntimeError("ws closed mid-frame")
            out += chunk
        return out

    def _read_frame(self):
        b0, b1 = self._recv_exact(2)
        fin = b0 & 0x80
        opcode = b0 & 0x0F
        masked = b1 & 0x80
        ln = b1 & 0x7F
        if ln == 126:
            ln = struct.unpack("!H", self._recv_exact(2))[0]
        elif ln == 127:
            ln = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(ln) if ln else b""
        if mask:
            payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        return fin, opcode, payload

    def recv_msg(self):
        """读一条完整消息（自动合并分片）。返回 (opcode, bytes)"""
        opcode = None
        data = b""
        while True:
            fin, op, payload = self._read_frame()
            if op != 0x0:
                opcode = op
            data += payload
            if fin:
                return opcode, data

    # ---- low level send
    def send_text(self, text):
        data = text.encode("utf-8")
        n = len(data)
        if n < 126:
            hdr = struct.pack("!BB", 0x81, 0x80 | n)
        elif n < 65536:
            hdr = struct.pack("!BBH", 0x81, 0x80 | 126, n)
        else:
            hdr = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
        mask = os.urandom(4)
        masked = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
        self.sock.sendall(hdr + mask + masked)

    # ---- CDP
    def call(self, method, params=None, mid=None):
        self._mid = getattr(self, "_mid", 0) + 1
        mid = mid or self._mid
        self.send_text(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            op, raw = self.recv_msg()
            if op == 0x8:
                return {"error": "closed"}
            try:
                msg = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if msg.get("id") == mid:
                return msg

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def connect(target_id):
    ts = list_targets()
    for t in ts:
        if t["id"] == target_id or t["id"].startswith(target_id.upper()):
            return WS(t["webSocketDebuggerUrl"]), t
    raise SystemExit("target not found: %s" % target_id)


def evaluate(ws, expr, return_by_value=True, await_promise=False):
    r = ws.call("Runtime.evaluate", {
        "expression": expr,
        "returnByValue": return_by_value,
        "awaitPromise": await_promise,
        "userGesture": True,
    })
    if "error" in r:
        return {"__error__": r["error"]}
    res = r.get("result", {})
    if "exceptionDetails" in res:
        ed = res["exceptionDetails"]
        return {"__exception__": ed.get("text"), "detail": ed.get("exception", {}).get("description")}
    return res.get("result", {}).get("value")


# ---------------------------------------------------------------- commands
PROBE_JS = r"""JSON.stringify({
  href: location.href,
  title: document.title,
  bodyClass: document.body ? document.body.className : null,
  bodyChildren: document.body ? document.body.children.length : -1,
  iframes: Array.from(document.querySelectorAll('iframe')).map(function(f){
    return {src: (f.src||'').slice(0,120), w: f.clientWidth, h: f.clientHeight};
  }),
  webviews: document.querySelectorAll('webview').length,
  wbxAlready: !!document.getElementById('wbx-switcher'),
  firstDiv: (function(){
    var d = document.body ? document.body.firstElementChild : null;
    return d ? (d.tagName + '#' + d.id + '.' + String(d.className).slice(0,60)) : null;
  })()
})"""


def cmd_probe():
    ts = list_targets()
    print("targets: %d" % len(ts))
    for t in ts:
        print("\n=== %s [%s] %s" % (t["id"], t["type"], t.get("url", "")[:90]))
        try:
            ws = WS(t["webSocketDebuggerUrl"])
        except Exception as e:
            print("  connect failed: %s" % e)
            continue
        try:
            ws.call("Runtime.enable")
            v = evaluate(ws, PROBE_JS)
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    pass
            for k, val in (v.items() if isinstance(v, dict) else [("raw", v)]):
                print("  %-13s %s" % (k, val))
        except Exception as e:
            print("  eval failed: %s" % e)
        finally:
            ws.close()


def cmd_eval(tid, expr):
    ws, t = connect(tid)
    try:
        ws.call("Runtime.enable")
        print(json.dumps(evaluate(ws, expr), ensure_ascii=False, indent=2)[:4000])
    finally:
        ws.close()


def cmd_evala(tid, expr, limit=20000):
    """eval 的异步版：等待 Promise 完成后再取结果（fetch/await 必备）。"""
    ws, t = connect(tid)
    try:
        ws.call("Runtime.enable")
        v = evaluate(ws, expr, await_promise=True)
        print(json.dumps(v, ensure_ascii=False, indent=2)[:int(limit)])
    finally:
        ws.close()


def cmd_click(tid, selector):
    ws, t = connect(tid)
    try:
        ws.call("Runtime.enable")
        r = evaluate(ws,
            "(function(){var el=document.querySelector(%r);"
            "if(!el) return 'NOT_FOUND';"
            "el.click();"
            "return 'CLICKED ' + el.tagName + (el.id?'#'+el.id:'') "
            "+ (el.getAttribute('data-wbx')?'[data-wbx='+el.getAttribute('data-wbx')+']':'');"
            "})()" % selector)
        print(r)
    finally:
        ws.close()


def cmd_front(tid):
    """把目标页签激活到前台。

    WHY: 页面处于 hidden 状态（窗口被最小化/隐藏，由 VBS `Run(cmd, 0, False)`
    的隐藏窗口模式启动）时，Chromium 不会把 Input domain 派发的鼠标事件
    投递给渲染进程 —— 表现就是 realclick 返回正常但页面毫无反应
    （document.hidden === true, 元素上的 click 监听器计数为 0）。
    先 bringToFront 再派发输入即可。
    """
    ws, t = connect(tid)
    try:
        ws.call("Page.bringToFront")
        vis = evaluate(ws, "JSON.stringify({hidden:document.hidden,vis:document.visibilityState})")
        print("FRONT ok %s" % vis)
    finally:
        ws.close()


def cmd_showwin(tid, x=60, y=40, w=1360, h=940):
    """把调试浏览器窗口从隐藏状态显示到屏幕上。

    WHY: VBS 用 sh.Run(cmd, 0, False) 启动时，Edge 的首个窗口会继承隐藏
    状态（STARTUPINFO.wShowWindow = SW_HIDE）。表现为三件事同时发生：
      - 用户屏幕上完全看不到这个浏览器（以为没启动）
      - 页面 document.hidden === true
      - Chromium 丢弃 Input domain 派发的鼠标事件（realclick 静默失效）
    Page.bringToFront 只能激活页签，改不了窗口的显示状态，所以必须用
    Browser.setWindowBounds 把 windowState 置为 normal 并给出屏幕内坐标。
    """
    ws, t = connect(tid)
    try:
        r = ws.call("Browser.getWindowForTarget", {"targetId": t["id"]})
        info = r.get("result") or {}
        wid = info.get("windowId")
        print("before:", json.dumps(info, ensure_ascii=False))
        if not wid:
            print("SHOWWIN fail: no windowId")
            return
        ws.call("Browser.setWindowBounds",
                {"windowId": wid, "bounds": {"windowState": "normal"}})
        ws.call("Browser.setWindowBounds",
                {"windowId": wid,
                 "bounds": {"left": int(x), "top": int(y),
                            "width": int(w), "height": int(h),
                            "windowState": "normal"}})
        r2 = ws.call("Browser.getWindowBounds", {"windowId": wid})
        print("after :", json.dumps(r2.get("result") or {}, ensure_ascii=False))
        vis = evaluate(ws, "JSON.stringify({hidden:document.hidden,vis:document.visibilityState})")
        print("SHOWWIN ok %s" % vis)
    finally:
        ws.close()


def cmd_realclick(tid, selector):
    """真实鼠标点击（走 CDP Input domain）。

    与 cmd_click 的区别：cmd_click 用 el.click()，只是派发一个 click 事件，
    React / 需要完整指针序列的组件（如 OpenAI 的结账按钮）会忽略它。
    本命令派发 mouseMoved -> mousePressed -> mouseReleased，
    与真人操作等价。

    注意：派发前必须先 Page.bringToFront，否则页面 hidden 时事件会被丢弃。
    """
    ws, t = connect(tid)
    try:
        ws.call("Runtime.enable")
        try:
            ws.call("Page.bringToFront")
        except Exception:
            pass
        pos = evaluate(ws,
            "(function(){var el=document.querySelector(%r);"
            "if(!el) return 'NOT_FOUND';"
            "el.scrollIntoView({block:'center'});"
            "var r=el.getBoundingClientRect();"
            "return JSON.stringify({x:Math.round(r.left+r.width/2),"
            "y:Math.round(r.top+r.height/2),"
            "w:Math.round(r.width),h:Math.round(r.height),"
            "tag:el.tagName,txt:(el.innerText||'').trim().slice(0,40)});})()"
            % selector)
        if pos == "NOT_FOUND":
            print("NOT_FOUND:", selector)
            return
        p = json.loads(pos)
        x, y = p["x"], p["y"]
        base = {"x": x, "y": y, "button": "left", "clickCount": 1,
                "modifiers": 0, "pointerType": "mouse"}
        ws.call("Input.dispatchMouseEvent", dict(base, type="mouseMoved", buttons=0))
        ws.call("Input.dispatchMouseEvent", dict(base, type="mousePressed", buttons=1))
        ws.call("Input.dispatchMouseEvent", dict(base, type="mouseReleased", buttons=0))
        print("REALCLICK <%s> \"%s\" at (%d,%d) size %dx%d"
              % (p["tag"], p["txt"], x, y, p["w"], p["h"]))
    finally:
        ws.close()


def cmd_inject(tid, path):
    with open(path, "r", encoding="utf-8") as f:
        code = f.read()
    print("script size: %.2f MB" % (len(code.encode("utf-8")) / 1048576.0))
    ws, t = connect(tid)
    try:
        ws.call("Runtime.enable")
        ws.call("Page.enable")
        before = evaluate(ws, "!!document.getElementById('wbx-switcher')")
        print("[%s] before: wbx-switcher=%s" % (t["type"], before))
        # 用 IIFE 包裹并捕获异常（顶层 return 在某些上下文非法，统一走表达式返回）
        wrapped = ("(function(){try{\n%s\n;return 'OK_INJECTED';}"
                   "catch(e){return 'THROW: '+(e && e.message ? e.message : String(e))}})()") % code
        r = evaluate(ws, wrapped)
        print("[%s] eval result: %s" % (t["type"], r))
        after = evaluate(ws, "JSON.stringify({sw:!!document.getElementById('wbx-switcher'),"
                             "style:!!document.querySelector('style[data-wbx]'),"
                             "wbx:typeof window.__WBX_THEME__,"
                             "btns:document.querySelectorAll('#wbx-switcher button').length,"
                             "theme: window.__WBX_THEME__ && window.__WBX_THEME__.state && window.__WBX_THEME__.state.theme})")
        print("[%s] after: %s" % (t["type"], after))
    finally:
        ws.close()


def cmd_inject_all(path):
    for t in list_targets():
        if t["type"] in ("page", "iframe"):
            print("\n--- injecting into %s [%s]" % (t["id"], t["type"]))
            try:
                cmd_inject(t["id"], path)
            except Exception as e:
                print("  failed: %s" % e)


def cmd_shot(tid, out):
    ws, t = connect(tid)
    try:
        ws.call("Page.enable")
        r = ws.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        res = r.get("result", {})
        if "data" not in res:
            print("capture failed: %s" % json.dumps(r)[:500])
            return
        with open(out, "wb") as f:
            f.write(base64.b64decode(res["data"]))
        print("saved: %s (%d bytes)" % (out, os.path.getsize(out)))
    finally:
        ws.close()


def cmd_state(tid):
    ws, t = connect(tid)
    try:
        ws.call("Runtime.enable")
        v = evaluate(ws, r"""JSON.stringify({
          sw: !!document.getElementById('wbx-switcher'),
          styles: Array.from(document.querySelectorAll('style')).map(function(s){
            return (s.id||'-') + '|' + (s.getAttribute('data-wbx')||'-') + '|' + s.className + '|' + s.textContent.length;
          }).slice(-6),
          bodyClass: document.body.className,
          cssVars: ['--wbx-art','--wbx-text','--wbx-accent','--wbx-panel','--wbx-side']
            .reduce(function(o,k){o[k]=(document.body.style.getPropertyValue(k)||'').slice(0,42);return o;},{}),
          layers: {
            bg: !!document.getElementById('wbx-bg'),
            ambient: !!document.getElementById('wbx-ambient'),
            fx: !!document.getElementById('wbx-fx'),
            bgLayer: document.querySelectorAll('.wbx-bg-layer').length,
            petals: document.querySelectorAll('.wbx-petal,.wbx-orb,.wbx-snow,.wbx-rain').length
          },
          theme: (window.__WBX_THEME__ && window.__WBX_THEME__.state) ? window.__WBX_THEME__.state.theme : null,
          barRect: (function(){var b=document.getElementById('wbx-switcher');
            if(!b) return null; var r=b.getBoundingClientRect();
            return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),
                    z:getComputedStyle(b).zIndex};})()
        })""")
        print(json.dumps(json.loads(v) if isinstance(v, str) else v, ensure_ascii=False, indent=2))
    finally:
        ws.close()


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    cmd = a[0]
    if cmd == "probe":
        cmd_probe()
    elif cmd == "eval":
        cmd_eval(a[1], a[2])
    elif cmd == "evala":
        cmd_evala(a[1], a[2], *([int(a[3])] if len(a) > 3 else []))
    elif cmd == "inject":
        cmd_inject(a[1], a[2])
    elif cmd == "inject-all":
        cmd_inject_all(a[1])
    elif cmd == "state":
        cmd_state(a[1])
    elif cmd == "shot":
        cmd_shot(a[1], a[2])
    elif cmd == "click":
        cmd_click(a[1], a[2])
    elif cmd == "realclick":
        cmd_realclick(a[1], a[2])
    elif cmd == "front":
        cmd_front(a[1])
    elif cmd == "showwin":
        cmd_showwin(a[1], *[int(v) for v in a[2:6]])
    else:
        print(__doc__)
