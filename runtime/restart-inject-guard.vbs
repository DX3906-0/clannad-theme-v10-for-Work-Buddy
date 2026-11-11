' Clannad 主题注入守护 - 静默启动入口（无控制台窗口）
' 用途：改了注入脚本后，用它重启常驻守护、加载新逻辑。
'      explorer 代启 → 新进程挂在 explorer 下、脱离 WorkBuddy 会话，可长期存活。
' 用法：直接双击本文件，或 explorer.exe "<本项目>\runtime\restart-inject-guard.vbs"
' 注意：脚本自身不做单实例互斥。重启前请先结束旧实例（任务管理器里结束
'      pythonw.exe；若不确定哪个是它，重启 WorkBuddy 后重新双击桌面快捷方式即可）。
' 路径自动推导：本文件位于 <root>\skills\clannad-theme-v10\runtime\，
'   脚本在 <root>\scripts\，WorkBuddy 用户目录为向上三级。
Option Explicit
Dim fso, sh, here, root, py, script, vdir, cand

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(fso.GetParentFolderName(fso.GetParentFolderName(here)))
If Len(sh.Environment("PROCESS")("WBX_ROOT")) > 0 Then root = sh.Environment("PROCESS")("WBX_ROOT")

py = ""
If fso.FolderExists(root & "\binaries\python\versions") Then
    For Each vdir In fso.GetFolder(root & "\binaries\python\versions").SubFolders
        If fso.FileExists(vdir.Path & "\pythonw.exe") Then py = vdir.Path & "\pythonw.exe"
    Next
End If
If py = "" Then py = "pythonw.exe"

' 优先 <root>\scripts\ 下的副本，回落本项目 runtime\ 内的副本
script = root & "\scripts\start-wb-with-skin.py"
If Not fso.FileExists(script) Then script = here & "\start-wb-with-skin.py"

sh.CurrentDirectory = root
sh.Run """" & py & """ -X utf8 """ & script & """", 0, False
