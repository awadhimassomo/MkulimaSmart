@echo off
set DJANGO_SETTINGS_MODULE=MkulimaSmart.settings
python -m daphne -b  192.168.1.197 -p 8001 MkulimaSmart.asgi:application
