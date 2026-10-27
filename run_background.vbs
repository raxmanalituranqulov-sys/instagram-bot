Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\user\Desktop\instagram 34"
WshShell.Run "cmd /c python bot.py", 0, False
