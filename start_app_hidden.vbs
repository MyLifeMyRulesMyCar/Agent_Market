' Starts the Marketing Agents web app detached from any console.
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""D:\Agent_Market\run_app.ps1""", 0, False
