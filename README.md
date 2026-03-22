# NSTX 
<img src="https://github.com/user-attachments/assets/f304521a-8452-4cb0-9e98-92d6a5de6840" width="150" alt="logo" />

>
![Python](https://img.shields.io/badge/Python-3.11+-FFD43B?style=flat-square&logo=python&logoColor=black)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)
---
## Overview
**NSTX**
this app can help for automate configuration, manage devices, and troubleshoot issues across network devices and endpoints. It uses SSH to securely connect to devices and supports multiple vendors .
<img width="1920" height="1080" alt="1" src="https://github.com/user-attachments/assets/779296ce-7cc7-43e0-999f-7e8850df9699" />
>if you want to change white/dark mode > go to tools > change theme

## Getting Started
***
## HOW TO USE
***DEVICE*** To add a device, click Add Device or press Ctrl + N.
Make sure to select the correct device type before saving.
<img width="1920" height="1080" alt="3" src="https://github.com/user-attachments/assets/48961d69-2810-4a97-bf91-2d9780dca602" />
***duplicate** You can select multiple devices to send commands at once.
Press Ctrl + A to select all devices
Hold Ctrl to select or deselect specific devices
Once selected, you can run one command on all devices and view the results together.
<img width="1920" height="1080" alt="4" src="https://github.com/user-attachments/assets/3cb39544-0801-447f-8327-f28f5b6ebc25" />
***console mode**
The input area will expand so you can write your configuration.
Press Ctrl + Shift to send the command.
<img width="1920" height="1080" alt="5" src="https://github.com/user-attachments/assets/df08ecf0-7947-4186-b560-3543f536c68f" />
***chat bot** 
Click the chatbot icon to open it.
Ask questions or request commands
The chatbot will generate a response
You can add the result to a task if needed
<img width="1920" height="1080" alt="7" src="https://github.com/user-attachments/assets/3a27930a-6630-494c-a749-998e230bfec8" />
***config sharing**
Go to Tools → Config Sharing.
Pull configuration from a device
Edit it (e.g., change IP address)
Push it back to a device
<img width="1920" height="1080" alt="8" src="https://github.com/user-attachments/assets/dfa07b70-1129-4ac4-89c6-db34ec01f1b2" />
***autopilot** 
Autopilot lets you automate tasks using prompts.
Use one or multiple prompts
Apply configurations or fix issues
Customize it based on your needs
Your imagination is the limit.
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
