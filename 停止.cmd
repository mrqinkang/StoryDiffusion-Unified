@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 停止 StoryDiffusion 服务
echo 正在停止 StoryDiffusion 服务...

(
echo import os, subprocess, socket
echo def find_python_pids_on_ports(start=8000, end=8100):
echo     '''查找占用指定端口范围的 Python 进程 PID'''
echo     pids = set()
echo     for port in range(start, end+1):
echo         with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
echo             if s.connect_ex(('127.0.0.1', port)) == 0:
echo                 continue  # 端口可用，跳过
echo         try:
echo             out = subprocess.check_output(
echo                 'netstat -ano ^^^| findstr :%%d ^^^| findstr LISTENING' %% port,
echo                 shell=True, text=True
echo             )
echo             for line in out.strip().splitlines():
echo                 parts = line.strip().split()
echo                 if parts:
echo                     pid = parts[-1]
echo                     if pid.isdigit():
echo                         pids.add(int(pid))
echo         except:
echo             pass
echo     return pids
echo pids = find_python_pids_on_ports()
echo if not pids:
echo     print('没有找到运行中的 StoryDiffusion 服务')
echo else:
echo     for pid in pids:
echo         try:
echo             subprocess.run(['taskkill', '/f', '/pid', str(pid)], capture_output=True)
echo             print('✅ 已终止 PID %%s' %% pid)
echo         except:
echo             print('❌ 无法终止 PID %%s' %% pid)
echo     print('共停止 %%s 个进程' %% len(pids))
) > _temp_kill.py

python _temp_kill.py
del /f /q _temp_kill.py

echo.
pause