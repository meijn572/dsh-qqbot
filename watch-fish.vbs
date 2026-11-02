' 看门狗：每 2 分钟检查鱼的服务，掉了就拉起来
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""D:\QQBot\dshbot\watch-fish.ps1""", 0, False
