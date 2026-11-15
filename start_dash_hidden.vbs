' Serves the static dashboards (Command Centre, pipeline, weekly brief) on port 5070.
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -Command ""Set-Location 'D:\Agent_Market'; & 'D:\Agent_Market\.venv\Scripts\python.exe' -m http.server 5070 --bind 127.0.0.1""", 0, False
