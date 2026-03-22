# NSTX 
```
      ___           ___           ___           ___     
     /\__\         /\  \         /\  \         |\__\    
    /::|  |       /::\  \        \:\  \        |:|  |   
   /:|:|  |      /:/\ \  \        \:\  \       |:|  |   
  /:/|:|  |__   _\:\~\ \  \       /::\  \      |:|__|__ 
 /:/ |:| /\__\ /\ \:\ \ \__\     /:/\:\__\ ____/::::\__\
 \/__|:|/:/  / \:\ \:\ \/__/    /:/  \/__/ \::::/~~/~   
     |:/:/  /   \:\ \:\__\     /:/  /       ~~|:|~~|    
     |::/  /     \:\/:/  /     \/__/          |:|  |    
     /:/  /       \::/  /                     |:|  |    
     \/__/         \/__/                       \|__|   
```
> **vibe netwroking with endpoint and and netwrok device **
![Python](https://img.shields.io/badge/Python-3.11+-FFD43B?style=flat-square&logo=python&logoColor=black)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)
---
## Overview
**NSTX**
<img width="1920" height="1080" alt="1" src="https://github.com/user-attachments/assets/779296ce-7cc7-43e0-999f-7e8850df9699" />
 
automate configuration, manage devices, and troubleshoot issues across network devices and endpoints. It uses SSH to securely connect to devices and supports multiple vendors .
>this link for both linux and windows compiled file

## Getting Started
****
**HOW TO USE ** first add the device by add device 

### Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/NSTX.git
cd NSTX
# Install dependencies
pip install -r requirements.txt
# Launch
python main.py
```
## Build — Standalone Executable
NSTX can be compiled using:
```bash
python -m PyInstaller \
  --onefile \
  --noconsole \
  --icon=icon.ico \
  --add-data "icon.ico;." \
  --clean \
  --name NSTX \
  main.py
```
Output:
```
dist/
 └── NSTX.exe
```
---
