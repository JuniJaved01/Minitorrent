@echo off
rem Rebuilds ui\static\app.css from input.css (needs Node.js once; the result is committed so users do not need Node).
cd /d "%~dp0" && npx --yes tailwindcss@3.4.17 -c tailwind.config.js -i input.css -o ..\static\app.css --minify
