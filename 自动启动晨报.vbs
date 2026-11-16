Option Explicit
Dim shell, fso, base, bat
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
bat = fso.BuildPath(base, "启动晨报.bat")
shell.Run Chr(34) & bat & Chr(34), 0, False
