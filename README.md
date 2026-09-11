# Clannad 主题 v10 for WorkBuddy

WorkBuddy 客户端皮肤：**6 个 Clannad 角色主题**，每个含专属壁纸 + 玻璃拟态 + 角色立绘 + 粒子动效。

## 主题列表

| 主题 | 粒子动效 |
|---|---|
| 古河渚 | 花瓣飘落 🌸 |
| 藤林杏 | 雨滴 ☔ |
| 藤林椋 | 光点浮动 ✨ |
| 坂上智代 | 雪花 ❄️ |
| 伊吹风子 | 光玉 🔮（当前精修主力，海星/海洋意象） |
| 樱花坡道 | 花瓣飘落 🌺 |

右上角有主题切换器，支持切换与一键还原原主题；还原状态持久化（watchdog 不会覆盖）。

## 文件

| 文件 | 说明 |
|---|---|
| `clannad-theme-console.js` | 主皮肤脚本（约 6.7MB，内含 base64 壁纸/立绘），注入 WorkBuddy 主窗生效 |
| `SKILL.md` | WorkBuddy Skill 描述文件 |
| `runtime/wb-skin-watchdog.py` | 自动注入守护：每 6s 轮询 CDP 端口，皮肤缺失则重注；带单例锁，只注入主窗 |
| `runtime/start-wb-with-skin.py` | 桌面快捷方式 `WorkBuddy.lnk` 的启动器：启动 WorkBuddy 并注入皮肤 |
| `runtime/ClannadSkin.vbs` | 开机自启入口（`Startup` 文件夹），无窗口调 pythonw 跑 watchdog |

> `runtime/` 下的文件是副本；**实际生效位置**：`~/.workbuddy/`（watchdog）、
> `~/.workbuddy/scripts/`（启动器）、`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`（自启）。
> 修改时先改仓库内版本再同步过去，保持两边一致。

## 使用说明

### 前置条件

- Windows + WorkBuddy 桌面客户端（Electron），且客户端**开启了远程调试**（CDP，实在不会让ai帮你开）。
  皮肤通过 CDP（Chrome DevTools Protocol）注入，端口随机，由 `~/.workbuddy/app/session/DevToolsActivePort` 文件记录。
- Python 3（仅标准库即可，无需第三方依赖）。

### 方式 A：自动注入（推荐）

1. 确认 `runtime/` 三个脚本中的路径常量与你的环境一致
   （`start-wb-with-skin.py` 顶部硬编码了 `ROOT`、`WB_EXE`、`PYTHON` 等，按需修改）。
2. 把 `clannad-theme-console.js` 与脚本放到 `~/.workbuddy/skills/clannad-theme-v10/`
   （或改常量指向你自己的目录），`wb-cdp.py` 需存在于 `~/.workbuddy/`。
3. 二选一启动：
   - **随 WorkBuddy 启动**：运行 `runtime/start-wb-with-skin.py`（可建快捷方式），它会拉起 WorkBuddy、等 CDP 就绪后注入，并守护扫描新开的 iframe 页（资料库/专家/自动化等懒创建页面也能覆盖）。
   - **开机常驻自愈**：把 `runtime/ClannadSkin.vbs` 放进 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`，watchdog 每 6s 轮询，皮肤丢失/WorkBuddy 重启都会自动重注。

### 方式 B：手动注入（临时体验）

WorkBuddy 启动后，读取端口文件第一行得到 CDP 端口，把 `clannad-theme-console.js` 全文作为表达式在主窗口执行即可：

```python
# 依赖 wb-cdp.py（仓库外的 ~/.workbuddy/ 下），或自行用 websocket 调 CDP
import os, importlib.util
os.environ['CDP_PORT'] = '<端口>'
spec = importlib.util.spec_from_file_location('wb_cdp', '<路径>/wb-cdp.py')
wb_cdp = importlib.util.module_from_spec(spec); spec.loader.exec_module(wb_cdp)
ws, t = wb_cdp.connect('<主窗口targetId>')
wb_cdp.evaluate(ws, open('clannad-theme-console.js', encoding='utf-8').read())
```

> 也可在 WorkBuddy 内用任何能执行 JS 的入口直接粘贴脚本全文运行。

### 日常使用

- 注入成功后**右上角有主题切换器**：6 个角色主题随时切换，也可一键还原为 WorkBuddy 原生主题；选择持久化在 `localStorage`（重启/重注入后保持）。
- 还原后再想启用：重新注入脚本即可（watchdog 会自动清残留再注）。
- 日志：watchdog 写 `~/.workbuddy/skin-watchdog.log`，启动器写 `~/.workbuddy/scripts/inject.log`。

## 壁纸与素材（assets/）

主脚本为单文件设计（base64 内嵌、便于 CDP 直接注入），`assets/` 是从中提取出的独立素材，供浏览与单独取用：

```
assets/
├── wallpapers/            # 6 张角色主题壁纸 + 默认壁纸（1536×942）
│   ├── nagisa.jpg  kyou.jpg  ryou.jpg
│   ├── tomoyo.jpg  fuko.jpg  sakura-petals.jpg
│   └── default-wallpaper.png
├── portraits/             # 6 张角色立绘（600×900 透明 PNG）
│   └── nagisa.png  kyou.png  ryou.png  tomoyo.png  fuko.png  sakura-petals.png
└── fx/
    └── particle-orb.png   # 粒子光斑贴图（256×256）
```

> 改动主题时**不需要**动 `assets/`——运行时读的是 JS 内嵌版本；`assets/` 仅作为独立素材仓库。

## 关键架构（防回归备忘）

- **玻璃层 `#wbx-glass`**：预模糊壁纸 JPEG + 42% 白纱，`syncGlass()` 每秒写几何。
  CSS 自带**四边羽化（左右 40px / 上下 30px）+ 24px 圆角**——JS 里**不要覆盖 mask**（保持 `''` 回落 CSS）。
- **frostable 引擎**：扫白底容器写 55% 主题色。必须排除侧栏**及其祖先**（`_gridViewItem` 包着侧栏，
  `closest()` 查不到祖先链下方的排除目标，需要 `querySelector()` 反查）。
- **多引擎多 tick 竞态**：`tameFullscreenBlur` / `unfrostAll` 会 `removeProperty` 清掉 inline，
  所以蒙层清除（`clearShellVeil`）必须**每 tick 校验补回**，不能"只处理一次"。
- **弹层容器必须保留 backdrop-filter**：`tameFullscreenBlur` 会给超视口 50% 的大容器剥 blur，
  但 modal/overlay/dialog/drawer/popover 词根的**弹层**覆盖在内容之上，blur 就是可读性来源——
  被剥后只剩 33% 磨砂底，底下文字穿透混叠（9/12「添加模型弹窗全透明」根因）。
  tame 已对这类词根显式写回 `blur(14px)`（后写者赢，同时覆盖历史 inline none 残留）；
  例外：`.user-menu-popover` 走专属 blur(20px) 逻辑。
- **遮罩词根规则** `[class*="wrap"]` 会误伤内容容器（应用改类名即回归），
  由 `clearMaskOverreach()` 语义兜底：真遮罩 = fixed 或面积 ≥35% 视口。
- **stylesheet `!important` 打不过 `@layer` 内 important**，也打不过每帧 inline 重写；
  稳定修改只能进主题源码（inline `!important`）。
- 排除主题自身图层要用 `id` 前缀 `wbx-` 判断，**不能用** `closest('[class*="wbx"]')`（body 会全命中）。

## 版本

- `v10-20260911-fixed`：9/11 全部修复完成版（玻璃层今早版式 + 矩形框兜底 + 蒙层清除）。

## 恢复方法

```bash
cd ~/.workbuddy/skills/clannad-theme-v10
git checkout v10-20260911-fixed -- clannad-theme-console.js   # 回退主题文件
# 然后用 wb-cdp.py 重新注入，或等 watchdog 自动重注
```
