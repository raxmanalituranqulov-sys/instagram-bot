@echo off
chcp 65001 > nul
title Instagram & YouTube Telegram Bot
echo ========================================================
echo   Instagram, YouTube, Video Converter va AI Chat Bot
echo ========================================================
echo.
echo Bot ishga tushirilmoqda...
python bot.py
if errorlevel 1 (
    echo.
    echo Xatolik yuz berdi. Iltimos, yuqoridagi xabarni tekshiring.
    pause
)
