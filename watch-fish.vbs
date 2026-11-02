' 看门狗：每 2 分钟检查鱼的服务，掉了就拉起来
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
script = folder & "\watch-fish.ps1"
sh.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & script & """", 0, False
