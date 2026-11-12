# 架构与防回归备忘

这份文档记录主题的实现机制，以及历史上踩过的坑。**改代码之前先读一遍**——下面每一条都是真实翻车换来的。

---

## 整体结构

注入一个 IIFE 到 WorkBuddy 主窗，它做五件事：

```
applyTheme(key)
├── 建图层   #wbx-ambient(壁纸) #wbx-glass(磨砂玻璃) #wbx-fx(粒子) #wbx-motifs(立绘)
├── 建切换器 #wbx-switcher(右上角浮层，6 主题 + 还原 + 乱序轮播)
├── 玻璃层   buildBlurWall() 用 canvas 预模糊壁纸 → base64 → #wbx-glass 背景
└── 引擎循环 setInterval 1s  ⇒ syncGlass(仅脏时) / syncMotifHost / 宠物避让 / 排队避让
                 setInterval 5s  ⇒ frostWhites / clearMaskOverreach
```

轮播是独立的一条线，不参与渲染引擎：`setRotate(minutes)` 起一个轮询定时器，到点调 `applyTheme(nextRotating())`。顺序由 Fisher-Yates 洗牌生成队列，队首恰为当前主题则与队尾交换（保证不连续重复）。**手动点主题、点 ↺ 都会 `stopRotate()`** —— 用户刚选好就被换走是很烦的事。分钟数存 `wbx-rotate`，自定义值同样持久化。

### 计时不能用 setInterval(间隔)

一开始写的是 `setInterval(fn, 30 * 60000)`，用户反馈"计时不准"。三个原因叠在一起：

1. **漂移累积** —— 每次回调都可能晚几到几十毫秒，跑十几轮就偏出数秒
2. **后台节流** —— 窗口最小化或切到后台时，浏览器把定时器压到 1 次/分钟甚至更久，30 分钟的间隔会被"顺延"成 31、33 分钟（这是体感不准的主因）
3. **长间隔不可靠** —— 一次性 `setTimeout(1800000)` 同样被节流，系统睡眠唤醒后也不补

现在只存**下次该切的绝对时间戳** `rotNextAt`，用 3 秒轮询比对 `Date.now()`：

```js
var late = now - rotNextAt;
rotNextAt = late > rotMs ? (now + rotMs) : (rotNextAt + rotMs);   // 落后超一轮则重算，否则对齐
```

每轮都以绝对时间为准重算，误差不累积；被节流时最多晚 3 秒补上（而不是晚一整轮）；睡眠导致大幅超时只触发一次切换，不补切多次。全新页面实测 1 分钟间隔触发于 **+60.0s 和 +120.0s，误差 0.0 秒**。

### 多实例定时器必须立即吊销

代际守卫（`isCurrentGen()`）只能让旧定时器在**下一次触发时**自毁——这中间有个致命时间窗：旧实例的轮播定时器在自毁前还会再调一次 `applyTheme`，表现为"设了 1 分钟，结果第 10 秒被旧实例切走一次，然后新实例到 60 秒才切"，两个实例交错切。

修法是**全局定时器登记表**：所有常驻定时器经 `wbxInterval()` 创建并登记到 `window.__WBX_TIMERS__`，新实例注入时在 IIFE 开头就把旧的整批 `clearInterval`，不留时间窗。`restore()` 里清定时器也要同步从表里摘除，否则表会残留已失效的 id。

> 加任何常驻定时器都必须走 `wbxInterval()`，直接 `setInterval` 会漏登记，下次注入清不掉。

三个引擎各管一摊：

| 引擎 | 职责 | 标记属性 |
|---|---|---|
| `frostWhites` | 把原生白底容器换成 55% 主题色透底 | `data-wbx-frost` |
| `tameFullscreenBlur` | 剥掉满屏大容器的 `backdrop-filter`（防掉帧） | `data-wbx-tamed` |
| `clearShellVeil` | 给包住侧栏/阅读列的整窗壳写透明底 | `data-wbx-veil` |

三者都在不同 tick 上跑，会互相清对方写的 inline 样式——所以**凡是清除类操作，必须每 tick 校验补回**，不能"只处理一次"。

---

## 踩过的坑

### 图层与壁纸

**整窗壳去蒙层必须语义兜底。**
应用更新把主壳改成 css-modules hash 类名（`_gridView_7xbcw_9`）+ `teams-*` 结构时，`clearShellVeil` 的类名名单全部落空 → 不透明白底盖死 `z-index:-1` 的壁纸层，只剩层级较高的侧栏立绘可见。
现在两层兜底：名单补新类，外加**语义判定**——凡「包含侧栏/阅读列的祖先壳 + 面积 ≥50% 视口 + 接近不透明（rgba 需 alpha ≥ 0.85，半透明面板底不许清）」一律去蒙层。应用再改类名，只要结构没变就能自动兜住。

**`body` / `html` 绝对不能碰。**
应用自带 `html{background:#fff}`，靠 `applyTheme` 写的 inline `transparent` 才透出壁纸。早期 `tameFullscreenBlur` 用 `querySelectorAll('*')` 遍历时包含了它们，`removeProperty` 清掉透明底 → 壁纸整片消失。

**立绘宿主必须自愈。**
`#wbx-motifs` 是 `position:absolute` + 四边贴 0，**挂在侧栏内**才相对侧栏，**挂在 body 下**就相对视口全屏。开机首启时侧栏还没渲染，只能暂挂 body —— 于是立绘糊满整窗。现在：CSS 兜底 `body.wbx-active > #wbx-motifs{display:none!important}`（宁可暂时没立绘也不糊脸）+ `syncMotifHost()` 每秒把宿主搬回侧栏。

**玻璃层缓存键必须包含模糊图版本。**
`buildBlurWall` 是异步的（`Image.onload` + canvas），算完只写 `dataset.blurUrl` 再调 `syncGlass()`。而 `syncGlass` 为性能加的几何缓存只比了 `l/w/h/v` —— 切主题时布局没变，判定"无变化"直接 return，新图永远写不进 `backgroundImage`，玻璃层恒显示上一张壁纸。
教训：**凡是"算出来塞进 dataset 再触发刷新"的路径，缓存键必须带上该数据的版本。**

### 磨砂与面板

**产物面板（`.detail-panel`）整树禁磨砂。**
应用新版把 `cr-*` 类名同时用于对话区和产物面板（`cr-text-block` = 正文块、`sc-code-block-wrap` = 代码块、`sc-editor-content-overlay` = 编辑器内容层）。三处引擎全部误伤，把文档预览糊成毛玻璃。
修法：CSS 规则一律加 `:not(.detail-panel *)`；`tameFullscreenBlur` 对面板后代的 `isOverlay` 强制 false；`frostWhites` 对面板后代直接 continue。
**原则：预览/编辑器类面板 = 文档正文 = 原生干净，任何磨砂都是错的。**

**弹层容器必须保留 `backdrop-filter`。**
`tameFullscreenBlur` 会给超视口 50% 的大容器剥 blur，但 `modal/overlay/dialog/drawer/popover` 词根的弹层是**覆盖在内容之上**的，blur 就是可读性来源——被剥后只剩 33% 磨砂底，底下文字直接穿透混叠。tame 已对这类词根显式写回 `blur(14px)`。

**两个引擎写同一元素会跳变。**
`assertPanelColors` 的 `OVERLAY_SEL` 分支和 `tameFullscreenBlur` 的弹层分支都命中 modal 本体，各自的 inline 后写者赢，浓度不一致就每个 tick 跳一下。现在共用模块级常量 `WBX_MODAL_GLASS`。

**`[class*="wrap"]` 词根规则会误伤内容容器。**
应用改类名就回归。由 `clearMaskOverreach()` 语义兜底：真遮罩 = `fixed` 或面积 ≥35% 视口。

**stylesheet 的 `!important` 打不过 `@layer` 内的 `!important`**，也打不过每帧重写。稳定修改只能进主题源码（inline `!important`）。

**排除主题自身图层要用 id 前缀 `wbx-` 判断**，不能用 `closest('[class*="wbx"]')` —— `body.wbx-active` 会全命中。

### 你还原了，就别再注回来

用户点 ↺ 后 `restore()` 写 `localStorage: wbx-theme-state.active = false`，**所有注入方都必须尊重它**：

- `loadState()` 主窗模式读到 `active:false` 保持原生（早期版本曾无条件强制回 true，正是"还原又被注回"的帮凶）
- 注入脚本 sweep 前先 `read_user_intent()`，显式 false 则主窗跳过、iframe 同步还原
- 唯一允许重置激活的时机 = 双击桌面快捷方式，或点切换器选主题

`wb-skin-watchdog.py` 和 `start-wb-with-skin.py` 是**两个独立注入方**，用户意愿逻辑必须两边一致，否则一方"修复"另一方"作恶"。

`restore()` 还要清 `tame` 写过的 inline —— 那些元素不在 `[data-wbx-frost]` 体系里，`unfrostAll()` 清不到。所以 tame 写入处打 `data-wbx-tamed="1"`，`restore()` 按标记清。

### 长会话性能

根因是**流式输出每个 token 都触发全量扫描**：`querySelectorAll('*')` + 逐元素 `getComputedStyle` + `getBoundingClientRect`，长会话数千节点直接卡死。防线分两层。

**第一层：不要全量扫**

`frostMo` 过滤对话区变更 —— mutation 全在 `.conversation-shell` 内就不调度，交给兜底轮覆盖（路由切换、弹层挂载都在 shell 外，不受影响）。

**第二层：扫的时候也别扫全部**

| 位置 | 改前 | 改后 | 依据 |
|---|---|---|---|
| `frostWhites` 候选 | `querySelectorAll('*')` 1136 个，**76ms/轮** | 块级标签白名单 336 个，**6.1ms/轮** | `isNeutralLight` 只认不透明 `rgb()` 且 `r>=235`，能命中的必然是有布局的块级容器，`span/a/i` 不可能是不透明壳 |
| `clearMaskOverreach` | 21 个候选却 **162ms** | 已打 `data-wbx-maskoff` 的跳过 rect | rect 会强制布局重算，"候选少但很慢"的典型陷阱 |
| `syncGlass` 几何 | 每秒无条件测量 | `glassDirty` 脏标记按需测量 | ResizeObserver + window.resize 已覆盖，每秒重测纯冗余 |

另外三条：

1. `syncGlass` 对几何未变的元素**短路**，但缓存键必须含 `blurUrl` 版本（见上方玻璃层同步）
2. `tameFullscreenBlur` **两遍式**（先纯读收集动作、再统一写），消除读写交错强制重排
3. `frostWhites` 走 `requestIdleCallback`（timeout 兜底）—— 早 100ms 晚 100ms 用户看不出来，撞在渲染帧上就是掉帧

加压实测（约 7500 节点模拟长会话）：

| 指标 | 改前 | 改后 |
|---|---|---|
| 最差单帧 | 212ms | 97ms |
| p99 帧长 | 42.5ms | 18.3ms |
| 长任务 | 9 个 | 2 个 |

正常会话稳态：144 FPS / p50 6.1ms / p99 12.2ms / 零长任务。

> 改这些引擎时**不得删掉短路、过滤和预筛**，删了帧率立刻回退。加新的预筛条件时先想清楚"被筛掉的元素里有没有可能该命中的"，`isNeutralLight` 的判定范围就是安全边界。

### 资源体积

壁纸和立绘以 base64 内嵌在 JS 里，所以体积**全在图片**（6.28MB / 6.43MB，代码只占 0.16MB）。

压缩前必须**逐个检查 alpha 通道实际使用率**，不能按格式一刀切：

```python
img.convert('RGBA').split()[-1].getextrema()   # (amin, amax)
```

- 纯不透明（`amin == 255`）却存成 PNG → 转 JPEG q88，某张 1536×1024 的壁纸 **2024KB → 256KB**
- 真用透明（立绘有 70~83% 透明像素）→ 必须保留 PNG，转 JPEG 会在边缘出白底
- 已经是 JPEG 的高质量图重新编码收益接近 0（甚至变大），不要碰

这一轮把 6.77MB 压到 4.35MB（-35.8%）。

### 图层不能只按"自己记录的引用"删

`state` 是每个 IIFE 里的局部变量，**跨代际完全隔离**。旧实例创建的 `#wbx-fx` 节点仍挂在 `body` 上，而新实例的 `state.fx` 指向的是它自己刚建的那个——按引用删永远删不到旧实例留下的。

后果：切换 N 次就叠 N 层粒子。实测某次会话累积到 **6 个 `#wbx-fx`**（4 组花瓣 + 1 组雪 + 1 组雨同时飘），用户看到的就是"好几个粒子效果叠在同一张壁纸上"。

正确做法是**按 DOM 全量清扫**：

```js
function clearFx() {
  document.querySelectorAll('#wbx-fx, #wbx-bg, .wbx-bg-layer').forEach(n => n.remove());
  document.querySelectorAll('body > .wbx-petal, body > .wbx-orb, body > .wbx-orb2').forEach(n => n.remove());
  state.fx = null;
}
```

同类问题也存在于 `getElementById`：它**永远只返回第一个**，跨代际留下多个同 id 节点时会拿到旧的。所以：

- `start()` 开头统一清扫 `wbx-switcher / wbx-glass / wbx-motifs` 的多余副本，并对 `style[data-wbx="theme"]` 去重
- 各图层用 `dedupeLayer(id)` 取"最后一个（最新）"，其余删掉
- `restore()` 里清玻璃层也要 `querySelectorAll` 全量删

> 判断依据：**只要状态存在闭包里，就不能假设 DOM 里只有自己那一份**。注入式脚本天然会出现多代际共存，所有"我的节点"都要按选择器找，不能只信内存引用。

### iframe

**内联 iframe 绝不能注入主题。**
智能体输出的流程图/图表渲染在 `about:srcdoc` 沙箱 iframe 里。一旦注入，`#wbx-glass` 会把壁纸铺进卡片内部。两道防线：

1. 主题源码环境守卫 = **协议白名单**：iframe 内必须同时满足 `http(s)` **且** `__WBX_EMBED__`；`about:srcdoc` / `about:blank` / `blob:` / `data:` 一律只清理不布置
2. 注入脚本判定 `is_remote_page(url)`，仅 http(s) 才置位 `__WBX_EMBED__`

早期的 bug 是把「所有 iframe」都当远程网页（日志里 113 次 `about:srcdoc` 注入）。

**设置界面是独立窗口**（`windowKind=settings`），同样不注入。

### 应用原生问题（主题改不了，只能绕）

**后台任务条会盖住排队消息条。**
「N 个后台任务运行中」条 `z-index:15`，排队条却挂在 `position:absolute; z-index:auto` 的覆层里 —— 覆层自成层叠上下文，**排队条自身 z-index 抬多高都没用**。

修法是**避让**而非抬升：任务条存在时把整个排队覆层 `translateY(-48px)`。用 `transform` 不用 `top`（应用自己按排队高度算 `top:-100px`，改 top 会打架）。位移量由 `input-stack.top - input-area.top` 实测，不依赖 hash 类名。CSS 由 `[data-wbx-lift="1"]` 门控，属性缺失时优雅退回原生。

**小宠物（成长伙伴）压住排队条按钮。**
外层是 `pointer-events:none`，但内部有个 ~70×70 的隐形热区 `pointer-events:auto`，正好盖住三个 icon-btn。任务条/排队条出现时用 `:has()` 条件隐藏。

**对话消息列表在回答输出完成时会整块重建。**
应用把 `cr-message-list-viewport` 卸载重建，重建后**只挂载当前轮次**，历史回答从 DOM 移除。切走再切回可部分恢复。属于应用侧行为，主题无干预点。

---

## 调试

```bash
# 列 targets
python runtime/wb-cdp.py probe

# 在主窗执行任意 JS
python runtime/wb-cdp.py eval <target-id> "<表达式>"

# 重注主题
python runtime/wb-cdp.py inject <target-id> clannad-theme-console.js
```

CDP 端口是随机的，每次都从 `~/.workbuddy/app/session/DevToolsActivePort` 第一行重新读。

> `probe` 会打印页面 URL，其中带有 `wbSeedToken` 和账号快照。**往公开处贴输出前先删掉那几行。**

**注入后必须验证 computed 值**，别只看代码改了没有。样式写进 inline 但被更高优先级压制是常态。

**A/B 定性法**：怀疑某个现象是主题引入的，调 `window.__wbxRestore()` 还原后重测。还复现 = 应用原生，别在主题里找。

**排查是谁在注入**：`Get-CimInstance Win32_Process` 查 `pythonw` 命令行（`-Filter` 版常被沙箱拦，全量查询再本地筛）。

---

## 关键常量

| 位置 | 值 | 说明 |
|---|---|---|
| `#wbx-glass` 白纱 | 0.42（助理页）/ 0.3（整窗页） | `setGlassVeil()` |
| 玻璃层 CSS mask | 四边羽化 左右 40px / 上下 30px + 24px 圆角 | JS 里不要覆盖，保持 `''` 回落 CSS |
| `frostWhites` 透底 | 55% 主题色 | `color-mix` |
| 弹窗玻璃 | 56% 主题色 + `blur(20px)` | `WBX_MODAL_GLASS` |
| 排队条避让 | 48px，夹紧 `[0,120]` | `syncQueueLift()` |
| watchdog 轮询 | 空闲 15s / 关注 3s | 单例锁端口 47311 |
