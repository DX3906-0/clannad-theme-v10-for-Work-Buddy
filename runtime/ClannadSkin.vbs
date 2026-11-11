' Clannad skin watchdog - auto start (no console window)
' Launched by explorer at logon from the Startup folder.
' 路径自动推导：本文件位于 <root>\skills\clannad-theme-v10\runtime\，向上三级即 WorkBuddy 用户目录。
' 如需自定义，设置环境变量 WBX_ROOT / WBX_SKIN_SCRIPT 后再运行。
Option Explicit
Dim fso, sh, here, root, py, script, vdir

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(fso.GetParentFolderName(fso.GetParentFolderName(here)))

If Len(sh.Environment("PROCESS")("WBX_ROOT")) > 0 Then root = sh.Environment("PROCESS")("WBX_ROOT")

' 优先用 WorkBuddy 自带的 pythonw（避免依赖系统 PATH）
py = ""
If fso.FolderExists(root & "\binaries\python\versions") Then
    For Each vdir In fso.GetFolder(root & "\binaries\python\versions").SubFolders
        If fso.FileExists(vdir.Path & "\pythonw.exe") Then py = vdir.Path & "\pythonw.exe"
    Next
End If
If py = "" Then py = "pythonw.exe"

script = root & "\wb-skin-watchdog.py"
If Len(sh.Environment("PROCESS")("WBX_SKIN_SCRIPT")) > 0 Then script = sh.Environment("PROCESS")("WBX_SKIN_SCRIPT")

sh.CurrentDirectory = root
sh.Run """" & py & """ -X utf8 """ & script & """", 0, False
