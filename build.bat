@echo off
:: RFIDTagBuilder v3 — Windows build script
:: Requires: pip install pyinstaller customtkinter openpyxl

echo Building RFIDTagBuilder v3...

pyinstaller ^
  --onefile ^
  --windowed ^
  --name "RFIDTagBuilder" ^
  --add-data "README.md;." ^
  --collect-all customtkinter ^
  main.py

echo.
echo Build complete. Output: dist\RFIDTagBuilder.exe
pause
