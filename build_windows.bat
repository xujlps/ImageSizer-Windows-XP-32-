@echo off
chcp 65001 >nul

echo ImageSizer - Windows XP 32-bit build
 echo.
echo Required build environment:
echo   Python 3.4.x 32-bit
echo   Pillow 5.4.1
echo   PyInstaller 3.4
echo.

py -3.4 -m pip install "Pillow==5.4.1"
py -3.4 -m pip install "PyInstaller==3.4"
py -3.4 -m PyInstaller --noconfirm --clean --onefile --windowed --name ImageSizer_XP32 ImageSizer.py

if exist dist\ImageSizer_XP32.exe (
    echo.
    echo Build complete: dist\ImageSizer_XP32.exe
) else (
    echo.
    echo Build failed.
)
pause
