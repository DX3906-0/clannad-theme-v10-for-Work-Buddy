# Clannad Theme for WorkBuddy

![Clannad](https://img.shields.io/badge/theme-Clannad-ff9ec4) ![platform](https://img.shields.io/badge/platform-Windows-lightgrey) ![python](https://img.shields.io/badge/python-3.8%2B%20stdlib-blue) ![license](https://img.shields.io/badge/license-MIT-green)

把 WorkBuddy 变成《CLANNAD》的坂道。

6 个角色主题，每个都有自己的壁纸、磨砂玻璃、角色立绘和粒子动效。切换器在右上角，随时换，也能一键还原回原生界面。

> **在线预览**：[`docs/gallery.html`](docs/gallery.html) —— 左右切换，可看每个主题的真实效果（壁纸、磨砂玻璃、立绘、粒子）。

---

## 怎么用

需要 Windows + WorkBuddy 桌面客户端，Python 3（只用标准库，装了 pip 之外什么都不用）。

因为主题是通过 CDP 注入到 Electron 渲染进程的，所以第一步得让客户端**开启远程调试**，这一步不做后面都无从谈起。不会的话可以让 AI 帮你改启动参数。

### 三步上手

```bash
# 1. 克隆到 WorkBuddy 的技能目录
git clone <repo-url> ~/.workbuddy/skills/clannad-theme-v10

# 2. 把 CDP 客户端放到用户目录（注入脚本依赖它）
cp ~/.workbuddy/skills/clannad-theme-v10/runtime/wb-cdp.py ~/.workbuddy/

# 3. 注入
python ~/.workbuddy/skills/clannad-theme-v10/runtime/wb-cdp.py \
       inject-all ~/.workbuddy/skills/clannad-theme-v10/clannad-theme-console.js
```

右上角出现切换器，就成了。

> 路径不用手动改。三个脚本都会自己推导 `~/.workbuddy`，也支持 `WBX_ROOT` 等环境变量覆盖，装在别处也能跑。

### 让它一直生效

手动注入只在当前会话有效，客户端一重启就没了。想长期保持，二选一：

**开机常驻自愈（推荐）** —— 把 `runtime/ClannadSkin.vbs` 复制到启动文件夹：

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```

守护进程每 15 秒看一眼，皮肤丢了自动补回来，不管是重启客户端还是切页面。

**跟随客户端启动** —— 把 `runtime/start-wb-with-skin.py` 做成快捷方式，以后从这里启动 WorkBuddy，它会等 CDP 就绪后注入。

### 日常

- 右上角切换器：6 个主题随时切，↺ 一键还原原生
- 选择会记住（存 `localStorage`），重启后还是你上次选的那个
- 还原之后它就真的不动了 —— 守护不会强行注回来。想再开，重新选个主题就行
- 日志：守护写 `~/.workbuddy/skin-watchdog.log`，启动器写 `~/.workbuddy/scripts/inject.log`

### 出问题了

**切换器没出现** → CDP 没连上。确认端口文件 `~/.workbuddy/app/session/DevToolsActivePort` 存在，第一行就是当前端口。客户端没开远程调试的话不会有这个文件。

**皮肤过一会儿自己消失** → 守护没在跑，或者注入被页面导航清掉了。检查 watchdog 日志。

**想彻底干净地还原** → 点 ↺ 即可。如果还有残留，`window.__wbxRestore()` 兜底。

---

## 文件都在哪

```
clannad-theme-console.js     主脚本，单文件（壁纸/立绘全部 base64 内嵌，方便直接注入）
SKILL.md                     WorkBuddy Skill 描述
runtime/
  ├── wb-cdp.py              零依赖 CDP 客户端（stdlib only）
  ├── wb-skin-watchdog.py    自愈守护，单例锁，轮询端口
  ├── start-wb-with-skin.py  启动器：拉起客户端 → 等 CDP → 注入
  ├── ClannadSkin.vbs        开机自启入口（无窗口）
  └── restart-inject-guard.vbs  改了守护代码后用它重启
assets/                      从主脚本里提取出的原始素材，仅供取用
docs/ARCHITECTURE.md         实现机制 + 踩坑记录
```

`runtime/` 里是副本，实际生效的位置在 `~/.workbuddy/`。改完记得同步过去（两边我都保持一致的）。

主脚本单文件 6.5MB，因为壁纸和立绘全都 base64 内嵌 —— 这样 CDP 注入一条命令就够了，不用管资源加载顺序。想单独拿素材的话看 `assets/`，那里是提取好的原图。

---

## 改代码之前

主题逻辑比看上去绕：三个引擎在不同 tick 上跑，会互相覆盖对方写的 inline 样式；应用本身还在持续改类名和 DOM 结构，每版更新都可能让某条规则失效。

**`docs/ARCHITECTURE.md` 里记了所有踩过的坑**，包括：

- 为什么产物面板必须整树禁磨砂
- 为什么壁纸层的 `z-index:-1` 会被一个改名的祖先壳盖死
- 为什么流式输出会让长会话卡死，以及不能删的那三处性能短路
- 哪些现象其实是应用原生问题，主题改不了只能绕

改之前花十分钟读一遍，能省掉不少来回。

---

## 已知限制

- **只支持 Windows**。脚本用了 VBS 和 Windows 路径约定，macOS 要自己改
- **客户端更新可能打破主题**。WorkBuddy 改 DOM 结构或类名时，某些规则会失效。主题对主要容器做了语义兜底（按尺寸和不透明度判断，不认类名），但不是万能的
- **和原生功能有轻微打架**。后台任务条会压住排队消息条、小宠物会挡按钮 —— 这些都是客户端自己的层叠问题，主题只能靠位移避让绕过去
- **注入依赖 CDP**。如果哪天客户端关掉了远程调试，主题就注不进去了

---

## 素材来源

壁纸与角色立绘版权归 © Visual Arts / Key 所有，仅用于个人学习与美化，请勿商用。

---

## License

MIT
