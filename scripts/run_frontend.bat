@echo off
REM Start the React SDN Load Balancer Frontend Dashboard on Windows
cd /d "%~dp0..\front-end"
echo ==========================================================
echo  Starting SDN Load Balancer Frontend Dashboard...
echo  URL: http://localhost:3000
echo ==========================================================
npm.cmd run dev
