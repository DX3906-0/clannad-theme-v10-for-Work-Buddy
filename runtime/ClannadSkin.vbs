' Clannad skin watchdog - auto start (no console window)
' Launched by explorer at logon from the Startup folder.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\HP\.workbuddy"
sh.Run """C:\Users\HP\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe"" -X utf8 ""C:\Users\HP\.workbuddy\wb-skin-watchdog.py""", 0, False
