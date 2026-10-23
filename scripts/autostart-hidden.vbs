' Starts autostart-runner.ps1 with no visible window (no terminal flashes on screen).
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & dir & "\autostart-runner.ps1"""
CreateObject("WScript.Shell").Run cmd, 0, False
