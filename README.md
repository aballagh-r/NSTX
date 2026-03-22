# NSTX 
<img src="https://github.com/user-attachments/assets/f304521a-8452-4cb0-9e98-92d6a5de6840" width="150" alt="logo" />
> **vibe netwroking with endpoint and and netwrok device **
![Python](https://img.shields.io/badge/Python-3.11+-FFD43B?style=flat-square&logo=python&logoColor=black)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)
---
## Overview
**NSTX**
<img width="1920" height="1080" alt="1" src="https://github.com/user-attachments/assets/779296ce-7cc7-43e0-999f-7e8850df9699" />
automate configuration, manage devices, and troubleshoot issues across network devices and endpoints. It uses SSH to securely connect to devices and supports multiple vendors .
>if you want to change white/dark mode > go to tools > change theme

## Getting Started
***
## HOW TO USE
***first add the device*** you can add a device by clicking add device or using ctrl+N as a shortcut, and it is important to select the type of the device
<img width="1920" height="1080" alt="3" src="https://github.com/user-attachments/assets/48961d69-2810-4a97-bf91-2d9780dca602" />
***duplicate** just select the device (use ctrl + A for all, deselect by holding ctrl), now you can send one command to multiple devices and return the output like this
<img width="1920" height="1080" alt="4" src="https://github.com/user-attachments/assets/3cb39544-0801-447f-8327-f28f5b6ebc25" />
***console mode**
for console mode, it is important to specify conf t or configure terminal, the input will expand and you can add your configuration, and by ctrl + shift you can send it
<img width="1920" height="1080" alt="5" src="https://github.com/user-attachments/assets/df08ecf0-7947-4186-b560-3543f536c68f" />
***chat bot** 
just click on the icon, it will expand and you can ask the model any question, and the command will respond, if you want you can add it to a task
<img width="1920" height="1080" alt="7" src="https://github.com/user-attachments/assets/3a27930a-6630-494c-a749-998e230bfec8" />
***config sharing**
click on config sharing in tools, you can pull config from a device and push it after editing anything you want like the IP or anything else
<img width="1920" height="1080" alt="8" src="https://github.com/user-attachments/assets/dfa07b70-1129-4ac4-89c6-db34ec01f1b2" />
***autopilot** on this you can just use one prompt or any prompts you want for solving problems, configuration, or anything you need, your imagination is the limit
---
![NSTXautopilot](https://github.com/user-attachments/assets/891aeef2-f00e-4bec-a405-4d0d04d5a120)
### compile
> I will compile it soon for both Linux and Windows.
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
