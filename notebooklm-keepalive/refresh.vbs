' Giữ phiên NotebookLM (Claude 2026-10-04, sửa 05/10): chạy keepalive.ps1 ẩn — refresh, lỗi thì login bằng hồ sơ Chrome riêng, ghi keepalive.log
Set sh = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & here & "\keepalive.ps1""", 0, True
