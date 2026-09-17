' Clannad 主题注入守护 - 静默启动入口（无控制台窗口）
' 用途：改了 scripts/start-wb-with-skin.py 后，用它重启常驻注入守护、加载新逻辑。
'      explorer 代启 → 新进程挂在 explorer 下、脱离 WorkBuddy 会话，可长期存活。
' 用法：explorer.exe "C:\Users\HP\.workbuddy\scripts\restart-inject-guard.vbs"
'      （或直接双击本文件）
' 注意：脚本自身不做单实例互斥。重启前请先结束旧实例（任务管理器里结束
'      pythonw.exe；若不确定哪个是它，重启 WorkBuddy 后重新双击桌面快捷方式即可）。
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\HP\.workbuddy"
sh.Run """C:\Users\HP\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe"" -X utf8 ""C:\Users\HP\.workbuddy\scripts\start-wb-with-skin.py""", 0, False
