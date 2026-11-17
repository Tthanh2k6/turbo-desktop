' Starts the turbo-desktop hub hidden at Windows logon (put a shortcut to this file in shell:startup).
' Log: %LOCALAPPDATA%\turbo-desktop-hub\serve.log
Set sh = CreateObject("WScript.Shell")
hub = CreateObject("Scripting.FileSystemObject").GetParentFolderName(CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName))
logDir = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\turbo-desktop-hub"
If Not CreateObject("Scripting.FileSystemObject").FolderExists(logDir) Then CreateObject("Scripting.FileSystemObject").CreateFolder(logDir)
sh.CurrentDirectory = hub
sh.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
cmd = "cmd /c """"" & hub & "\.venv\Scripts\python.exe"" -u -m turbo_hub serve > """ & logDir & "\serve.log"" 2>&1"""
sh.Run cmd, 0, False
