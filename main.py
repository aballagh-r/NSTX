import sys
import os
import json
import requests
import time
import re
import threading
import subprocess
import platform
import ctypes
from   dataclasses import dataclass, field
from   enum import Enum, auto
from   typing import Optional
from   datetime import datetime
from   collections import defaultdict
import getpass

from PyQt6.QtWidgets import * 
from PyQt6.QtWidgets import *
from PyQt6.QtCore    import *
from PyQt6.QtGui     import *
from model           import AutopilotPanel

# ───────────────────────────────────────────────
# Global State
# ───────────────────────────────────────────────
devices = []            
workers = []             
cmd_history = []         
Tasks = {}                
quick_commands = []      
selected_indexes = set() 
device_sessions = {}     
current_theme = "light"

THEMES = {
    "dark": {
        "bg": "#070a0f", "fg": "#c8d6e5", "base": "#0d1117", "alt_base": "#0a1018",
        "border": "#1e2a3a", "input": "#0d1117", "input_text": "#e0eeff",
        "button": "#0d1117", "button_text": "#7a9fc0", "button_hover": "#1e2a3a",
        "highlight": "#1e3a5f", "accent": "#00d4ff", "success": "#00ff88",
        "error": "#ff4455", "warn": "#ffaa00", "meta": "#446688",
        "console": "#020509", "console_text": "#00cc88",
        "selection": "#0a2040", "selection_border": "#00d4ff",
        "card_bg": "#0d1117", "card_hover": "#111a25"
    },
    "light": {
        "bg": "#f5f7fa", "fg": "#1c2024", "base": "#ffffff", "alt_base": "#eef1f5",
        "border": "#dce1e6", "input": "#ffffff", "input_text": "#1c2024",
        "button": "#ffffff", "button_text": "#445566", "button_hover": "#f0f4f8",
        "highlight": "#e0f7fa", "accent": "#0088cc", "success": "#1a7f37",
        "error": "#cf222e", "warn": "#9a6700", "meta": "#5c6b7f",
        "console": "#ffffff", "console_text": "#1c2024",
        "selection": "#e0f7fa", "selection_border": "#0088cc",
        "card_bg": "#ffffff", "card_hover": "#f0f4f8"
    }
}

CONFIG_FILE = os.path.expanduser("~/.NSTX_config.json")
AI_URL = "https://openrouter.ai/api/v1/chat/completions"

ASCII_BANNER = r"""
 .-._          ,-,--.  ,--.--------.          ,-.--, 
/==/ \  .-._ ,-.'-  _\/==/,  -   , -\.--.-.  /=/, .' 
|==|, \/ /, /==/_ ,_.'\==\.-.  - ,-./\==\ -\/=/- /   
|==|-  \|  |\==\  \    `--`\==\- \    \==\ `-' ,/    
|==| ,  | -| \==\ -\        \==\_ \    |==|,  - |    
|==| -   _ | _\==\ ,\       |==|- |   /==/   ,   \   
|==|  /\ , |/==/\/ _ |      |==|, |  /==/, .--, - \  
/==/, | |- |\==\ - , /      /==/ -/  \==\- \/=/ , /  
`--`./  `--` `--`---'       `--`--`   `--`-'  `--`   
"""

TAGLINE = "This app was created by Tarik ."


def typewriter(text: str, delay: float = 0.015):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()


def print_banner():
    typewriter(ASCII_BANNER, delay=0.004)
    typewriter(TAGLINE, delay=0.045)
    print()


def save_api_key(api_key: str):
    data = {"api_key": api_key}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        check = json.load(f)
    if check.get("api_key") != api_key:
        raise RuntimeError("Config verification failed — key was not saved correctly.")


def load_api_key() -> str | None:
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        key = data.get("api_key", "").strip()
        return key if key else None
    except (json.JSONDecodeError, IOError):
        return None


def get_api_key() -> str:
    key = load_api_key()
    if key:
        return key

    print("No API key found.")
    print("Create a free key at: https://openrouter.ai/settings/keys\n")
    while True:
        api_key = getpass.getpass("Enter your OpenRouter API key: ").strip()
        if api_key:
            break
        print("Key cannot be empty, please try again.")

    save_api_key(api_key)
    print(f"Key saved to {CONFIG_FILE}")
    return api_key
print_banner()
API_KEY = get_api_key()


if __name__ == "__main__":
    print("Starting ...")

def resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def save_config():
    try:
        safe_devices = []
        for d in devices:
            sd = {k: v for k, v in d.items() if k not in ("connection",)}
            safe_devices.append(sd)
        with open(CONFIG_FILE, "w") as f:
            json.dump({
                "devices": safe_devices,
                "Tasks": Tasks,
                "quick_commands": quick_commands,
                "theme": current_theme
            }, f, indent=2)
    except Exception as e:
        print(f"[Config save error] {e}")


def load_config():
    global current_theme
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            for d in data.get("devices", []):
                d.setdefault("connected", False)
                d.setdefault("hostname", None)
                d.setdefault("tags", [])
                d.setdefault("notes", "")
                d.setdefault("secret", "")
                d.setdefault("port", 22)
                devices.append(d)
            Tasks.update(data.get("Tasks", {}))
            current_theme = data.get("theme", "dark")
            
            # Load quick commands
            qc = data.get("quick_commands", [])
            if qc:
                quick_commands.extend(qc)
            else:
                # Defaults if empty
                quick_commands.extend([
                    {"label": "ver", "cmd": "show version"},
                    {"label": "arp", "cmd": "show arp"},
                    {"label": "run", "cmd": "show running-config"},
                    {"label": "vlan", "cmd": "show vlan brief"},
                    {"label": "cpu", "cmd": "show processes cpu sorted"},
                    {"label": "log", "cmd": "show log"},
                ])
    except Exception as e:
        print(f"[Config load error] {e}")


# ───────────────────────────────────────────────
# Smart Config Parser
# ───────────────────────────────────────────────
class Vendor(Enum):
    CISCO_IOS    = "cisco_ios"
    CISCO_IOSXE  = "cisco_xe"
    CISCO_IOSXR  = "cisco_xr"
    CISCO_NXOS   = "cisco_nxos"
    JUNIPER      = "juniper_junos"
    HP_COMWARE   = "hp_comware"
    HP_PROCURVE  = "hp_procurve"
    HUAWEI       = "huawei"
    FORTINET     = "fortinet"
    PALOALTO     = "paloalto_panos"
    DELL_OS10    = "dell_os10"
    ALCATEL_AOS  = "alcatel_aos"
    GENERIC      = "generic"


class CmdType(Enum):
    SHOW         = auto()   
    EXEC         = auto()  
    CONFIG       = auto() 
    SPECIAL_SAVE = auto()   
    SPECIAL_RELOAD = auto() 
    INTERACTIVE  = auto()   
    SUBMODE_ENTER = auto()  
    SUBMODE_EXIT  = auto()  
    CONFIG_END    = auto()  
    COMMENT       = auto()  
    EMPTY         = auto()  


class SendStrategy(Enum):
    SEND_COMMAND        = "send_command"
    SEND_COMMAND_TIMING = "send_command_timing"   
    SEND_CONFIG_SET     = "send_config_set"
    SEND_CONFIG_COMMIT  = "send_config_commit"    
    MANUAL_CONFIRM      = "manual_confirm"        


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────

@dataclass
class ParsedCommand:
    raw: str
    normalized: str
    cmd_type: CmdType
    strategy: SendStrategy
    submode_context: str = ""        
    requires_confirm: bool = False
    confirm_pattern: str = ""        
    vendor_hint: Optional[Vendor] = None
    notes: str = ""


@dataclass
class ConfigBlock:
    context_stack: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    @property
    def context_path(self) -> str:
        return " > ".join(self.context_stack) if self.context_stack else "global"


# ─────────────────────────────────────────────
# Vendor detection
# ─────────────────────────────────────────────

_VENDOR_FINGERPRINTS: list[tuple[re.Pattern, Vendor]] = [
    (re.compile(r"cisco\s+ios\s+xr",           re.I), Vendor.CISCO_IOSXR),
    (re.compile(r"cisco\s+nexus|nxos|nx-os",   re.I), Vendor.CISCO_NXOS),
    (re.compile(r"cisco\s+ios.{0,30}xe|ios-xe", re.I), Vendor.CISCO_IOSXE),
    (re.compile(r"cisco\s+ios|cisco ios",       re.I), Vendor.CISCO_IOS),
    (re.compile(r"juniper|junos",               re.I), Vendor.JUNIPER),
    (re.compile(r"dell|os10",                   re.I), Vendor.DELL_OS10),
    (re.compile(r"alcatel|aos",                 re.I), Vendor.ALCATEL_AOS),
    (re.compile(r"comware|h3c",                 re.I), Vendor.HP_COMWARE),
    (re.compile(r"procurve|provision",          re.I), Vendor.HP_PROCURVE),
    (re.compile(r"huawei|vrp",                  re.I), Vendor.HUAWEI),
    (re.compile(r"fortigate|fortios",           re.I), Vendor.FORTINET),
    (re.compile(r"pan-os|palo alto",            re.I), Vendor.PALOALTO),
]

def detect_vendor(banner_or_version_output: str) -> Vendor:
    for pattern, vendor in _VENDOR_FINGERPRINTS:
        if pattern.search(banner_or_version_output):
            return vendor
    return Vendor.GENERIC


# ─────────────────────────────────────────────
# Per-vendor config triggers / submodes / end keywords
# ─────────────────────────────────────────────

_VENDOR_PROFILES: dict[Vendor, dict] = {

    Vendor.CISCO_IOS: {
        "config_enter":    {"conf t", "configure terminal", "configure t", "conf terminal", "config t"},
        "config_exit":     {"end"},
        "submode_exit":    {"exit", "quit"},
        "save":            {"wr", "write", "write memory", "copy run start",
                            "copy running-config startup-config"},
        "reload":          {"reload"},
        "confirm_cmds":    [r"^reload", r"^write\s+erase", r"^erase\s+startup",
                            r"^no\s+service\s+password-encryption",
                            r"^debug\s+all"],
        "show_prefixes":   ["show", "ping", "traceroute", "tracert", "debug",
                            "undebug", "test", "verify", "more", "type",
                            "terminal", "dir", "clock"],
        "submode_patterns": [
            r"^interface\s+\S+",
            r"^router\s+(ospf|eigrp|bgp|rip|isis|lisp)\s*\S*",
            r"^line\s+(vty|con|aux|tty)\s*\S*",
            r"^vlan\s+\d[\d,\-]*",
            r"^route-map\s+\S+",
            r"^policy-map\s+\S+",
            r"^class-map\s+\S+",
            r"^crypto\s+(isakmp|ipsec|map|keyring|pki)\s+\S+",
            r"^ip\s+dhcp\s+pool\s+\S+",
            r"^ip\s+(access-list|prefix-list)\s+\S+",
            r"^ipv6\s+(access-list|prefix-list)\s+\S+",
            r"^mac\s+access-list\s+\S+",
            r"^mpls\s+ldp",
            r"^segment-routing",
            r"^template\s+\S+",
            r"^parameter-map\s+\S+",
            r"^ip\s+sla\s+\d+",
            r"^track\s+\d+",
            r"^event\s+manager\s+applet\s+\S+",
            r"^voice\s+(service|class|register|translation)\s+\S*",
            r"^dial-peer\s+\S+",
            r"^stacking",
        ],
        "global_config_keywords": [
            "ip route", "ipv6 route", "ip routing", "ipv6 unicast-routing",
            "no ip", "no ipv6", "access-list", "ip access-list",
            "vlan", "hostname", "spanning-tree", "ntp", "snmp-server",
            "logging", "username", "service", "aaa", "banner",
            "enable", "boot", "archive", "alias", "ip domain",
            "ip name-server", "ip default-gateway", "ip ssh",
            "ip http", "ip ftp", "ip tftp", "ip flow",
            "lldp", "cdp", "errdisable", "mls", "monitor session",
            "storm-control", "port-security", "dot1x", "radius-server",
            "tacacs-server", "key chain", "object-group", "zone-pair",
            "zone security", "flow record", "flow monitor", "flow exporter",
            "netflow", "sampler", "traffic-shape", "clock timezone",
            "redundancy", "mode sso", "mode rpr",
        ],
    },

    Vendor.CISCO_NXOS: {
        "config_enter":    {"conf t", "configure terminal", "config t"},
        "config_exit":     {"end"},
        "submode_exit":    {"exit"},
        "save":            {"copy run start", "copy running-config startup-config"},
        "reload":          {"reload"},
        "confirm_cmds":    [r"^reload", r"^write\s+erase", r"^erase"],
        "show_prefixes":   ["show", "ping", "traceroute", "debug", "undebug",
                            "ethanalyzer", "slot", "test"],
        "submode_patterns": [
            r"^interface\s+\S+",
            r"^vlan\s+\d[\d,\-]*",
            r"^vrf\s+(context|definition)\s+\S+",
            r"^router\s+(ospf|bgp|eigrp|isis)\s*\S*",
            r"^route-map\s+\S+",
            r"^policy-map\s+(?:type\s+\S+\s+)?\S+",
            r"^class-map\s+(?:type\s+\S+\s+)?\S+",
            r"^ip\s+(access-list|prefix-list)\s+\S+",
            r"^ipv6\s+(access-list|prefix-list)\s+\S+",
            r"^port-profile\s+\S+",
            r"^vpc\s+domain\s+\d+",
            r"^evpn",
            r"^nv\s+overlay",
            r"^segment-routing",
            r"^feature-set\s+\S+",
        ],
        "global_config_keywords": [
            "feature", "no feature", "hostname", "ip route", "ipv6 route",
            "ntp", "snmp-server", "logging", "username", "aaa", "banner",
            "spanning-tree", "lacp", "vpc", "fabricpath", "overlay",
        ],
    },

    Vendor.CISCO_IOSXR: {
        "config_enter":    {"conf t", "configure terminal", "configure"},
        "config_exit":     {"end", "abort"},
        "submode_exit":    {"exit"},
        "save":            {"commit", "commit confirmed", "commit replace"},
        "reload":          {"reload"},
        "confirm_cmds":    [r"^reload", r"^commit\s+replace"],
        "show_prefixes":   ["show", "ping", "traceroute", "monitor", "debug",
                            "trace", "test"],
        "submode_patterns": [
            r"^interface\s+\S+",
            r"^router\s+(ospf|bgp|isis|eigrp|rip)\s*\S*",
            r"^vrf\s+\S+",
            r"^route-policy\s+\S+",
            r"^policy-map\s+\S+",
            r"^class-map\s+\S+",
            r"^ipv4\s+access-list\s+\S+",
            r"^ipv6\s+access-list\s+\S+",
            r"^mpls\s+ldp",
            r"^segment-routing",
            r"^l2vpn",
            r"^evpn",
            r"^bfd",
            r"^multicast-routing",
        ],
        "global_config_keywords": [
            "hostname", "ntp", "snmp-server", "logging", "username", "aaa",
            "banner", "ip route", "router static", "commit",
        ],
    },

    Vendor.JUNIPER: {
        "config_enter":    {"configure", "configure exclusive", "configure private"},
        "config_exit":     {"run", "exit"},          # 'exit' from config drops to shell
        "submode_exit":    {"up", "top"},
        "save":            {"commit", "commit confirmed", "commit check",
                            "commit and-quit"},
        "reload":          {"request system reboot"},
        "confirm_cmds":    [r"^request\s+system\s+reboot",
                            r"^rollback\s+0",
                            r"^load\s+factory-default"],
        "show_prefixes":   ["show", "run show", "ping", "traceroute",
                            "monitor", "request", "clear"],
        "submode_patterns": [
            r"^set\s+interfaces\s+\S+",
            r"^set\s+protocols\s+\S+",
            r"^set\s+routing-options\s+",
            r"^set\s+policy-options\s+",
            r"^set\s+firewall\s+",
            r"^set\s+class-of-service\s+",
            r"^set\s+vlans\s+\S+",
            r"^set\s+groups\s+\S+",
            r"^set\s+system\s+",
            r"^edit\s+\S+",
        ],
        "global_config_keywords": ["set ", "delete ", "rename ", "deactivate ",
                                   "activate ", "annotate "],
    },

    Vendor.DELL_OS10: {
        "config_enter":    {"conf t", "configure terminal", "config t"},
        "config_exit":     {"end"},
        "submode_exit":    {"exit"},
        "save":            {"write", "write memory", "copy run start"},
        "reload":          {"reload"},
        "confirm_cmds":    [r"^reload", r"^write\s+erase"],
        "show_prefixes":   ["show", "ping", "traceroute", "bash", "diff",
                            "watch", "test", "verify"],
        "submode_patterns": [
            r"^interface\s+\S+",
            r"^router\s+(ospf|bgp|isis|rip)\s*\S*",
            r"^vlan\s+\d[\d,\-]*",
            r"^vrf\s+(instance|definition)\s+\S+",
            r"^route-map\s+\S+",
            r"^policy-map\s+\S+",
            r"^class-map\s+\S+",
            r"^ip\s+(access-list|prefix-list)\s+\S+",
            r"^management\s+(ssh|api|cvx|security)\s*\S*",
            r"^event-handler\s+\S+",
            r"^daemon\s+\S+",
        ],
        "global_config_keywords": [
            "hostname", "ip route", "ipv6 route", "ntp", "snmp-server",
            "logging", "username", "aaa", "banner", "spanning-tree",
            "lacp", "lldp", "clock", "service",
        ],
    },

    Vendor.ALCATEL_AOS: {
        "config_enter":    {"conf t", "configure terminal", "configure t", "conf terminal", "config t"},
        "config_exit":     {"end"},
        "submode_exit":    {"exit", "quit"},
        "save":            {"wr", "write", "write memory", "copy run start",
                            "copy running-config startup-config"},
        "reload":          {"reload"},
        "confirm_cmds":    [r"^reload", r"^write\s+erase", r"^erase\s+startup",
                            r"^no\s+service\s+password-encryption",
                            r"^debug\s+all"],
        "show_prefixes":   ["show", "ping", "traceroute", "tracert", "debug",
                            "undebug", "test", "verify", "more", "type",
                            "terminal", "dir", "clock"],
        "submode_patterns": [
            r"^interface\s+\S+",
            r"^router\s+(ospf|eigrp|bgp|rip|isis|lisp)\s*\S*",
            r"^line\s+(vty|con|aux|tty)\s*\S*",
            r"^vlan\s+\d[\d,\-]*",
            r"^route-map\s+\S+",
            r"^policy-map\s+\S+",
            r"^class-map\s+\S+",
            r"^crypto\s+(isakmp|ipsec|map|keyring|pki)\s+\S+",
            r"^ip\s+dhcp\s+pool\s+\S+",
            r"^ip\s+(access-list|prefix-list)\s+\S+",
            r"^ipv6\s+(access-list|prefix-list)\s+\S+",
            r"^mac\s+access-list\s+\S+",
            r"^mpls\s+ldp",
            r"^segment-routing",
            r"^template\s+\S+",
            r"^parameter-map\s+\S+",
            r"^ip\s+sla\s+\d+",
            r"^track\s+\d+",
            r"^event\s+manager\s+applet\s+\S+",
            r"^voice\s+(service|class|register|translation)\s+\S*",
            r"^dial-peer\s+\S+",
            r"^stacking",
        ],
        "global_config_keywords": [
            "ip route", "ipv6 route", "ip routing", "ipv6 unicast-routing",
            "no ip", "no ipv6", "access-list", "ip access-list",
            "vlan", "hostname", "spanning-tree", "ntp", "snmp-server",
            "logging", "username", "service", "aaa", "banner",
            "enable", "boot", "archive", "alias", "ip domain",
            "ip name-server", "ip default-gateway", "ip ssh",
            "ip http", "ip ftp", "ip tftp", "ip flow",
            "lldp", "cdp", "errdisable", "mls", "monitor session",
            "storm-control", "port-security", "dot1x", "radius-server",
            "tacacs-server", "key chain", "object-group", "zone-pair",
            "zone security", "flow record", "flow monitor", "flow exporter",
            "netflow", "sampler", "traffic-shape", "clock timezone",
            "redundancy", "mode sso", "mode rpr",
        ],
    },

    Vendor.HUAWEI: {
        "config_enter":    {"system-view"},
        "config_exit":     {"return"},
        "submode_exit":    {"quit"},
        "save":            {"save"},
        "reload":          {"reboot"},
        "confirm_cmds":    [r"^reboot", r"^reset\s+saved"],
        "show_prefixes":   ["display", "ping", "tracert", "debugging",
                            "undo debugging", "test-aaa"],
        "submode_patterns": [
            r"^interface\s+\S+",
            r"^bgp\s+\d+",
            r"^ospf\s+\d*",
            r"^isis\s+\d*",
            r"^rip\s*\d*",
            r"^vlan\s+\d+",
            r"^vlan\s+batch",
            r"^acl\s+\S+",
            r"^route-policy\s+\S+",
            r"^traffic\s+(classifier|behavior|policy)\s+\S+",
            r"^user-interface\s+\S+",
            r"^aaa",
        ],
        "global_config_keywords": [
            "ip route-static", "ipv6 route-static", "ntp-service",
            "snmp-agent", "info-center", "local-user", "stelnet",
            "sysname", "clock",
        ],
    },

    Vendor.HP_COMWARE: {
        "config_enter":    {"system-view"},
        "config_exit":     {"return"},
        "submode_exit":    {"quit"},
        "save":            {"save"},
        "reload":          {"reboot"},
        "confirm_cmds":    [r"^reboot"],
        "show_prefixes":   ["display", "ping", "tracert"],
        "submode_patterns": [
            r"^interface\s+\S+",
            r"^ospf\s+\d*",
            r"^bgp\s+\d+",
            r"^vlan\s+\d+",
            r"^acl\s+(number|name)\s+\S+",
        ],
        "global_config_keywords": ["ip route-static", "sysname"],
    },

    Vendor.HP_PROCURVE: {
        "config_enter":    {"conf", "configure"},
        "config_exit":     {"end"},
        "submode_exit":    {"exit"},
        "save":            {"write memory"},
        "reload":          {"reload", "boot"},
        "confirm_cmds":    [r"^reload", r"^boot"],
        "show_prefixes":   ["show", "ping", "traceroute", "walkMIB"],
        "submode_patterns": [
            r"^vlan\s+\d+",
            r"^interface\s+\S+",
        ],
        "global_config_keywords": ["hostname", "ip route", "snmp-server", "aaa"],
    },

    Vendor.FORTINET: {
        "config_enter":    {"config "},
        "config_exit":     {"end"},
        "submode_exit":    {"next", "abort"},
        "save":            {"execute backup config"},
        "reload":          {"execute reboot"},
        "confirm_cmds":    [r"^execute\s+reboot", r"^execute\s+factoryreset"],
        "show_prefixes":   ["show", "get", "diagnose", "execute ping",
                            "execute traceroute"],
        "submode_patterns": [
            r"^config\s+(system|firewall|router|vpn|user|log|wad)\s+\S*",
            r"^edit\s+\S+",
        ],
        "global_config_keywords": ["set ", "unset ", "append "],
    },

    Vendor.PALOALTO: {
        "config_enter":    {"configure"},
        "config_exit":     {"exit"},
        "submode_exit":    {"up"},
        "save":            {"commit", "commit force"},
        "reload":          {"request restart system"},
        "confirm_cmds":    [r"^request\s+restart"],
        "show_prefixes":   ["show", "run", "debug", "test",
                            "request", "set cli"],
        "submode_patterns": [
            r"^edit\s+\S+",
            r"^set\s+(deviceconfig|network|vsys|shared)\s+",
        ],
        "global_config_keywords": ["set ", "delete ", "move ", "rename "],
    },

    Vendor.DELL_OS10: {
        "config_enter":    {"configure terminal", "conf t"},
        "config_exit":     {"end"},
        "submode_exit":    {"exit"},
        "save":            {"write memory", "copy running-configuration startup-configuration"},
        "reload":          {"reload"},
        "confirm_cmds":    [r"^reload", r"^write\s+erase", r"^restore\s+factory-default"],
        "show_prefixes":   ["show", "ping", "traceroute", "find"],
        "submode_patterns": [
            r"^interface\s+\S+",
            r"^router\s+(bgp|ospf|isis)\s*\S*",
            r"^route-map\s+\S+",
        ],
        "global_config_keywords": ["hostname", "ip route", "ntp server", "snmp-server", "username", "banner"],
    },

    Vendor.ALCATEL_AOS: {
        "config_enter":    set(),  # AOS usually accepts config commands directly or via specific contexts
        "config_exit":     {"end", "exit"},
        "submode_exit":    {"exit"},
        "save":            {"write memory", "copy running-config working", "copy running-config certified"},
        "reload":          {"reload"},
        "confirm_cmds":    [r"^reload"],
        "show_prefixes":   ["show", "ping", "traceroute", "display"],
        "submode_patterns": [r"^interface", r"^vlan", r"^ip"],
        "global_config_keywords": ["ip static-route", "system name", "aaa authentication", "user"],
    },
}

# Fallback for GENERIC vendor
_VENDOR_PROFILES[Vendor.GENERIC] = _VENDOR_PROFILES[Vendor.CISCO_IOS].copy()


class CommandClassifier:
    def __init__(self, vendor: Vendor = Vendor.CISCO_IOS):
        self.vendor = vendor
        self.profile = _VENDOR_PROFILES.get(vendor, _VENDOR_PROFILES[Vendor.GENERIC])

    def classify(self, raw_cmd: str) -> ParsedCommand:
        s = raw_cmd.strip()
        low = s.lower()

        if not s:
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.EMPTY,
                                 strategy=SendStrategy.SEND_COMMAND)

        if s.startswith("!") or s.startswith("#"):
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.COMMENT,
                                 strategy=SendStrategy.SEND_COMMAND)

        p = self.profile

        # --- config enter ---
        if low in p.get("config_enter", set()):
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.CONFIG,
                                 strategy=SendStrategy.SEND_CONFIG_SET,
                                 notes="global config entry — handled by netmiko")

        # --- hard end (returns to exec) ---
        if low in p.get("config_exit", set()):
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.CONFIG_END,
                                 strategy=SendStrategy.SEND_COMMAND,
                                 notes="exits config mode entirely")

        # --- sub-mode exit (one level up) ---
        if low in p.get("submode_exit", set()):
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.SUBMODE_EXIT,
                                 strategy=SendStrategy.SEND_CONFIG_SET,
                                 notes="exits one sub-mode level")

        # --- save ---
        if low in p.get("save", set()):
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.SPECIAL_SAVE,
                                 strategy=SendStrategy.SEND_COMMAND_TIMING,
                                 notes="save / commit — may take time")

        # --- reload ---
        if any(re.match(rf"^{kw}", low) for kw in p.get("reload", set())):
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.SPECIAL_RELOAD,
                                 strategy=SendStrategy.MANUAL_CONFIRM,
                                 requires_confirm=True,
                                 confirm_pattern=r"[Cc]onfirm|[Yy]es|proceed",
                                 notes="reload — manual confirmation required")

        # --- show / read-only ---
        show_prefixes = p.get("show_prefixes", [])
        if any(low == pfx or low.startswith(pfx + " ") for pfx in show_prefixes):
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.SHOW,
                                 strategy=SendStrategy.SEND_COMMAND)

        # --- interactive confirmation commands ---
        for pat in p.get("confirm_cmds", []):
            if re.match(pat, low):
                return ParsedCommand(raw=raw_cmd, normalized=s,
                                     cmd_type=CmdType.INTERACTIVE,
                                     strategy=SendStrategy.SEND_COMMAND_TIMING,
                                     requires_confirm=True,
                                     confirm_pattern=r"[Cc]onfirm|[Yy]es|proceed|\[y/n\]",
                                     notes="requires interactive confirmation")

        # --- sub-mode entry ---
        for pat in p.get("submode_patterns", []):
            if re.match(pat, low):
                return ParsedCommand(raw=raw_cmd, normalized=s,
                                     cmd_type=CmdType.SUBMODE_ENTER,
                                     strategy=SendStrategy.SEND_CONFIG_SET,
                                     submode_context=s)

        # --- global config keywords ---
        for kw in p.get("global_config_keywords", []):
            if low.startswith(kw.lower()):
                return ParsedCommand(raw=raw_cmd, normalized=s,
                                     cmd_type=CmdType.CONFIG,
                                     strategy=SendStrategy.SEND_CONFIG_SET)

        # --- Juniper / PAN-OS / Fortinet: 'set' prefix is always config ---
        if self.vendor in (Vendor.JUNIPER, Vendor.PALOALTO, Vendor.FORTINET,
                           ) and low.startswith("set "):
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.CONFIG,
                                 strategy=SendStrategy.SEND_CONFIG_SET)

        # --- Huawei / HP Comware: fall into config if in system-view ---
        # (handled upstream by parser context, but flag as config anyway)
        if self.vendor in (Vendor.HUAWEI, Vendor.HP_COMWARE):
            return ParsedCommand(raw=raw_cmd, normalized=s,
                                 cmd_type=CmdType.CONFIG,
                                 strategy=SendStrategy.SEND_CONFIG_SET)

        # --- default: treat as exec ---
        return ParsedCommand(raw=raw_cmd, normalized=s,
                             cmd_type=CmdType.EXEC,
                             strategy=SendStrategy.SEND_COMMAND,
                             notes="unrecognized — sent as exec command")


class SmartConfigParser:
    def __init__(self, vendor: Vendor = Vendor.CISCO_IOS):
        self.vendor = vendor
        self.classifier = CommandClassifier(vendor)
        self._context_stack: list[str] = []  # stack of sub-mode contexts

    @property
    def current_context(self) -> str:
        return " > ".join(self._context_stack) if self._context_stack else "global"

    def parse(self, raw_text: str) -> list[ParsedCommand]:
        results: list[ParsedCommand] = []
        lines = raw_text.strip().splitlines()

        for raw_line in lines:
            cmd = self.classifier.classify(raw_line)
            cmd.submode_context = self.current_context

            # Update context stack
            if cmd.cmd_type == CmdType.SUBMODE_ENTER:
                self._context_stack.append(cmd.normalized)
            elif cmd.cmd_type == CmdType.SUBMODE_EXIT:
                if self._context_stack:
                    self._context_stack.pop()
            elif cmd.cmd_type in (CmdType.CONFIG_END,):
                self._context_stack.clear()

            results.append(cmd)

        return results

    def extract_config_lines(self, raw_text: str) -> list[str]:
        """
        Strip conf-t/end wrappers, comments, blanks.
        Returns clean lines safe for netmiko send_config_set().
        Preserves exit/quit for proper sub-mode nesting.
        """
        parsed = self.parse(raw_text)
        lines = []
        for cmd in parsed:
            if cmd.cmd_type in (CmdType.EMPTY, CmdType.COMMENT):
                continue
            if cmd.cmd_type == CmdType.CONFIG_END:
                continue  # netmiko adds 'end' itself
            # Strip bare config-enter triggers (netmiko handles conf t)
            if cmd.cmd_type == CmdType.CONFIG and cmd.normalized.lower() in \
               self.classifier.profile.get("config_enter", set()):
                continue
            lines.append(cmd.normalized)
        return lines


def parse_smart_config(raw_text: str, vendor: Vendor = Vendor.CISCO_IOS) -> list[str]:
    """Drop-in replacement for original parse_smart_config()."""
    return SmartConfigParser(vendor).extract_config_lines(raw_text)


def classify_command(cmd: str, vendor: Vendor = Vendor.CISCO_IOS) -> str:
    if not isinstance(vendor, Vendor):
        try:
            vendor = Vendor(vendor)
        except ValueError:
            vendor = Vendor.GENERIC
            
    result = CommandClassifier(vendor).classify(cmd)
    type_map = {
        CmdType.SHOW:          "show",
        CmdType.CONFIG:        "config",
        CmdType.EXEC:          "exec",
        CmdType.SPECIAL_SAVE:  "special_save",
        CmdType.SPECIAL_RELOAD: "special_reload",
        CmdType.INTERACTIVE:   "interactive",
        CmdType.SUBMODE_ENTER: "submode_enter",
        CmdType.SUBMODE_EXIT:  "submode_exit",
        CmdType.CONFIG_END:    "config_end",
        CmdType.COMMENT:       "comment",
        CmdType.EMPTY:         "empty",
    }
    return type_map.get(result.cmd_type, "exec")

# ───────────────────────────────────────────────
# SSH Interactive Worker
# ───────────────────────────────────────────────
class SSHWorker(QThread):
    out = pyqtSignal(str)
    refresh = pyqtSignal()
    progress = pyqtSignal(int, int)
    log_entry = pyqtSignal(str, str, str)

    def __init__(self, indexes, command_block, timeout=60):
        super().__init__()
        self.indexes = list(indexes)
        self.command_block = command_block.strip()
        self.timeout = timeout
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _emit(self, text):
        self.out.emit(text)

    def run(self):
        total = len(self.indexes)
        for n, idx in enumerate(self.indexes):
            if self._stop_flag:
                self._emit("[ABORTED] Execution stopped by user.")
                break

            self.progress.emit(n + 1, total)
            device = devices[idx]
            name = device.get("hostname") or device["host"]
            
            # Session key for persistence
            sess_key = f"{device['host']}:{device.get('port', 22)}:{device.get('username','')}"

            self._emit(
                f"\n{'─'*64}\n"
                f"  ▸ {name}  [{device['host']}:{device.get('port',22)}]"
                f"  {datetime.now().strftime('%H:%M:%S')}\n"
                f"{'─'*64}"
            )

            try:
                from netmiko import ConnectHandler
                conn = None
                
                # Try to reuse existing session
                if sess_key in device_sessions:
                    c = device_sessions[sess_key]
                    # If the secret has changed, we must reconnect.
                    # Netmiko stores the secret in the 'secret' attribute of the connection object.
                    current_secret = device.get("secret", "")
                    session_secret = c.secret or ""

                    if c.is_alive() and current_secret == session_secret:
                        conn = c
                    else:
                        if current_secret != session_secret:
                            self._emit(f"  [INFO] Secret changed. Re-establishing connection.")
                        try:
                            if c.is_alive():
                                c.disconnect()
                        except: pass
                        del device_sessions[sess_key]

                if conn is None:
                    # Build clean connection params (no internal keys)
                    conn_params = {k: v for k, v in device.items()
                                   if k not in ("hostname", "connected", "tags", "notes")}

                    # Fix: Increase timeouts to prevent TCP connection failures
                    conn_params["conn_timeout"] = 60
                    conn_params["banner_timeout"] = 60
                    conn_params["auth_timeout"] = 60
                    # Performance optimization
                    conn_params["fast_cli"] = True

                    # Remove empty secret so netmiko doesn't fail
                    if not conn_params.get("secret"):
                        conn_params.pop("secret", None)

                    # Retry mechanism for robust connections
                    for attempt in range(3):
                        try:
                            conn = ConnectHandler(**conn_params)
                            break
                        except Exception as e:
                            if attempt == 2:
                                raise e
                            self._emit(f"  [RETRY] Connection failed, retrying ({attempt+1}/3)...")
                            time.sleep(1.5)
                    
                    device_sessions[sess_key] = conn

                # Determine device type behavior (Non-Cisco = Shell Mode)
                dtype = device.get("device_type", "").lower()
                is_cisco = "cisco" in dtype
                use_shell = not is_cisco
                is_linux = "linux" in dtype
                
                # Attempt to enter enable mode if a secret is provided for Cisco devices
                if is_cisco and device.get("secret"):
                    if not conn.check_enable_mode():
                        self._emit("  [INFO] Attempting to enter enable mode...")
                        try:
                            # The enable() call will use the 'secret' passed during ConnectHandler
                            conn.enable()
                            # If successful, re-establish the base prompt
                            conn.set_base_prompt()
                            self._emit("  [INFO] Successfully entered enable mode.")
                        except Exception as e:
                            # This will catch wrong secrets, timeouts, etc.
                            self._emit(f"  [ERROR] Failed to enter enable mode: {str(e)}")
                            raise  # Re-raise to fail this device and move to the next

                # Fix: Enable ANSI stripping for shell devices to handle colored prompts reliably
                if use_shell:
                    conn.ansi_escape_codes = True

                # Add a hint if we're not in enable mode on a Cisco device
                if is_cisco and not conn.check_enable_mode():
                    self._emit(f"  [INFO] Connected in user mode. Privileged commands may fail. (Hint: add enable secret)")

                # Grab real hostname
                real_hostname = None

                # 1. Try 'hostname' command for Linux (most reliable for Kali/Ubuntu/etc)
                if is_linux:
                    try:
                        conn.write_channel("hostname\n")
                        time.sleep(0.5)
                        output = conn.read_channel()
                        # Clean output: remove command echo, remove prompt chars
                        for line in output.splitlines():
                            line = line.strip()
                            # Skip echo and prompt lines
                            if "hostname" in line or any(c in line for c in "#$%>"):
                                continue
                            if line:
                                real_hostname = line
                                break
                    except:
                        pass

                # 2. Fallback: Extract from prompt (tolerant of failures)
                if not real_hostname:
                    try:
                        prompt = conn.find_prompt()
                        ansi_escape = re.compile(r'\x1B(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1B]*(\x07|\x1B\\)|[@-Z\\-_])')
                        clean_prompt = ansi_escape.sub('', prompt)
                        
                        # Enforce ASCII printable only (removes Kali symbols/Arabic)
                        clean_prompt = "".join(c for c in clean_prompt if c.isprintable() and ord(c) < 128)
                        
                        real_hostname = re.sub(r"[#>\$\s]+$", "", clean_prompt).strip()
                    except:
                        pass

                if real_hostname:
                    devices[idx]["hostname"] = real_hostname

                # ── Smart command classification ───────────────────
                dtype_str = device.get("device_type", "cisco_ios")
                try:
                    vendor = Vendor(dtype_str)
                except ValueError:
                    vendor = Vendor.GENERIC

                parser = SmartConfigParser(vendor)
                parsed_cmds = parser.parse(self.command_block)
                cleaned_lines = parser.extract_config_lines(self.command_block)
                
                first_norm = cleaned_lines[0] if cleaned_lines else ""
                kind = classify_command(first_norm, vendor)

                is_config = (
                    any(c.cmd_type == CmdType.CONFIG for c in parsed_cmds)
                    or any(c.strategy == SendStrategy.SEND_CONFIG_SET for c in parsed_cmds)
                    or (len(cleaned_lines) > 1 and not use_shell)
                )
                
                # Override config detection for shell devices to avoid "configure terminal" attempts
                if use_shell:
                    is_config = False

                # ── Execute ────────────────────────────────────────
                if is_config:
                    if not cleaned_lines:
                        self._emit("  [WARN] No config lines to send.")
                    else:
                        self._emit(
                            f"  [CONFIG MODE]  {len(cleaned_lines)} line(s):\n"
                            + "\n".join(f"    {l}" for l in cleaned_lines)
                        )
                        output = conn.send_config_set(
                            cleaned_lines,
                            read_timeout=self.timeout,
                            cmd_verify=True,
                            strip_prompt=False,
                            strip_command=False,
                        )
                        self._emit(output)
                elif kind == "special_save":
                    if is_cisco:
                        conn.save_config()
                        self._emit("  [OK] Configuration saved to startup-config.")
                    else:
                        self._emit("  [WARN] Save skipped (Shell Mode).")

                elif kind == "special_reload":
                    self._emit("  [WARN] Reload skipped — confirm manually on device.")

                else:
                    # Exec / show command — send each line separately if multiple
                    for cmd_line in cleaned_lines:
                        # Handle interactive '?' to get help output
                        if not use_shell and cmd_line.strip().endswith('?'):
                            output = conn.send_command_timing(
                                cmd_line,
                                read_timeout=self.timeout,
                            )
                            # Clean up the output which often includes the command echo and the prompt
                            lines = output.splitlines()
                            if lines and cmd_line.strip() in lines[0]:
                                lines.pop(0)
                            if lines and lines[-1].strip().endswith(cmd_line.strip()):
                                lines.pop(-1)
                            output = "\n".join(lines).strip()
                        elif use_shell:
                            # Use raw channel I/O to simulate a real shell
                            conn.write_channel(cmd_line + '\n')
                            time.sleep(1.0) # Wait for output

                            raw_output = ""
                            if conn.is_alive():
                                raw_output = conn.read_channel()

                            # --- Clean the raw output ---
                            # Enhanced cleaning: ANSI CSI, OSC (titles/shell integration), and Backspaces
                            ansi_escape = re.compile(r'\x1B(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1B]*(\x07|\x1B\\)|[@-Z\\-_])')
                            clean_output = ansi_escape.sub('', raw_output)
                            
                            # Handle backspaces
                            chars = []
                            for c in clean_output:
                                if c == '\x08':
                                    if chars: chars.pop()
                                else:
                                    chars.append(c)
                            clean_output = "".join(chars)

                            lines = clean_output.splitlines()
                            
                            # Remove command echo if present
                            if lines and cmd_line.strip() in lines[0]: lines.pop(0)
                                
                            output = "\n".join(lines).strip()
                            if not output:
                                output = "  [✓] Command executed."
                            else:
                                output = "\n".join(f"  {line}" for line in output.splitlines())
                        else:
                            output = conn.send_command(
                                cmd_line,
                                read_timeout=self.timeout,
                                strip_prompt=True,
                                strip_command=True,
                            )
                        self._emit(output or "  (no output)")

                devices[idx]["connected"] = True
                self.log_entry.emit(name, self.command_block, "OK")
                # conn.disconnect()  <-- Keep session alive

            except Exception as e:
                # Invalidate session on error
                if sess_key in device_sessions:
                    try: device_sessions[sess_key].disconnect()
                    except: pass
                    del device_sessions[sess_key]
                    
                devices[idx]["connected"] = False
                self._emit(f"  [ERROR] {type(e).__name__}: {e}")
                self.log_entry.emit(name, self.command_block, str(e))

        self.refresh.emit()


# ───────────────────────────────────────────────
# Ping Worker
# ───────────────────────────────────────────────
class PingWorker(QThread):
    result = pyqtSignal(int, bool, float)

    def __init__(self, indexes):
        super().__init__()
        self.indexes = indexes

    def run(self):
        param = "-n" if platform.system().lower() == "windows" else "-c"
        for idx in self.indexes:
            host = devices[idx]["host"]
            try:
                t0 = time.time()
                r = subprocess.run(["ping", param, "1", host],
                                   capture_output=True, text=True, timeout=5)
                rtt = (time.time() - t0) * 1000
                alive = r.returncode == 0

                # Extra check: Windows ping returns 0 for "Destination host unreachable"
                if alive and ("unreachable" in r.stdout.lower() or "timed out" in r.stdout.lower()):
                    alive = False

            except Exception:
                alive, rtt = False, 0.0
            devices[idx]["connected"] = alive
            self.result.emit(idx, alive, rtt)


# ───────────────────────────────────────────────
# Config Share Worker
# ───────────────────────────────────────────────
class ConfigShareWorker(QThread):
    out = pyqtSignal(str)
    done = pyqtSignal(str)   # emits the pulled config text when pull is complete

    def __init__(self, mode, src_idx=None, dst_indexes=None, config_text=None, timeout=60):
        super().__init__()
        self.mode = mode              # "pull" | "push" | "pull_and_push"
        self.src_idx = src_idx
        self.dst_indexes = dst_indexes or []
        self.config_text = config_text or ""
        self.timeout = timeout

    def _connect(self, idx):
        from netmiko import ConnectHandler
        d = devices[idx]
        params = {k: v for k, v in d.items()
                  if k not in ("hostname", "connected", "tags", "notes")}
        
        # Fix: Increase timeouts
        params["conn_timeout"] = 60
        params["banner_timeout"] = 60
        params["auth_timeout"] = 60

        if not params.get("secret"):
            params.pop("secret", None)
        return ConnectHandler(**params)

    def _device_name(self, idx):
        d = devices[idx]
        return d.get("hostname") or d["host"]

    def run(self):
        from netmiko import ConnectHandler

        pulled_config = self.config_text

        # ── PULL ──────────────────────────────────────────
        if self.mode in ("pull", "pull_and_push") and self.src_idx is not None:
            src_name = self._device_name(self.src_idx)
            self.out.emit(f"\n[PULL] Connecting to {src_name}...")
            try:
                conn = self._connect(self.src_idx)
                raw = conn.send_command("show running-config", read_timeout=60)
                conn.disconnect()

                pulled_config = raw
                self.out.emit(
                    f"[PULL] Got full running-config from {src_name}  "
                    f"— {len(pulled_config.splitlines())} lines"
                )

                devices[self.src_idx]["connected"] = True
                self.done.emit(pulled_config)

            except Exception as e:
                self.out.emit(f"[ERROR] Pull from {src_name} failed: {e}")
                return

        # ── PUSH ──────────────────────────────────────────
        if self.mode in ("push", "pull_and_push") and self.dst_indexes and pulled_config:
            # Parse config into sendable lines
            config_lines = []
            for line in pulled_config.splitlines():
                s = line.strip()
                if not s or s.startswith("!") or s.startswith("#"):
                    continue
                if s.lower() in ("end", "exit"):
                    continue
                if s.lower().startswith(("building configuration",
                                          "current configuration",
                                          "version ", "boot ", "service ")):
                    continue
                config_lines.append(s)

            if not config_lines:
                self.out.emit("[WARN] No pushable lines found in config.")
                return

            self.out.emit(
                f"\n[PUSH] Pushing {len(config_lines)} config lines "
                f"to {len(self.dst_indexes)} device(s)..."
            )

            for idx in self.dst_indexes:
                name = self._device_name(idx)
                self.out.emit(f"\n  ▸ Pushing to {name} ({devices[idx]['host']})...")
                try:
                    conn = self._connect(idx)
                    
                    # Dynamic timeout for large configs
                    push_timeout = max(self.timeout, len(config_lines) * 3.0)
                    output = conn.send_config_set(
                        config_lines,
                        read_timeout=push_timeout,
                        cmd_verify=True,
                        strip_prompt=False,
                        strip_command=False,
                    )
                    conn.save_config()
                    conn.disconnect()
                    devices[idx]["connected"] = True
                    self.out.emit(f"  [OK] {name} — config applied and saved.")
                except Exception as e:
                    devices[idx]["connected"] = False
                    self.out.emit(f"  [ERROR] {name} — {e}")


# ───────────────────────────────────────────────
# Auto Complete Worker (Dynamic)
# ───────────────────────────────────────────────
class AutoCompleteWorker(QThread):
    results_ready = pyqtSignal(list)

    def __init__(self, device_idx, partial_cmd):
        super().__init__()
        self.device_idx = device_idx
        self.partial_cmd = partial_cmd

    def run(self):
        try:
            device = devices[self.device_idx]
            sess_key = f"{device['host']}:{device.get('port', 22)}:{device.get('username','')}"
            
            conn = device_sessions.get(sess_key)
            if not conn or not conn.is_alive():
                return

            # Check device type for Linux vs Cisco
            dtype = device.get("device_type", "cisco_ios").lower()
            is_cisco = "cisco" in dtype
            use_shell = not is_cisco

            if use_shell:
                # Shell Mode: Send Tab (twice to be sure to list options)
                conn.write_channel(self.partial_cmd + "\t\t")
                time.sleep(0.5)
                output = conn.read_channel()
                # Cancel current line to clean up
                conn.write_channel("\x03") 
            else:
                # Cisco/Network
                conn.write_channel(self.partial_cmd + "?")
                time.sleep(0.1) # Faster response
                output = conn.read_channel()
                # Clean up the buffer (Ctrl+U to clear line)
                conn.write_channel("\x15") 

            # Parse output
            lines = output.splitlines()
            completions = []
            for line in lines:
                line = line.strip()
                # Filter out the command echo and prompt
                if self.partial_cmd in line or "?" in line or "\t" in line: continue
                if any(x in line for x in ["#", ">", "$", "@"]): continue

                # Grab the first word if it looks like a command
                parts = line.split()
                if parts:
                    cmd = parts[0]
                    # Basic filtering to ensure it looks like a command
                    if len(cmd) > 1 and re.match(r"^[a-zA-Z0-9-]+$", cmd):
                        completions.append(cmd)
            
            self.results_ready.emit(sorted(list(set(completions))))
        except:
            pass

# ───────────────────────────────────────────────
# File Editor Worker & Dialog
# ───────────────────────────────────────────────
class FileEditorWorker(QThread):
    content_read = pyqtSignal(str)
    write_done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, device_idx, filepath, mode="read", content=""):
        super().__init__()
        self.device_idx = device_idx
        self.filepath = filepath
        self.mode = mode
        self.content = content

    def run(self):
        import random
        import string
        device = devices[self.device_idx]
        sess_key = f"{device['host']}:{device.get('port', 22)}:{device.get('username','')}"
        
        try:
            from netmiko import ConnectHandler
            conn = device_sessions.get(sess_key)
            
            if not conn or not conn.is_alive():
                params = {k: v for k, v in device.items() 
                          if k not in ("hostname", "connected", "tags", "notes")}
                params["conn_timeout"] = 60
                params["banner_timeout"] = 60
                params["auth_timeout"] = 60
                if not params.get("secret"): params.pop("secret", None)
                conn = ConnectHandler(**params)
                device_sessions[sess_key] = conn

            if self.mode == "read":
                out = conn.send_command(f"cat {self.filepath}", read_timeout=30)
                if "No such file" in out or "Permission denied" in out:
                    self.error.emit(out)
                else:
                    self.content_read.emit(out)

            elif self.mode == "write":
                delim = "EOF_" + "".join(random.choices(string.ascii_letters + string.digits, k=12))
                cmd = f"cat > {self.filepath} << '{delim}'\n{self.content}\n{delim}"
                out = conn.send_command(cmd, read_timeout=60)
                if "Permission denied" in out:
                    self.error.emit(out)
                else:
                    self.write_done.emit()

        except Exception as e:
            self.error.emit(str(e))


class RemoteFileEditor(QDialog):
    def __init__(self, device_idx, filepath, parent=None):
        super().__init__(parent)
        self.device_idx = device_idx
        self.filepath = filepath
        self.setWindowTitle(f"Remote Editor: {filepath}")
        self.resize(900, 700)
        c = THEMES[current_theme]
        self.setStyleSheet(f"""
            QDialog {{ background: {c['bg']}; color: {c['fg']}; }}
            QTextEdit {{ background: {c['input']}; color: {c['console_text']}; border: 1px solid {c['border']}; font-family: Consolas; font-size: 12px; }}
            QLabel {{ color: {c['button_text']}; }}
            QPushButton {{ background: {c['button']}; color: {c['button_text']}; border: 1px solid {c['border']}; padding: 6px 12px; border-radius: 4px; }}
            QPushButton:hover {{ background: {c['button_hover']}; color: {c['accent']}; border-color: {c['accent']}; }}
        """)
        
        layout = QVBoxLayout(self)
        self.editor = QTextEdit()
        layout.addWidget(self.editor)
        
        btns = QHBoxLayout()
        self.status_lbl = QLabel("Initializing...")
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self.save)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        
        btns.addWidget(self.status_lbl)
        btns.addStretch()
        btns.addWidget(save_btn)
        btns.addWidget(close_btn)
        layout.addLayout(btns)
        
        self.load()

    def load(self):
        self.editor.setDisabled(True)
        self.status_lbl.setText(f"Pulling {self.filepath}...")
        self.worker = FileEditorWorker(self.device_idx, self.filepath, "read")
        self.worker.content_read.connect(self.on_read)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(lambda: self.editor.setDisabled(False))
        self.worker.start()

    def save(self):
        self.editor.setDisabled(True)
        self.status_lbl.setText(f"Saving {self.filepath}...")
        content = self.editor.toPlainText()
        self.worker = FileEditorWorker(self.device_idx, self.filepath, "write", content)
        self.worker.write_done.connect(self.on_saved)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(lambda: self.editor.setDisabled(False))
        self.worker.start()

    def on_read(self, content):
        self.editor.setPlainText(content)
        self.status_lbl.setText("File loaded.")

    def on_saved(self):
        self.status_lbl.setText("File saved successfully.")
        QMessageBox.information(self, "Success", "File saved to remote device.")

    def on_error(self, msg):
        self.status_lbl.setText("Error occurred.")
        QMessageBox.critical(self, "Error", msg)

# ───────────────────────────────────────────────
# Config Share Dialog
# ───────────────────────────────────────────────
class ConfigShareDialog(QDialog):
    def __init__(self, parent=None, console_cb=None):
        super().__init__(parent)
        self.console_cb = console_cb  # callback to write to main console
        self._pulled_config = ""
        self._worker = None

        self.setWindowTitle("Config Share")
        self.setMinimumSize(900, 640)
        c = THEMES[current_theme]
        self.setStyleSheet(f"""
            QDialog {{ background: {c['bg']}; color: {c['fg']}; }}
            QLabel {{ color: {c['button_text']}; font-size: 11px; }}
            QLabel#hdr {{ color: {c['accent']}; font-size: 13px; font-weight: bold;
                         font-family: Consolas; letter-spacing: 2px; }}
            QGroupBox {{ border: 1px solid {c['border']}; border-radius: 5px;
                        margin-top: 14px; color: {c['meta']}; font-size: 10px;
                        font-family: Consolas; letter-spacing: 1px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
            QListWidget {{ background: {c['input']}; border: 1px solid {c['border']};
                          color: {c['fg']}; border-radius: 4px; }}
            QListWidget::item {{ padding: 6px 10px; }}
            QListWidget::item:selected {{ background: {c['highlight']}; color: {c['accent']}; }}
            QTextEdit {{ background: {c['console']}; color: {c['console_text']}; border: 1px solid {c['border']};
                        font-family: "Cascadia Code","Consolas",monospace; font-size: 11px;
                        border-radius: 4px; padding: 6px; }}
            QLineEdit {{ background: {c['input']}; border: 1px solid {c['border']}; color: {c['input_text']};
                        padding: 6px 10px; border-radius: 4px; font-family: Consolas; }}
            QLineEdit:focus {{ border-color: {c['accent']}; }}
            QPushButton {{ background: {c['button']}; color: {c['button_text']}; border: 1px solid {c['border']};
                          padding: 7px 16px; border-radius: 4px; }}
            QPushButton:hover {{ background: {c['button_hover']}; color: {c['accent']}; border-color: {c['accent']}; }}
            QPushButton#primary {{ background: {c['highlight']}; color: {c['accent']}; border-color: {c['accent']};
                                  font-weight: bold; }}
            QPushButton#primary:hover {{ background: {c['accent']}; color: #000; }}
            QPushButton#danger {{ color: {c['error']}; border-color: {c['error']}; }}
            QPushButton#danger:hover {{ background: {c['error']}; color: #fff; }}
        """)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        hdr = QLabel("⟳  CONFIG SHARE")
        hdr.setObjectName("hdr")
        root.addWidget(hdr)

        subtitle = QLabel(
            " "
        )
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # ── Main splitter ──────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT: source + destination
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.setSpacing(8)

        # Source
        src_grp = QGroupBox(" SOURCE DEVICE ")
        sv = QVBoxLayout(src_grp)
        self._src_list = QListWidget()
        self._src_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._src_list.setMaximumHeight(160)
        sv.addWidget(self._src_list)

        pull_btn = QPushButton("⬇  Pull Config ")
        pull_btn.setObjectName("primary")
        pull_btn.clicked.connect(self._pull)
        sv.addWidget(pull_btn)
        lv.addWidget(src_grp)

        # Destination
        dst_grp = QGroupBox(" TARGET DEVICES ")
        dv = QVBoxLayout(dst_grp)
        self._dst_list = QListWidget()
        self._dst_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        dv.addWidget(self._dst_list, 1)

        dst_btns = QHBoxLayout()
        sel_all = QPushButton("Select All")
        sel_all.clicked.connect(self._dst_list.selectAll)
        clr_sel = QPushButton("Clear")
        clr_sel.clicked.connect(self._dst_list.clearSelection)
        dst_btns.addWidget(sel_all)
        dst_btns.addWidget(clr_sel)
        dv.addLayout(dst_btns)

        push_btn = QPushButton("⬆  Push Config ")
        push_btn.setObjectName("primary")
        push_btn.clicked.connect(self._push)
        dv.addWidget(push_btn)
        lv.addWidget(dst_grp, 1)

        splitter.addWidget(left)

        # RIGHT: config preview / editor
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.setSpacing(6)

        prev_hdr = QHBoxLayout()
        prev_lbl = QLabel("CONFIG PREVIEW ")
        prev_lbl.setStyleSheet(f"color:{c['meta']}; font-size:10px; font-family:Consolas; letter-spacing:1px;")
        prev_hdr.addWidget(prev_lbl)
        prev_hdr.addStretch()
        self._line_count = QLabel("0 lines")
        self._line_count.setStyleSheet(f"color:{c['highlight']}; font-size:10px; font-family:Consolas;")
        prev_hdr.addWidget(self._line_count)
        clr_btn = QPushButton("✕ Clear")
        clr_btn.setFixedHeight(24)
        clr_btn.setStyleSheet(f"QPushButton{{background:{c['button']};color:{c['meta']};border:1px solid {c['border']};padding:2px 8px;border-radius:3px;font-size:10px;}} QPushButton:hover{{color:{c['error']};}}")
        clr_btn.clicked.connect(self._preview.clear if hasattr(self, "_preview") else lambda: None)
        prev_hdr.addWidget(clr_btn)
        rv.addLayout(prev_hdr)

        self._preview = QTextEdit()
        self._preview.setPlaceholderText(
            "Config will appear here after pulling. (editable before push)\n"
            "You can edit it before pushing.\n\n"
            "Or paste config manually and push directly."
        )
        rv.addWidget(self._preview, 1)

        # Fix clear btn ref
        clr_btn.clicked.disconnect()
        clr_btn.clicked.connect(self._preview.clear)

        # Status
        self._status = QLabel("Ready — select a source and pull, or paste config manually.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color:{c['meta']}; font-size:10px; font-family:Consolas; padding:4px;")
        rv.addWidget(self._status)

        splitter.addWidget(right)
        splitter.setSizes([340, 560])
        root.addWidget(splitter, 1)

        # Connect preview text-changed → line count
        self._preview.textChanged.connect(self._update_line_count)

        self._populate_device_lists()

    def _populate_device_lists(self):
        self._src_list.clear()
        self._dst_list.clear()
        for d in devices:
            name = d.get("hostname") or d["host"]
            status = "●" if d.get("connected") else "○"
            label = f"  {status}  {name}  ({d['host']})"
            self._src_list.addItem(label)
            self._dst_list.addItem(label)

    def _update_line_count(self):
        n = len([l for l in self._preview.toPlainText().splitlines() if l.strip()])
        self._line_count.setText(f"{n} lines")

    def _pull(self):
        # convert items to indexes via QListWidget.row()
        rows = [self._src_list.row(i) for i in self._src_list.selectedItems()]
        if not rows:
            QMessageBox.warning(self, "No Source", "Select a source device.")
            return
        src_idx = rows[0]
        self._status.setText(f"Pulling config from {devices[src_idx].get('hostname') or devices[src_idx]['host']}...")

        w = ConfigShareWorker("pull", src_idx=src_idx)
        workers.append(w)
        w.out.connect(self._on_out)
        w.done.connect(self._on_pulled)
        w.finished.connect(lambda: workers.remove(w) if w in workers else None)
        w.start()

    def _on_pulled(self, config_text):
        self._pulled_config = config_text
        self._preview.setPlainText(config_text)
        self._status.setText("Config pulled. Review/edit above, then push to targets.")

    def _push(self):
        config_text = self._preview.toPlainText().strip()
        if not config_text:
            QMessageBox.warning(self, "No Config", "Pull or paste a config first.")
            return
        rows = [self._dst_list.row(i) for i in self._dst_list.selectedItems()]
        if not rows:
            QMessageBox.warning(self, "No Targets", "Select at least one target device.")
            return
        self._status.setText(f"Pushing config to {len(rows)} device(s)...")
        w = ConfigShareWorker("push", dst_indexes=rows, config_text=config_text)
        workers.append(w)
        w.out.connect(self._on_out)
        w.finished.connect(lambda: (
            workers.remove(w) if w in workers else None,
            self._status.setText("Push complete.")
        ))
        w.start()

    def _on_out(self, text):
        if self.console_cb:
            self.console_cb(text)
        self._status.setText(text[:120])


# ───────────────────────────────────────────────
# Console Syntax Highlighter
# ───────────────────────────────────────────────
class TermHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        c = THEMES[current_theme]
        self.rules = [
            (r"─{10,}", c['border'], False, False),
            (r"▸\s+\S+.*", c['accent'], True, False),
            (r"\[ERROR\].*|\bERROR\b.*", c['error'], True, False),
            (r"\[OK\].*|\bOK\b", c['success'], True, False),
            (r"\[WARN\].*|\bWARN\b.*", c['warn'], True, False),
            (r"\[CONFIG MODE\].*", "#bb88ff", False, False),
            (r"\b(\d{1,3}\.){3}\d{1,3}(/\d+)?\b", "#ff8c00", False, False),
            (r"\b([0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4}\b", "#dd88ff", False, False),
            (r"^(interface|vlan|router|line|hostname)\s+\S+", c['accent'], False, False),
            (r"^\s+(ip address|ip route|shutdown|no shutdown|description).*", "#c8a0ff", False, False),
            (r"GigabitEthernet\S*|FastEthernet\S*|Vlan\S*|Loopback\S*|Tunnel\S*", "#ffcc66", False, False),
            (r"\bup\b|\bUp\b|\bUP\b", c['success'], False, False),
            (r"\bdown\b|\bDown\b|\bDOWN\b", c['error'], False, False),
        ]

    def highlightBlock(self, text):
        for pattern, color, bold, italic in self.rules:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if bold:
                fmt.setFontWeight(QFont.Weight.Bold)
            if italic:
                fmt.setFontItalic(True)
            for m in re.finditer(pattern, text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ───────────────────────────────────────────────
# Device Card Widget
# ───────────────────────────────────────────────
class DeviceCard(QFrame):
    clicked = pyqtSignal(int)
    double_clicked = pyqtSignal(int)

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.selected = False
        self.setFixedHeight(62)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._build()
        self.refresh()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Status dot
        self.dot = QLabel("●")
        self.dot.setFixedWidth(14)
        self.dot.setFont(QFont("Arial", 9))
        layout.addWidget(self.dot)

        # Info
        info = QVBoxLayout()
        info.setSpacing(2)
        self.name_lbl = QLabel()
        self.name_lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self.meta_lbl = QLabel()
        self.meta_lbl.setFont(QFont("Consolas", 9))
        info.addWidget(self.name_lbl)
        info.addWidget(self.meta_lbl)
        layout.addLayout(info, 1)

        # Selection check
        self.check = QLabel("✓")
        self.check.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.check.setFixedWidth(20)
        self.check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.check)

    def refresh(self):
        d = devices[self.index]
        name = d.get("hostname") or d["host"]
        connected = d.get("connected", False)
        tags = "  ".join(f"#{t}" for t in d.get("tags", []))

        self.name_lbl.setText(name)
        self.meta_lbl.setText(f"{d['host']}:{d.get('port',22)}  {d.get('device_type','cisco_ios')}  {tags}")
        self.dot.setText("●")
        c = THEMES[current_theme]
        self.dot.setStyleSheet(f"color: {c['success'] if connected else c['error']};")
        self.meta_lbl.setStyleSheet(f"color: {c['meta']};")

        self._apply_style()

    def _apply_style(self):
        c = THEMES[current_theme]
        if self.selected:
            self.setStyleSheet(f"""
                DeviceCard {{
                    background: {c['selection']};
                    border: 1px solid {c['selection_border']};
                    border-radius: 6px;
                }}
            """)
            self.name_lbl.setStyleSheet(f"color: {c['accent']};")
            self.check.setStyleSheet(f"color: {c['accent']};")
            self.check.setVisible(True)
        else:
            self.setStyleSheet(f"""
                DeviceCard {{
                    background: {c['card_bg']};
                    border: 1px solid {c['border']};
                    border-radius: 6px;
                }}
                DeviceCard:hover {{
                    background: {c['card_hover']};
                    border-color: {c['highlight']};
                }}
            """)
            self.name_lbl.setStyleSheet(f"color: {c['fg']};")
            self.check.setStyleSheet("color: transparent;")

    def set_selected(self, val):
        self.selected = val
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.index)


# ───────────────────────────────────────────────
# Device Panel (scrollable cards)
# ───────────────────────────────────────────────
class DevicePanel(QScrollArea):
    selection_changed = pyqtSignal()
    edit_requested = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(4)
        self._layout.addStretch()
        self.setWidget(self._container)
        self._cards = {}  # index → DeviceCard

    def rebuild(self, filter_text=""):
        # Destroy old cards
        for card in list(self._cards.values()):
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        # Remove stretch
        if self._layout.count() > 0:
            item = self._layout.takeAt(self._layout.count() - 1)
            if item and item.widget(): item.widget().deleteLater()

        for idx, d in enumerate(devices):
            name = (d.get("hostname") or d["host"]).lower()
            ip = d["host"].lower()
            tags = " ".join(d.get("tags", [])).lower()
            if filter_text and filter_text.lower() not in name + ip + tags:
                continue

            card = DeviceCard(idx)
            card.selected = (idx in selected_indexes)
            card._apply_style()
            card.clicked.connect(self._on_click)
            card.double_clicked.connect(self.edit_requested)

            # Context menu
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(
                lambda pos, i=idx, c=card: self._context_menu(pos, i, c))

            self._layout.addWidget(card)
            self._cards[idx] = card

        self._layout.addStretch()

    def _on_click(self, idx):
        mods = QApplication.keyboardModifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            # Toggle
            if idx in selected_indexes:
                selected_indexes.discard(idx)
            else:
                selected_indexes.add(idx)
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            # Range select
            if selected_indexes:
                last = max(selected_indexes)
                lo, hi = min(idx, last), max(idx, last)
                for i in range(lo, hi + 1):
                    selected_indexes.add(i)
            else:
                selected_indexes.add(idx)
        else:
            # Single select — toggle if already only this one
            if selected_indexes == {idx}:
                # keep selected (don't deselect on single click)
                pass
            else:
                selected_indexes.clear()
                selected_indexes.add(idx)

        self._sync_visual()
        self.selection_changed.emit()

    def _sync_visual(self):
        for idx, card in self._cards.items():
            card.set_selected(idx in selected_indexes)

    def select_all(self):
        for idx in self._cards:
            selected_indexes.add(idx)
        self._sync_visual()
        self.selection_changed.emit()

    def deselect_all(self):
        selected_indexes.clear()
        self._sync_visual()
        self.selection_changed.emit()

    def _context_menu(self, pos, idx, card):
        d = devices[idx]
        name = d.get("hostname") or d["host"]
        c = THEMES[current_theme]
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background:{c['base']}; color:{c['fg']}; border:1px solid {c['border']}; padding:4px; }}
            QMenu::item {{ padding:6px 20px; }}
            QMenu::item:selected {{ background:{c['highlight']}; color:{c['accent']}; }}
            QMenu::separator {{ background:{c['border']}; height:1px; margin:4px 0; }}
        """)
        menu.addAction(f"Edit  {name}").triggered.connect(lambda: self.edit_requested.emit(idx))
        menu.addAction("Copy IP").triggered.connect(lambda: QApplication.clipboard().setText(d["host"]))
        menu.addSeparator()
        menu.addAction("Ping").triggered.connect(lambda: self._ping_one(idx))
        menu.exec(card.mapToGlobal(pos))

    def _ping_one(self, idx):
        # Emit to parent via a shared signal pattern — handled by main window
        self._ping_signal_idx = idx
        # Fallback: direct ping
        w = PingWorker([idx])
        workers.append(w)
        w.result.connect(lambda i, alive, rtt: self._on_ping(i, alive, rtt))
        w.finished.connect(lambda: workers.remove(w) if w in workers else None)
        w.start()

    def _on_ping(self, idx, alive, rtt):
        devices[idx]["connected"] = alive
        if idx in self._cards:
            self._cards[idx].refresh()

    def _quick(self, idx, cmd):
        # Signal main window — handled via global
        selected_indexes.clear()
        selected_indexes.add(idx)
        self._sync_visual()
        self.selection_changed.emit()
        # Store pending command
        self._pending_cmd = cmd

    def _edit_file(self, idx):
        path, ok = QInputDialog.getText(self, "Remote File", "Enter absolute path to file (e.g. /etc/hosts):")
        if ok and path:
            dlg = RemoteFileEditor(idx, path.strip(), self)
            dlg.exec()

    def _remove(self, idx):
        if 0 <= idx < len(devices):
            devices.pop(idx)
            selected_indexes.discard(idx)
            # Re-index selected_indexes
            new_sel = set()
            for s in selected_indexes:
                if s < idx:
                    new_sel.add(s)
                elif s > idx:
                    new_sel.add(s - 1)
            selected_indexes.clear()
            selected_indexes.update(new_sel)
            save_config()
            self.rebuild()
            self.selection_changed.emit()

    def refresh_cards(self):
        for idx, card in self._cards.items():
            card.refresh()
        self._sync_visual()


# ───────────────────────────────────────────────
# Multi-line Command Input
# ───────────────────────────────────────────────
class SmartInputBox(QTextEdit):
    send_requested = pyqtSignal(str)
    mode_changed = pyqtSignal(str)  # 'exec', 'config', 'show'
    dynamic_completion_requested = pyqtSignal(str) # Request help from device

    COMPLETIONS = []

    def __init__(self):
        super().__init__()
        self._in_config = False
        self._hist_pos = len(cmd_history)
        self._hist_draft = ""

        self.setFont(QFont("Cascadia Code", 12))
        self.setFixedHeight(48)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.update_theme()
        self.textChanged.connect(self._on_text_changed)
        
        # Setup Completer
        self.completer = QCompleter(self.COMPLETIONS, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self.insertCompletion)

    def update_theme(self):
        c = THEMES[current_theme]
        self.setStyleSheet(f"""
            SmartInputBox {{
                background: {c['console']};
                color: {c['input_text']};
                border: 2px solid {c['border']};
                border-radius: 6px;
                padding: 8px 12px;
                selection-background-color: {c['highlight']};
            }}
            SmartInputBox:focus {{
                border-color: {c['accent']};
            }}
        """)

    def insertCompletion(self, completion):
        if self.completer.widget() != self:
            return
        tc = self.textCursor()
        # Replace the current block (line) with the completion
        tc.select(QTextCursor.SelectionType.BlockUnderCursor)
        tc.insertText(completion)
        # Move cursor to end
        self.setTextCursor(tc)

    def _on_text_changed(self):
        text = self.toPlainText()
        lines = text.strip().splitlines()
        first = lines[0].strip() if lines else ""

        cmd_info = CommandClassifier(Vendor.CISCO_IOS).classify(first)
        old_in_config = self._in_config
        self._in_config = (
            cmd_info.cmd_type in (CmdType.CONFIG, CmdType.SUBMODE_ENTER)
            or len(lines) > 1
        )

        if self._in_config != old_in_config:
            if self._in_config:
                self.setFixedHeight(160)
                self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                self.mode_changed.emit("config")
            else:
                self.setFixedHeight(48)
                self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                cmd_type = classify_command(text)
                self.mode_changed.emit(cmd_type)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        text = self.toPlainText().strip()
        
        # ? triggers dynamic help
        if key == Qt.Key.Key_Question:
            self.dynamic_completion_requested.emit(self.textCursor().block().text())
            # We don't return here, we let the ? be typed or handled by the user preference

        # If completer popup is visible, let it handle navigation keys
        if self.completer.popup().isVisible():
            if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                event.ignore()
                return

        # Ctrl+Enter or Shift+Enter → always send
        if key == Qt.Key.Key_Return and (
            mods & Qt.KeyboardModifier.ControlModifier
            or mods & Qt.KeyboardModifier.ShiftModifier
        ):
            if text:
                self._send(text)
            return

        # Plain Enter
        if key == Qt.Key.Key_Return and not mods:
            if not self._in_config:
                # Single-line exec mode → send immediately
                if text:
                    self._send(text)
                return
            else:
                # Config mode → check if last line is 'end' or 'exit' to send
                lines = text.splitlines()
                last = lines[-1].strip().lower()
                if last in ("end", "exit", "quit", ""):
                    if text:
                        self._send(text)
                    return
                # Otherwise just add a newline
                super().keyPressEvent(event)
                return

        # Up arrow → history
        if key == Qt.Key.Key_Up:
            # In config mode, only trigger history if on the first line
            if not self._in_config or self.textCursor().blockNumber() == 0:
                if cmd_history:
                    if self._hist_pos == len(cmd_history):
                        self._hist_draft = self.toPlainText()
                    self._hist_pos = max(0, self._hist_pos - 1)
                    self.setPlainText(cmd_history[self._hist_pos])
                    self._move_cursor_end()
                return

        # Down arrow → history
        if key == Qt.Key.Key_Down:
            # In config mode, only trigger history if on the last line
            if not self._in_config or self.textCursor().blockNumber() == self.document().blockCount() - 1:
                if self._hist_pos < len(cmd_history) - 1:
                    self._hist_pos += 1
                    self.setPlainText(cmd_history[self._hist_pos])
                else:
                    self._hist_pos = len(cmd_history)
                    self.setPlainText(self._hist_draft)
                self._move_cursor_end()
                return

        # Tab → autocomplete
        if key == Qt.Key.Key_Tab:
            # Send current line to device for completion
            self.dynamic_completion_requested.emit(self.textCursor().block().text())
            return

        # Escape → clear
        if key == Qt.Key.Key_Escape:
            self.clear()
            return

        super().keyPressEvent(event)

    def _send(self, text):
        if not cmd_history or cmd_history[-1] != text:
            cmd_history.append(text)
        self._hist_pos = len(cmd_history)
        self._hist_draft = ""
        self.clear()
        self._in_config = False
        self.setFixedHeight(48)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.mode_changed.emit("exec")
        self.send_requested.emit(text)

    def _move_cursor_end(self):
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cur)

    def show_dynamic_completions(self, items):
        if not items: return
        # Update completer model dynamically
        model = QStringListModel(items, self.completer)
        self.completer.setModel(model)
        
        # Calculate prefix (last word)
        text = self.textCursor().block().text()
        prefix = text.split()[-1] if text.split() else ""
        self.completer.setCompletionPrefix(prefix)
        
        rect = self.cursorRect()
        rect.setWidth(self.completer.popup().sizeHintForColumn(0) + self.completer.popup().verticalScrollBar().sizeHint().width())
        self.completer.complete(rect)

    def show_static_completions(self):
        # Restore static model
        self.completer.setModel(QStringListModel(self.COMPLETIONS, self.completer))
        
        # Trigger completion based on last word
        text = self.textCursor().block().text()
        prefix = text.split()[-1] if text.split() else ""
        self.completer.setCompletionPrefix(prefix)
        
        rect = self.cursorRect()
        rect.setWidth(self.completer.popup().sizeHintForColumn(0) + self.completer.popup().verticalScrollBar().sizeHint().width())
        self.completer.complete(rect)


# ───────────────────────────────────────────────
# Add / Edit Device Dialog
# ───────────────────────────────────────────────
class DeviceDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("Device Configuration")
        self.setMinimumWidth(460)
        c = THEMES[current_theme]
        self.setStyleSheet(f"""
            QDialog {{ background: {c['bg']}; color: {c['fg']}; }}
            QLabel {{ color: {c['button_text']}; font-size: 11px; }}
            QLineEdit, QComboBox, QTextEdit {{
                background: {c['input']}; border: 1px solid {c['border']};
                color: {c['input_text']}; padding: 7px 10px; border-radius: 5px;
                font-family: Consolas; font-size: 12px;
            }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
            QPushButton {{
                background: {c['button']}; color: {c['button_text']}; border: 1px solid {c['border']};
                padding: 8px 20px; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {c['button_hover']}; color: {c['accent']}; border-color: {c['accent']}; }}
            QPushButton#save {{ background: {c['highlight']}; color: {c['accent']}; border-color: {c['accent']}; font-weight: bold; }}
            QPushButton#save:hover {{ background: {c['accent']}; color: #000; }}
            QGroupBox {{ border: 1px solid {c['border']}; border-radius: 5px; margin-top: 12px; color: {c['meta']}; font-size: 10px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left:8px; padding:0 4px; }}
        """)

        main = QVBoxLayout(self)
        main.setSpacing(12)

        conn_grp = QGroupBox("CONNECTION")
        form = QFormLayout(conn_grp)
        form.setSpacing(8)

        self.f_ip = QLineEdit(data.get("host", "") if data else "")
        self.f_ip.setPlaceholderText("192.168.1.1")
        self.f_port = QLineEdit(str(data.get("port", 22)) if data else "22")
        self.f_user = QLineEdit(data.get("username", "") if data else "")
        self.f_pass = QLineEdit(data.get("password", "") if data else "")
        self.f_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_secret = QLineEdit(data.get("secret", "") if data else "")
        self.f_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_secret.setPlaceholderText("(optional)")

        self.f_dtype = QComboBox()
        types = ["cisco_ios", "cisco_xe", "cisco_xr", "cisco_nxos", "cisco_asa",
                 "juniper_junos", "huawei", "linux",
                 "paloalto_panos", "fortinet",
                 "dell_os10", "alcatel_aos"]
        self.f_dtype.addItems(types)
        if data and data.get("device_type") in types:
            self.f_dtype.setCurrentIndex(types.index(data["device_type"]))

        form.addRow("IP / Host *", self.f_ip)
        form.addRow("SSH Port", self.f_port)
        form.addRow("Username *", self.f_user)
        form.addRow("Password *", self.f_pass)
        form.addRow("Enable Secret", self.f_secret)
        form.addRow("Device Type", self.f_dtype)
        main.addWidget(conn_grp)

        meta_grp = QGroupBox("METADATA")
        mform = QFormLayout(meta_grp)
        mform.setSpacing(8)
        self.f_name = QLineEdit(data.get("hostname", "") if data else "")
        self.f_name.setPlaceholderText("auto-detected on connect")
        self.f_tags = QLineEdit(", ".join(data.get("tags", [])) if data else "")
        self.f_tags.setPlaceholderText("prod, core, site-a")
        self.f_notes = QLineEdit(data.get("notes", "") if data else "")
        mform.addRow("Display Name", self.f_name)
        mform.addRow("Tags", self.f_tags)
        mform.addRow("Notes", self.f_notes)
        main.addWidget(meta_grp)

        btns = QHBoxLayout()
        ok = QPushButton("Save Device")
        ok.setObjectName("save")
        ok.setDefault(True)
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        main.addLayout(btns)

    def get_data(self):
        return {
            "host": self.f_ip.text().strip(),
            "port": int(self.f_port.text().strip() or 22),
            "username": self.f_user.text().strip(),
            "password": self.f_pass.text(),
            "secret": self.f_secret.text(),
            "device_type": self.f_dtype.currentText(),
            "hostname": self.f_name.text().strip() or None,
            "tags": [t.strip() for t in self.f_tags.text().split(",") if t.strip()],
            "notes": self.f_notes.text().strip(),
            "connected": False,
        }


# ───────────────────────────────────────────────
# Task Editor
# ───────────────────────────────────────────────
class TaskEditor(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Task Library")
        self.setMinimumSize(680, 460)
        c = THEMES[current_theme]
        self.setStyleSheet(f"""
            QDialog {{ background: {c['bg']}; color: {c['fg']}; }}
            QListWidget {{ background: {c['input']}; border: 1px solid {c['border']}; color: {c['fg']}; padding: 4px; border-radius: 4px; }}
            QListWidget::item {{ padding: 8px 12px; }}
            QListWidget::item:selected {{ background: {c['highlight']}; color: {c['accent']}; }}
            QTextEdit {{ background: {c['console']}; color: {c['console_text']}; font-family: "Cascadia Code","Consolas",monospace; font-size: 12px; border: 1px solid {c['border']}; border-radius: 4px; padding: 8px; }}
            QLineEdit {{ background: {c['input']}; border: 1px solid {c['border']}; color: {c['input_text']}; padding: 7px; border-radius: 4px; font-family: Consolas; }}
            QPushButton {{ background: {c['button']}; color: {c['button_text']}; border: 1px solid {c['border']}; padding: 7px 16px; border-radius: 4px; }}
            QPushButton:hover {{ background: {c['button_hover']}; color: {c['accent']}; }}
            QLabel {{ color: {c['meta']}; font-size: 11px; }}
        """)

        main = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(QLabel("SAVED TaskS"))
        self.Task_list = QListWidget()
        self.Task_list.itemClicked.connect(self._load)
        left.addWidget(self.Task_list)
        lbtns = QHBoxLayout()
        new_btn = QPushButton("+ New")
        del_btn = QPushButton("Delete")
        new_btn.clicked.connect(self._new)
        del_btn.clicked.connect(self._delete)
        lbtns.addWidget(new_btn)
        lbtns.addWidget(del_btn)
        left.addLayout(lbtns)
        main.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Task NAME"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. harden-interface")
        right.addWidget(self.name_edit)
        right.addWidget(QLabel("COMMANDS  (one per line, # for comments)"))
        self.body_edit = QTextEdit()
        self.body_edit.setPlaceholderText(
            "# Configure secure interface\ninterface GigabitEthernet0/1\n"
            " description UPLINK\n no shutdown\n spanning-tree portfast"
        )
        right.addWidget(self.body_edit, 1)
        save_btn = QPushButton("💾  Save Task")
        save_btn.clicked.connect(self._save)
        right.addWidget(save_btn)
        main.addLayout(right, 2)

        self._refresh_list()

    def _refresh_list(self):
        self.Task_list.clear()
        for name in Tasks:
            self.Task_list.addItem(name)

    def _load(self, item):
        name = item.text()
        self.name_edit.setText(name)
        self.body_edit.setPlainText(Tasks[name])

    def _new(self):
        self.name_edit.clear()
        self.body_edit.clear()
        self.name_edit.setFocus()

    def _save(self):
        name = self.name_edit.text().strip()
        body = self.body_edit.toPlainText().strip()
        if name and body:
            Tasks[name] = body
            save_config()
            self._refresh_list()

    def _delete(self):
        name = self.name_edit.text().strip()
        if name in Tasks:
            del Tasks[name]
            save_config()
            self._refresh_list()
            self.name_edit.clear()
            self.body_edit.clear()


# ───────────────────────────────────────────────
# Quick Command Manager
# ───────────────────────────────────────────────
class QuickCmdDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Commands Manager")
        self.setMinimumSize(500, 400)
        c = THEMES[current_theme]
        self.setStyleSheet(f"""
            QDialog {{ background: {c['bg']}; color: {c['fg']}; }}
            QListWidget {{ background: {c['input']}; border: 1px solid {c['border']}; color: {c['fg']}; padding: 4px; border-radius: 4px; }}
            QListWidget::item {{ padding: 8px 12px; }}
            QListWidget::item:selected {{ background: {c['highlight']}; color: {c['accent']}; }}
            QLineEdit {{ background: {c['input']}; border: 1px solid {c['border']}; color: {c['input_text']}; padding: 7px; border-radius: 4px; font-family: Consolas; }}
            QPushButton {{ background: {c['button']}; color: {c['button_text']}; border: 1px solid {c['border']}; padding: 7px 16px; border-radius: 4px; }}
            QPushButton:hover {{ background: {c['button_hover']}; color: {c['accent']}; }}
            QLabel {{ color: {c['meta']}; font-size: 11px; }}
        """)

        layout = QVBoxLayout(self)
        
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_click)
        layout.addWidget(self.list_widget)

        form = QFormLayout()
        self.lbl_edit = QLineEdit()
        self.cmd_edit = QLineEdit()
        form.addRow("Label (short):", self.lbl_edit)
        form.addRow("Command:", self.cmd_edit)
        layout.addLayout(form)

        btns = QHBoxLayout()
        add_btn = QPushButton("Add / Update")
        add_btn.clicked.connect(self._add)
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self._delete)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        layout.addLayout(btns)
        
        self._refresh()

    def _refresh(self):
        self.list_widget.clear()
        for item in quick_commands:
            self.list_widget.addItem(f"{item['label']}  →  {item['cmd']}")

    def _on_item_click(self, item):
        idx = self.list_widget.row(item)
        if 0 <= idx < len(quick_commands):
            data = quick_commands[idx]
            self.lbl_edit.setText(data['label'])
            self.cmd_edit.setText(data['cmd'])

    def _add(self):
        lbl = self.lbl_edit.text().strip()
        cmd = self.cmd_edit.text().strip()
        if not lbl or not cmd:
            return
        
        # Check if updating existing by label
        for item in quick_commands:
            if item['label'] == lbl:
                item['cmd'] = cmd
                self._refresh()
                return

        quick_commands.append({"label": lbl, "cmd": cmd})
        self._refresh()

    def _delete(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(quick_commands):
            quick_commands.pop(row)
            self._refresh()


# ───────────────────────────────────────────────
# Normal SSH (Internal Window)
# ───────────────────────────────────────────────
class MiniTerminal:
    ANSI16 = [
        "#000000","#cd3131","#0dbc79","#e5e510",
        "#2472c8","#bc3fbc","#11a8cd","#e5e5e5",
        "#666666","#f14c4c","#23d18b","#f5f543",
        "#3b8eea","#d670d6","#29b8db","#ffffff",
    ]

    def __init__(self, rows=24, cols=80):
        self.rows = rows
        self.cols = cols
        self.default_cell = [' ', None, None, False, False]
        self.lines   = [[list(self.default_cell) for _ in range(cols)] for _ in range(rows)]
        self.history = []          # scrollback
        self.cx = 0; self.cy = 0
        self.current_fg      = None
        self.current_bg      = None
        self.current_bold    = False
        self.current_reverse = False
        self.alt_lines = None
        self.alt_cx = 0; self.alt_cy = 0
        self.is_alt = False
        self._saved_cx = 0; self._saved_cy = 0
        # 256-colour palette built lazily
        self._palette256 = None

    # ── 256-colour palette ────────────────────────────────────────────────────
    def _get_palette256(self):
        if self._palette256:
            return self._palette256
        p = list(self.ANSI16)
        # 216-colour cube
        for r in range(6):
            for g in range(6):
                for b in range(6):
                    p.append("#{:02x}{:02x}{:02x}".format(
                        0 if r==0 else 55+r*40,
                        0 if g==0 else 55+g*40,
                        0 if b==0 else 55+b*40,
                    ))
        # 24 greyscale ramp
        for i in range(24):
            v = 8 + i*10
            p.append("#{:02x}{:02x}{:02x}".format(v,v,v))
        self._palette256 = p
        return p

    def _color_hex(self, idx):
        """Return hex string for colour index (0-255 or None)."""
        if idx is None:
            return None
        if isinstance(idx, int) and idx < 16:
            return self.ANSI16[idx]
        p = self._get_palette256()
        if isinstance(idx, int) and idx < len(p):
            return p[idx]
        if isinstance(idx, str):   # already '#rrggbb'
            return idx
        return None

    # ── main input processing ─────────────────────────────────────────────────
    def process(self, data):
        i = 0
        while i < len(data):
            c = data[i]
            if c == '\x1b':
                if i + 1 >= len(data): i += 1; continue
                nxt = data[i+1]
                if nxt == '[':
                    j = i + 2
                    while j < len(data) and not (0x40 <= ord(data[j]) <= 0x7E):
                        j += 1
                    if j < len(data):
                        self._handle_csi(data[i+2:j+1]); i = j
                elif nxt == ']':
                    j = i + 2
                    while j < len(data):
                        if data[j] == '\x07': break
                        if data[j] == '\x1b' and j+1 < len(data) and data[j+1] == '\\':
                            j += 1; break
                        j += 1
                    i = j
                elif nxt in '()': i += 2
                elif nxt == '7': self._saved_cx,self._saved_cy=self.cx,self.cy; i+=1
                elif nxt == '8': self.cx,self.cy=self._saved_cx,self._saved_cy; i+=1
                elif nxt == 'M':
                    if self.cy==0:
                        self.lines.insert(0,[list(self.default_cell) for _ in range(self.cols)])
                        self.lines.pop()
                    else: self.cy -= 1
                    i += 1
                elif nxt == 'c': self.__init__(self.rows,self.cols); i+=1
                else: i += 1
            elif c == '\r': self.cx = 0
            elif c == '\n':
                self.cy += 1
                if self.cy >= self.rows: self._scroll(); self.cy = self.rows-1
            elif c in ('\b','\x7f'):
                if self.cx > 0:
                    self.cx -= 1
                    self.lines[self.cy][self.cx] = list(self.default_cell)
            elif c == '\t':
                self.cx = min(((self.cx//8)+1)*8, self.cols-1)
            elif c == '\x07': pass   # BEL
            elif 32 <= ord(c) <= 126 or ord(c) > 127:
                if self.cx >= self.cols:
                    self.cx = 0; self.cy += 1
                    if self.cy >= self.rows: self._scroll(); self.cy = self.rows-1
                self.lines[self.cy][self.cx] = [
                    c, self.current_fg, self.current_bg,
                    self.current_bold, self.current_reverse
                ]
                self.cx += 1
            i += 1

    def _handle_csi(self, seq):
        cmd  = seq[-1]
        body = seq[:-1]
        is_p = body.startswith('?')
        if is_p: body = body[1:]
        try:
            params = [int(x) if x else None for x in (body.split(';') if body else [])]
        except Exception: params = []
        def gp(idx, d): return params[idx] if idx<len(params) and params[idx] is not None else d

        if is_p and cmd=='h':
            if gp(0,0) in (47,1047,1049): self._enter_alt(); return
        if is_p and cmd=='l':
            if gp(0,0) in (47,1047,1049): self._exit_alt(); return
        if cmd=='m': self._sgr(params or [0]); return

        if cmd in 'Hf':
            self.cy=min(max(0,gp(0,1)-1),self.rows-1)
            self.cx=min(max(0,gp(1,1)-1),self.cols-1)
        elif cmd=='A': self.cy=max(0,self.cy-gp(0,1))
        elif cmd=='B': self.cy=min(self.rows-1,self.cy+gp(0,1))
        elif cmd=='C': self.cx=min(self.cols-1,self.cx+gp(0,1))
        elif cmd=='D': self.cx=max(0,self.cx-gp(0,1))
        elif cmd=='G': self.cx=min(max(0,gp(0,1)-1),self.cols-1)
        elif cmd=='d': self.cy=min(max(0,gp(0,1)-1),self.rows-1)
        elif cmd=='J':
            m=gp(0,0)
            if m==0:
                for k in range(self.cx,self.cols): self.lines[self.cy][k]=list(self.default_cell)
                for r in range(self.cy+1,self.rows): self.lines[r]=[list(self.default_cell) for _ in range(self.cols)]
            elif m==1:
                for r in range(self.cy): self.lines[r]=[list(self.default_cell) for _ in range(self.cols)]
                for k in range(self.cx+1): self.lines[self.cy][k]=list(self.default_cell)
            elif m==2:
                # ── FIX: ED2 clears the *visible* screen but keeps cursor position.
                #         We do NOT wipe history here — that's ED3 (m==3).
                self.lines=[[list(self.default_cell) for _ in range(self.cols)] for _ in range(self.rows)]
                self.cx=self.cy=0
            elif m==3:
                # ED3 — clear scrollback history (xterm extension used by `clear`)
                self.history.clear()
                self.lines=[[list(self.default_cell) for _ in range(self.cols)] for _ in range(self.rows)]
                self.cx=self.cy=0
        elif cmd=='K':
            m=gp(0,0)
            if m==0:
                for k in range(self.cx,self.cols): self.lines[self.cy][k]=list(self.default_cell)
            elif m==1:
                for k in range(self.cx+1): self.lines[self.cy][k]=list(self.default_cell)
            elif m==2:
                self.lines[self.cy]=[list(self.default_cell) for _ in range(self.cols)]
        elif cmd=='X':
            for k in range(self.cx,min(self.cx+gp(0,1),self.cols)):
                self.lines[self.cy][k]=list(self.default_cell)
        elif cmd=='L':
            for _ in range(gp(0,1)):
                self.lines.insert(self.cy,[list(self.default_cell) for _ in range(self.cols)])
                if len(self.lines)>self.rows: self.lines.pop()
        elif cmd=='M':
            for _ in range(gp(0,1)):
                if self.cy<len(self.lines):
                    self.lines.pop(self.cy)
                    self.lines.append([list(self.default_cell) for _ in range(self.cols)])
        elif cmd=='P':
            row=self.lines[self.cy]
            for _ in range(gp(0,1)):
                if self.cx<len(row): row.pop(self.cx); row.append(list(self.default_cell))
        elif cmd=='@':
            row=self.lines[self.cy]
            for _ in range(gp(0,1)):
                row.insert(self.cx,list(self.default_cell))
                if len(row)>self.cols: row.pop()
        elif cmd=='S':
            for _ in range(gp(0,1)): self._scroll()
        elif cmd=='T':
            for _ in range(gp(0,1)):
                self.lines.insert(0,[list(self.default_cell) for _ in range(self.cols)])
                if len(self.lines)>self.rows: self.lines.pop()

    def _sgr(self, params):
        i = 0
        while i < len(params):
            p = params[i] if params[i] is not None else 0
            if   p==0:  self.current_fg=None; self.current_bg=None; self.current_bold=False; self.current_reverse=False
            elif p==1:  self.current_bold=True
            elif p==22: self.current_bold=False
            elif p==7:  self.current_reverse=True
            elif p==27: self.current_reverse=False
            elif 30<=p<=37: self.current_fg=p-30
            elif p==38:
                if i+1<len(params) and params[i+1]==5 and i+2<len(params):
                    self.current_fg=params[i+2]; i+=2
                elif i+1<len(params) and params[i+1]==2 and i+4<len(params):
                    r,g,b=params[i+2],params[i+3],params[i+4]
                    self.current_fg="#{:02x}{:02x}{:02x}".format(r or 0,g or 0,b or 0); i+=4
                else: i+=2
            elif p==39: self.current_fg=None
            elif 40<=p<=47: self.current_bg=p-40
            elif p==48:
                if i+1<len(params) and params[i+1]==5 and i+2<len(params):
                    self.current_bg=params[i+2]; i+=2
                elif i+1<len(params) and params[i+1]==2 and i+4<len(params):
                    r,g,b=params[i+2],params[i+3],params[i+4]
                    self.current_bg="#{:02x}{:02x}{:02x}".format(r or 0,g or 0,b or 0); i+=4
                else: i+=2
            elif p==49: self.current_bg=None
            elif 90<=p<=97:   self.current_fg=p-90+8
            elif 100<=p<=107: self.current_bg=p-100+8
            i+=1

    def _enter_alt(self):
        if not self.is_alt:
            self.alt_lines=[row[:] for row in self.lines]
            self.alt_cx,self.alt_cy=self.cx,self.cy
            self.lines=[[list(self.default_cell) for _ in range(self.cols)] for _ in range(self.rows)]
            self.cx=self.cy=0; self.is_alt=True

    def _exit_alt(self):
        if self.is_alt and self.alt_lines:
            self.lines=self.alt_lines; self.cx,self.cy=self.alt_cx,self.alt_cy
            self.is_alt=False

    def _scroll(self):
        if not self.is_alt:
            self.history.append(self.lines.pop(0))
            if len(self.history)>10000: self.history.pop(0)
        else:
            self.lines.pop(0)
        self.lines.append([list(self.default_cell) for _ in range(self.cols)])

    def to_html(self):
        BG="#0A0E14"; FG="#CDD6F4"
        if self.is_alt:
            # Alt-screen (nano/vim/htop): render EXACTLY self.rows lines.
            # Do NOT trim — apps like nano rely on precise row count for layout.
            rows = self.lines
        else:
            # Normal scrollback: include history, trim trailing blank rows.
            rows = self.history + self.lines
            while rows and all(c[0]==' ' and c[1] is None for c in rows[-1]):
                rows = rows[:-1]
        out = [
            f'<pre style="'
            f'font-family:\'Cascadia Code\',\'JetBrains Mono\',\'Fira Code\',\'Consolas\',monospace;'
            f'font-size:10.5pt;line-height:1.25;margin:0;padding:10px 12px;'
            f'background:{BG};color:{FG};'
            f'white-space:pre-wrap;word-break:break-all;">'
        ]
        p256 = self._get_palette256()
        def resolve(idx):
            if idx is None: return None
            if isinstance(idx, str): return idx
            if 0<=idx<len(p256): return p256[idx]
            return None

        for row in rows:
            cur=None; buf=[]
            for cell in row:
                ch,fg,bg,bold,rev=cell
                rfg,rbg=(resolve(bg),resolve(fg)) if rev else (resolve(fg),resolve(bg))
                key=(rfg,rbg,bold)
                if key!=cur:
                    if cur is not None:
                        out.append(self._esc(''.join(buf))); out.append('</span>'); buf=[]
                    css=[]
                    if rfg: css.append(f'color:{rfg}')
                    elif rev: css.append(f'color:{BG}')
                    if rbg: css.append(f'background:{rbg}')
                    elif rev: css.append(f'background:{FG}')
                    if bold: css.append('font-weight:bold')
                    out.append(f'<span style="{";".join(css)}">' if css else '<span>')
                    cur=key
                buf.append(ch)
            if cur is not None:
                out.append(self._esc(''.join(buf))); out.append('</span>')
            out.append('\n')
        out.append('</pre>')
        return ''.join(out)

    def _esc(self,t): return t.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

    def resize(self, cols, rows):
        """Resize the terminal grid — called on window resize (SIGWINCH)."""
        if cols == self.cols and rows == self.rows:
            return
        # Expand or shrink each row
        for i, row in enumerate(self.lines):
            if len(row) < cols:
                row.extend([list(self.default_cell)] * (cols - len(row)))
            else:
                self.lines[i] = row[:cols]
        # Expand or shrink vertically
        while len(self.lines) < rows:
            self.lines.append([list(self.default_cell) for _ in range(cols)])
        while len(self.lines) > rows:
            self.lines.pop()
        # Same for alt screen
        if self.alt_lines:
            for i, row in enumerate(self.alt_lines):
                if len(row) < cols:
                    row.extend([list(self.default_cell)] * (cols - len(row)))
                else:
                    self.alt_lines[i] = row[:cols]
            while len(self.alt_lines) < rows:
                self.alt_lines.append([list(self.default_cell) for _ in range(cols)])
            while len(self.alt_lines) > rows:
                self.alt_lines.pop()
        self.cols = cols
        self.rows = rows
        self.cx   = min(self.cx, cols - 1)
        self.cy   = min(self.cy, rows - 1)

    def clear_all(self):
        """Hard-clear: wipe history and visible screen (like `reset`)."""
        self.history.clear()
        self.lines=[[list(self.default_cell) for _ in range(self.cols)] for _ in range(self.rows)]
        self.cx=self.cy=0


# ─────────────────────────────────────────────────────────────────────────────
#  TERMINAL WIDGET  — QPainter direct cell rendering (no QTextEdit, no hscroll)
# ─────────────────────────────────────────────────────────────────────────────

class TerminalWidget(QWidget):
    """
    Renders the MiniTerminal cell grid directly with QPainter.
    No QTextEdit, no HTML, no document model — zero horizontal scroll possible.
    Each character cell is drawn at a fixed pixel position.
    """
    keyPressed = pyqtSignal(str)
    resized    = pyqtSignal(int, int)   # cols, rows

    BG  = QColor("#0A0E14")
    FG  = QColor("#CDD6F4")

    PALETTE = [
        "#000000","#cd3131","#0dbc79","#e5e510",
        "#2472c8","#bc3fbc","#11a8cd","#e5e5e5",
        "#666666","#f14c4c","#23d18b","#f5f543",
        "#3b8eea","#d670d6","#29b8db","#ffffff",
    ]

    def __init__(self, term: "MiniTerminal", parent=None):
        super().__init__(parent)
        self.term = term
        self._in_alt = False

        # ── Font ──────────────────────────────────────────────────────────────
        for name in ("Cascadia Code","JetBrains Mono","Fira Code","Consolas","Courier New"):
            f = QFont(name, 10)
            if QFontInfo(f).fixedPitch(): break
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setFixedPitch(True)
        self._font      = f
        self._font_bold = QFont(f); self._font_bold.setBold(True)
        fm = QFontMetrics(f)
        self._cw = fm.horizontalAdvance('M')   # cell width
        self._ch = fm.height()                  # cell height
        self._ca = fm.ascent()                  # baseline offset

        # ── Scrollback ────────────────────────────────────────────────────────
        self._scroll_offset = 0   # rows scrolled up from bottom (0 = bottom)

        # ── Cursor blink ──────────────────────────────────────────────────────
        self._cur_vis = True
        self._blink   = QTimer(self)
        self._blink.timeout.connect(self._blink_tick)
        self._blink.start(530)

        # ── 256-colour cache ──────────────────────────────────────────────────
        self._qcolor_cache: dict = {}

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFont(f)

        # Vertical scrollbar (external, lives in parent layout)
        from PyQt6.QtWidgets import QScrollBar
        self._vbar = QScrollBar(Qt.Orientation.Vertical, parent)
        self._vbar.setStyleSheet("""
            QScrollBar:vertical { background:#0A0E14; width:7px; border:none; }
            QScrollBar::handle:vertical { background:#1E2A3A; border-radius:3px; min-height:24px; }
            QScrollBar::handle:vertical:hover { background:#2E4A6A; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        """)
        self._vbar.valueChanged.connect(self._on_vscroll)

    # ── colour resolver ───────────────────────────────────────────────────────
    def _qc(self, idx) -> QColor:
        if idx is None: return self.FG
        if idx in self._qcolor_cache: return self._qcolor_cache[idx]
        if isinstance(idx, str):
            c = QColor(idx)
        elif isinstance(idx, int):
            pal = self.term._get_palette256()
            c   = QColor(pal[idx]) if 0 <= idx < len(pal) else self.FG
        else:
            c = self.FG
        self._qcolor_cache[idx] = c
        return c

    # ── scrollbar sync ────────────────────────────────────────────────────────
    def _sync_scrollbar(self):
        hist = len(self.term.history)
        if self._in_alt or hist == 0:
            self._vbar.setRange(0, 0)
            self._vbar.setValue(0)
            return
        rows = self.term.rows
        self._vbar.setRange(0, hist)
        self._vbar.setPageStep(rows)
        self._vbar.setSingleStep(1)
        # Don't move the bar if user is scrolled up
        if self._scroll_offset == 0:
            self._vbar.setValue(hist)

    def _on_vscroll(self, val):
        hist = len(self.term.history)
        # val=hist means bottom (no scroll), val=0 means top
        self._scroll_offset = max(0, hist - val)
        self.update()

    def scroll_to_bottom(self):
        self._scroll_offset = 0
        self._sync_scrollbar()
        self.update()

    # ── painting ──────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QBrush
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        cw, ch, ca = self._cw, self._ch, self._ca
        W, H = self.width(), self.height()

        # Fill background
        p.fillRect(0, 0, W, H, self.BG)

        # Which rows to show
        if self._in_alt:
            visible = self.term.lines
        else:
            all_rows = self.term.history + self.term.lines
            total    = len(all_rows)
            rows_vis = H // ch
            # bottom of scrollback = last rows_vis rows
            end   = total - self._scroll_offset
            start = max(0, end - rows_vis)
            visible = all_rows[start:end]

        for ry, row in enumerate(visible):
            y = ry * ch
            for cx_idx, cell in enumerate(row):
                ch_char, fg, bg, bold, rev = cell
                x = cx_idx * cw

                # Resolve colours
                if rev:
                    bg_col = self._qc(fg) if fg is not None else self.FG
                    fg_col = self._qc(bg) if bg is not None else self.BG
                else:
                    bg_col = self._qc(bg) if bg is not None else self.BG
                    fg_col = self._qc(fg) if fg is not None else self.FG

                # Draw cell background (skip if default bg — already filled)
                if bg is not None or rev:
                    p.fillRect(x, y, cw, ch, bg_col)

                # Draw character
                if ch_char.strip():
                    p.setFont(self._font_bold if bold else self._font)
                    p.setPen(fg_col)
                    p.drawText(x, y + ca, ch_char)

        # Draw cursor (only when not scrolled up and not in alt with app cursor)
        if self._cur_vis and self._scroll_offset == 0:
            cx = self.term.cx
            cy = self.term.cy
            if self._in_alt:
                # cursor is absolute in alt screen
                pass
            else:
                # cursor is in the visible lines portion
                hist_shown = min(len(self.term.history), H // ch)
                cy = hist_shown + self.term.cy - max(0, hist_shown + self.term.rows - H // ch)
            p.fillRect(cx * cw, cy * ch, cw, ch, QColor("#CDD6F4"))
            if self.term.lines[self.term.cy][self.term.cx][0].strip():
                p.setFont(self._font)
                p.setPen(self.BG)
                p.drawText(cx * cw, cy * ch + ca, self.term.lines[self.term.cy][self.term.cx][0])

        p.end()

    # ── resize → emit new cols/rows ───────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        cols = max(80, self.width()  // self._cw)
        rows = max(24, self.height() // self._ch)
        self.resized.emit(cols, rows)
        self._sync_scrollbar()

    # ── blink ─────────────────────────────────────────────────────────────────
    def _blink_tick(self):
        self._cur_vis = not self._cur_vis
        self.update()

    def focusInEvent(self,  e): self._blink.start(530); super().focusInEvent(e)
    def focusOutEvent(self, e): self._blink.stop(); self._cur_vis=True; self.update(); super().focusOutEvent(e)

    # ── wheel scroll ──────────────────────────────────────────────────────────
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        steps = max(1, abs(delta) // 40)
        if self._in_alt:
            key = '\x19' if delta > 0 else '\x16'
            for _ in range(steps): self.keyPressed.emit(key)
        else:
            hist = len(self.term.history)
            if delta > 0:
                self._scroll_offset = min(self._scroll_offset + steps * 3, hist)
            else:
                self._scroll_offset = max(self._scroll_offset - steps * 3, 0)
            self._sync_scrollbar()
            self.update()
        event.accept()

    # ── focus / tab ───────────────────────────────────────────────────────────
    def focusNextPrevChild(self, _): return False

    # ── keyboard ─────────────────────────────────────────────────────────────
    def keyPressEvent(self, event):
        key  = event.key()
        text = event.text()
        mods = event.modifiers()

        if (mods & Qt.KeyboardModifier.ControlModifier and
            mods & Qt.KeyboardModifier.ShiftModifier and
            key == Qt.Key.Key_V):
            clip = QApplication.clipboard().text()
            if clip: self.keyPressed.emit(clip)
            event.accept(); return

        # Any key press snaps back to bottom
        self.scroll_to_bottom()

        mapping = {
            Qt.Key.Key_Backspace: '\x08',
            Qt.Key.Key_Delete:    '\x1b[3~',
            Qt.Key.Key_Return:    '\r',
            Qt.Key.Key_Enter:     '\r',
            Qt.Key.Key_Escape:    '\x1b',
            Qt.Key.Key_Tab:       '\t',
            Qt.Key.Key_Up:        '\x1b[A',
            Qt.Key.Key_Down:      '\x1b[B',
            Qt.Key.Key_Right:     '\x1b[C',
            Qt.Key.Key_Left:      '\x1b[D',
            Qt.Key.Key_Home:      '\x1b[H',
            Qt.Key.Key_End:       '\x1b[F',
            Qt.Key.Key_PageUp:    '\x1b[5~',
            Qt.Key.Key_PageDown:  '\x1b[6~',
            Qt.Key.Key_Insert:    '\x1b[2~',
            Qt.Key.Key_F1:        '\x1bOP',
            Qt.Key.Key_F2:        '\x1bOQ',
            Qt.Key.Key_F3:        '\x1bOR',
            Qt.Key.Key_F4:        '\x1bOS',
            Qt.Key.Key_F5:        '\x1b[15~',
            Qt.Key.Key_F6:        '\x1b[17~',
            Qt.Key.Key_F7:        '\x1b[18~',
            Qt.Key.Key_F8:        '\x1b[19~',
            Qt.Key.Key_F9:        '\x1b[20~',
            Qt.Key.Key_F10:       '\x1b[21~',
        }
        if key in mapping:
            self.keyPressed.emit(mapping[key])
        elif mods & Qt.KeyboardModifier.ControlModifier:
            if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                self.keyPressed.emit(chr(key - Qt.Key.Key_A + 1))
            elif key == Qt.Key.Key_BracketLeft:
                self.keyPressed.emit('\x1b')
        elif mods & Qt.KeyboardModifier.AltModifier and text:
            self.keyPressed.emit('\x1b' + text)
        elif text:
            self.keyPressed.emit(text)
        event.accept()


# ── keep old name as alias so NormalSSHDialog can use either name ─────────────
TerminalTextEdit = TerminalWidget


# ─────────────────────────────────────────────────────────────────────────────
#  SSH WORKER
# ─────────────────────────────────────────────────────────────────────────────

class ParamikoShellWorker(QThread):
    data_ready     = pyqtSignal(str)
    error          = pyqtSignal(str)
    session_closed = pyqtSignal()


    def __init__(self, device):
        super().__init__()
        self.device  = device
        self.running = True
        self.shell   = None
        self.client  = None

    def run(self):
        import paramiko
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            args = {
                "hostname": self.device["host"],
                "username": self.device["username"],
                "port":     int(self.device.get("port", 22)),
                "timeout":  10,
            }
            if self.device.get("password"):
                args["password"] = self.device["password"]
            self.client.connect(**args)
            self.shell = self.client.invoke_shell(term='xterm-256color', width=80, height=24)
            self.shell.settimeout(0)   # non-blocking
            time.sleep(0.3)            # brief wait for banner/prompt
            while self.running:
                try:
                    data = self.shell.recv(65536)
                    if not data:
                        break
                    self.data_ready.emit(data.decode('utf-8', errors='replace'))
                except Exception:
                    # No data yet — sleep 5 ms (was 20 ms, 4x faster response)
                    time.sleep(0.005)
                if self.shell.exit_status_ready():
                    break
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if self.client: self.client.close()
            self.session_closed.emit()

    def write(self, data):
        if self.shell:
            if isinstance(data, str):
                # Encode explicitly — \t → 0x09 (what bash readline expects
                # for tab-completion). Never let Python mangle special bytes.
                data = data.encode('utf-8', errors='replace')
            self.shell.send(data)

    def pty_resize(self, cols, rows):
        """Send SIGWINCH to the remote PTY so nano/vim reflow to new size."""
        if self.shell:
            try:
                self.shell.resize_pty(width=cols, height=rows)
            except Exception:
                pass

    def stop(self):
        self.running = False


# ─────────────────────────────────────────────────────────────────────────────
#  TITLE BAR
# ─────────────────────────────────────────────────────────────────────────────

class TitleBar(QWidget):
    def __init__(self, user, host, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setObjectName("TB")
        self._drag = None
        self._pulse_state = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._do_pulse)

        self.setStyleSheet("""
            QWidget#TB {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #111827, stop:1 #0D1117);
                border-bottom: 1px solid #1E2D40;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 6, 0)
        lay.setSpacing(0)

        # SSH icon
        ico = QLabel("⌨")
        ico.setStyleSheet("color:#38BDF8;font-size:15px;background:transparent;padding-right:10px;")
        lay.addWidget(ico)

        # Connection label
        self._chip = QLabel(f"  {user}@{host}  ")
        self._chip.setStyleSheet("""
            color: #94A3B8;
            background: #0D1117;
            font-family: 'Cascadia Code','JetBrains Mono','Fira Code','Consolas', monospace;
            font-size: 10px;
            padding: 4px 14px 4px 14px;
            border-top: 2px solid #38BDF8;
            border-radius: 0;
        """)
        lay.addWidget(self._chip)
        lay.addStretch()

        # Status pill
        self._pill = QLabel("  ◎ CONNECTING  ")
        self._pill.setStyleSheet("""
            color: #F59E0B;
            font-family: 'Cascadia Code','Consolas', monospace;
            font-size: 8px;
            letter-spacing: 2px;
            background: transparent;
            padding-right: 12px;
        """)
        lay.addWidget(self._pill)

        # Window controls
        for sym, tip, hcol, slot in [
            ("─", "Minimise", "#1E293B", lambda: self.window().showMinimized()),
            ("▭", "Maximise", "#1E293B", self._tog_max),
            ("✕", "Close",    "#7F1D1D", lambda: self.window().close()),
        ]:
            b = QPushButton(sym)
            b.setToolTip(tip)
            b.setFixedSize(36, 32)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: #475569;
                    border: none; font-size: 11px;
                    font-family: 'Consolas', monospace;
                }}
                QPushButton:hover {{
                    background: {hcol}; color: #F8FAFC;
                    border-radius: 4px;
                }}
            """)
            b.clicked.connect(slot)
            lay.addWidget(b)

    def _tog_max(self):
        w = self.window()
        w.showNormal() if w.isMaximized() else w.showMaximized()

    def set_connected(self, host):
        self._pill.setText(f"  ◉ {host}  ")
        self._pill.setStyleSheet("""
            color: #34D399; font-family: 'Cascadia Code','Consolas', monospace;
            font-size: 8px; letter-spacing: 2px;
            background: transparent; padding-right: 12px;
        """)
        self._pulse_timer.start(800)

    def set_error(self):
        self._pulse_timer.stop()
        self._pill.setText("  ◉ ERROR  ")
        self._pill.setStyleSheet("""
            color: #F87171; font-family: 'Cascadia Code','Consolas', monospace;
            font-size: 8px; letter-spacing: 2px;
            background: transparent; padding-right: 12px;
        """)

    def set_closed(self):
        self._pulse_timer.stop()
        self._pill.setText("  ◎ CLOSED  ")
        self._pill.setStyleSheet("""
            color: #334155; font-family: 'Cascadia Code','Consolas', monospace;
            font-size: 8px; letter-spacing: 2px;
            background: transparent; padding-right: 12px;
        """)

    def _do_pulse(self):
        """Animate the connected pill between two green shades."""
        self._pulse_state = 1 - self._pulse_state
        col = "#6EE7B7" if self._pulse_state else "#34D399"
        self._pill.setStyleSheet(f"""
            color: {col}; font-family: 'Cascadia Code','Consolas', monospace;
            font-size: 8px; letter-spacing: 2px;
            background: transparent; padding-right: 12px;
        """)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


# ─────────────────────────────────────────────────────────────────────────────
#  ACCENT BAR  — thin neon line below title bar
# ─────────────────────────────────────────────────────────────────────────────

class AccentBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(2)
        self.setStyleSheet("""
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0.00 #0A0E14,
                stop:0.20 #0EA5E9,
                stop:0.50 #38BDF8,
                stop:0.80 #0EA5E9,
                stop:1.00 #0A0E14);
        """)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class NormalSSHDialog(QDialog):
    def __init__(self, device_idx, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.device = devices[device_idx]
        ansi_esc    = re.compile(r'\x1B(?:\[[0-?]*[ -/]*[@-~]|[@-Z\\-_])')
        raw_name    = (self.device.get("hostname") or self.device["host"]).strip()
        name        = ansi_esc.sub('', raw_name).strip()
        user        = self.device.get("username", "")

        self.setWindowTitle(f"{user}@{name}")
        self.resize(940, 600)
        self.setMinimumSize(640, 420)

        # ── Root layout (shadow wrapper) ──────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 6)

        frame = QFrame(self)
        frame.setGraphicsEffect(shadow)
        frame.setStyleSheet("""
            QFrame {
                background: #0A0E14;
                border: 1px solid #1E2D40;
                border-radius: 10px;
            }
        """)
        root.addWidget(frame)

        lay = QVBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Title bar
        self._title_bar = TitleBar(user, name, self)
        lay.addWidget(self._title_bar)

        # Neon accent bar
        lay.addWidget(AccentBar())

        # Console + vertical scrollbar in a horizontal row
        console_row = QHBoxLayout()
        console_row.setContentsMargins(0, 0, 0, 0)
        console_row.setSpacing(0)
        # ── Terminal emulator + SSH worker ────────────────────────────────────
        self.term   = MiniTerminal(24, 80)
        self._render_pending = False  # throttle renders to 60fps
        self.console = TerminalWidget(self.term, frame)
        console_row.addWidget(self.console, 1)
        console_row.addWidget(self.console._vbar)
        lay.addLayout(console_row, 1)

        # Resize grip (bottom-right corner)
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 2, 2)
        grip_row.addStretch()
        grip = QSizeGrip(frame)
        grip.setStyleSheet("background:transparent;")
        grip_row.addWidget(grip)
        lay.addLayout(grip_row)

        self.worker = ParamikoShellWorker(self.device)
        self.worker.data_ready.connect(self.on_data)
        self.worker.error.connect(self.on_error)
        self.worker.session_closed.connect(self.on_closed)
        self.console.keyPressed.connect(self.worker.write)
        self.worker.start()

        # Wire terminal resize: font-metric cols/rows → PTY SIGWINCH
        self.console.resized.connect(self._on_resize)

        QTimer.singleShot(700, lambda: self._title_bar.set_connected(name))

        # Auto-clear on open — only for Linux/bash, not network devices.
        # Network devices (Cisco IOS etc.) don't understand `clear` the same way.
        self.term.clear_all()
        dtype = (self.device.get("device_type") or self.device.get("type") or "").lower()
        _net = {"cisco_ios","cisco_xe","cisco_xr","cisco_nxos","cisco_asa",
                "cisco_wlc","juniper","juniper_junos","hp_comware",
                "hp_procurve","huawei","paloalto_panos","fortinet",
                "network","ios","nxos"}
        self._is_network_device = dtype in _net
        if not self._is_network_device:
            QTimer.singleShot(1000, self._initial_clear)

    def _initial_clear(self):
        """Send clear to the remote shell + hard-wipe local history/screen."""
        self.worker.write('clear\r')
        QTimer.singleShot(350, self.term.clear_all)

    # ── Data / event handlers ─────────────────────────────────────────────────

    def _on_resize(self, cols, rows):
        """Called when the console widget is resized — update PTY and emulator."""
        self.term.resize(cols, rows)
        self.worker.pty_resize(cols, rows)

    def on_data(self, text):
        self.term.process(text)
        if not self._render_pending:
            self._render_pending = True
            QTimer.singleShot(16, self._render)

    def _render(self):
        """Repaint the terminal — called max 60fps via 16ms timer."""
        self._render_pending = False
        self.console._in_alt = self.term.is_alt
        
        self.console._vbar.setVisible(not self.term.is_alt)
        
        self.console._sync_scrollbar()
        
        if self.console._scroll_offset == 0:
            self.console.scroll_to_bottom()
        
        self.console.update()

    def on_error(self, msg):
        self._title_bar.set_error()
        self.term.process(f"\r\n\x1b[1;31m[ERROR]\x1b[0m {msg}\r\n")
        self.console.update()

    def on_closed(self):
        self._title_bar.set_closed()
        self.term.process("\r\n\x1b[90m[SESSION CLOSED]\x1b[0m\r\n")
        self.console.update()

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
            self.worker.wait()
        event.accept()

# ───────────────────────────────────────────────
# Session Log
# ───────────────────────────────────────────────
class SessionLog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Log")
        self.resize(800, 500)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Time", "Device", "Command", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        export_btn = QPushButton("Export CSV")
        clear_btn.clicked.connect(lambda: self.table.setRowCount(0))
        export_btn.clicked.connect(self._export)
        btn_row.addStretch()
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(export_btn)
        layout.addLayout(btn_row)
        self.update_theme()

    def add(self, device, cmd, status):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(datetime.now().strftime("%H:%M:%S")))
        self.table.setItem(r, 1, QTableWidgetItem(device))
        self.table.setItem(r, 2, QTableWidgetItem(cmd[:80]))
        item = QTableWidgetItem(status[:40])
        c = THEMES[current_theme]
        item.setForeground(QColor(c['success']) if status == "OK" else QColor(c['error']))
        self.table.setItem(r, 3, item)

    def update_theme(self):
        c = THEMES[current_theme]
        self.setStyleSheet(f"""
            QDialog {{ background:{c['bg']}; }}
            QTableWidget {{ background:{c['input']}; color:{c['fg']}; gridline-color:{c['border']}; border:none; font-family:Consolas; font-size:11px; }}
            QHeaderView::section {{ background:{c['alt_base']}; color:{c['meta']}; border:1px solid {c['border']}; padding:6px; }}
            QPushButton {{ background:{c['button']}; color:{c['button_text']}; border:1px solid {c['border']}; padding:6px 16px; border-radius:4px; }}
            QPushButton:hover {{ background:{c['button_hover']}; color:{c['accent']}; }}
        """)
        
        succ = QColor(c['success'])
        err = QColor(c['error'])
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 3)
            if item:
                item.setForeground(succ if item.text() == "OK" else err)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "session_log.csv", "CSV (*.csv)")
        if path:
            with open(path, "w") as f:
                f.write("Time,Device,Command,Status\n")
                for r in range(self.table.rowCount()):
                    row = [self.table.item(r, c).text() for c in range(4)]
                    f.write(",".join(row) + "\n")

#-------------------AI worker thread for API calls----------------
class AIWorker(QThread):
    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, messages):
        super().__init__()
        self.messages = messages

    def run(self):
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            }
            data = {
                "model": "stepfun/step-3.5-flash:free",
                "messages": self.messages,
                "max_tokens": 1000
            }
            response = requests.post(AI_URL, headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content']
                self.result.emit(content)
            else:
                self.error.emit(f"API Error {response.status_code}: {response.text}")
        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _blend_hex(hex_color, alpha):
    """Alpha-blend hex_color toward black at 0-1 alpha. Always returns #rrggbb."""
    try:
        r, g, b = _hex_to_rgb(hex_color)
        return f"#{int(r*alpha):02x}{int(g*alpha):02x}{int(b*alpha):02x}"
    except Exception:
        return hex_color


def _inline(text, accent, input_bg, fg):
    """**bold** and `code` — _esc() must be called on text before this."""
    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: f"<b><font color='{accent}'>{m.group(1)}</font></b>",
        text,
    )
    text = re.sub(
        r"`([^`]+)`",
        lambda m: (
            f"<span style='background:{input_bg};border-radius:2px;"
            f"padding:0px 4px;font-family:Consolas,monospace;font-size:11px;'>"
            f"<font color='{accent}'>{m.group(1)}</font></span>"
        ),
        text,
    )
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Markdown
# ─────────────────────────────────────────────────────────────────────────────

def _render_ai_text(text, accent, card_bg, input_bg, border, fg, meta, code_store):
    """
    code_store: dict passed in from AIChatPanel — maps '#copy-N' → raw code text
    so the anchorClicked handler can copy the right block to clipboard.
    """

    try:
        mr, mg, mb = _hex_to_rgb(meta)
        div_line = f"#{min(255,int(mr*1.1)):02x}{min(255,int(mg*1.1)):02x}{min(255,int(mb*1.1)):02x}"
        num_col  = meta
    except Exception:
        div_line = num_col = meta

    lang_col = fg
    copy_col = _blend_hex(accent, 0.75)

    # ── Step 1: extract fenced code blocks ────────────────────────────────────
    slots = {}

    def pull_fence(m):
        raw_lang = (m.group(1) or "").strip().lower()
        label = {"": "code", "markdown": "text", "md": "text",
                 "plaintext": "text", "plain": "text"}.get(raw_lang, raw_lang)

        lines = (m.group(2) or "").split("\n")
        while lines and not lines[0].strip():  lines.pop(0)
        while lines and not lines[-1].strip(): lines.pop()

        # store raw text for clipboard copy
        raw_text = "\n".join(lines)
        slot_id  = f"@@SLOT{len(slots)}@@"
        copy_key = f"#copy-{len(slots)}"
        add_task_key = f"#add-task-{len(slots)}"
        code_store[copy_key] = raw_text
        code_store[add_task_key] = raw_text

        rows = ""
        for i, ln in enumerate(lines):
            safe = _esc(ln) if ln.strip() else "&nbsp;"
            rows += (
                f"<tr>"
                f"<td width='22' align='right' valign='top' "
                f"style='padding-right:8px;font-family:Consolas;font-size:10px;"
                f"line-height:1.6;'>"
                f"<font color='{num_col}'>{i+1}</font></td>"
                f"<td valign='top' style='font-family:Consolas;font-size:11px;"
                f"line-height:1.6;white-space:pre-wrap;word-wrap:break-word;'>"
                f"<font color='{fg}'>{safe}</font></td>"
                f"</tr>"
            )

        n = len(lines)

        slots[slot_id] = (
            f"<table width='100%' border='0' cellpadding='0' cellspacing='0' "
            f"style='margin:8px 0;border:1px solid {border};background:{input_bg};'>"

            # ── header bar: lang label left, copy link + line count right ────
            f"<tr><td style='padding:4px 10px;border-bottom:1px solid {border};'>"
            f"<table width='100%' border='0' cellpadding='0' cellspacing='0'><tr>"

            # lang label — uses fg so it's always readable
            f"<td><font color='{lang_col}' "
            f"style='font-family:Consolas;font-size:8px;letter-spacing:0.8px;'>"
            f"{label}</font></td>"

            # right side: line count  |  copy link
            f"<td align='right'>"
            f"<font color='{num_col}' style='font-family:Consolas;font-size:8px;'>"
            f"{n}&nbsp;line{'s' if n != 1 else ''}</font>"
            f"&nbsp;&nbsp;"
            f"<a href='{copy_key}' style='text-decoration:none;'>"
            f"<font color='{copy_col}' "
            f"style='font-family:Consolas;font-size:8px;letter-spacing:0.5px;'>"
            f"copy</font></a>"
            f"&nbsp;&nbsp;<font color='{div_line}'>|</font>&nbsp;&nbsp;"
            f"<a href='{add_task_key}' style='text-decoration:none;'>"
            f"<font color='{copy_col}' "
            f"style='font-family:Consolas;font-size:8px;letter-spacing:0.5px;'>"
            f"add to tasks</font></a>"
            f"</td>"

            f"</tr></table></td></tr>"

            # ── code rows ────────────────────────────────────────────────────
            f"<tr><td style='padding:7px 10px;'>"
            f"<table border='0' cellpadding='0' cellspacing='0' width='100%'>"
            f"{rows}</table></td></tr>"
            f"</table>"
        )
        return slot_id

    text = re.sub(r"```(\w*)[^\n]*\n(.*?)```", pull_fence, text, flags=re.DOTALL)

    # ── Step 2: line-by-line ──────────────────────────────────────────────────
    out = []
    for line in text.split("\n"):
        stripped = line.strip()

        if stripped in slots:
            out.append(slots[stripped])
            continue

        # ### h3
        m = re.match(r"^###\s+(.+)$", line)
        if m:
            content = _inline(_esc(m.group(1)), accent, input_bg, fg)
            out.append(
                f"<p style='margin:10px 0 3px;padding-bottom:4px;"
                f"border-bottom:1px solid {border};word-wrap:break-word;'>"
                f"<span style='font-family:Segoe UI,sans-serif;font-size:12px;"
                f"font-weight:600;'>"
                f"<font color='{fg}'>{content}</font></span></p>"
            )
            continue

        # ## h2
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            content = _inline(_esc(m.group(1)), accent, input_bg, fg)
            out.append(
                f"<p style='margin:12px 0 4px;padding-bottom:4px;"
                f"border-bottom:1px solid {div_line};word-wrap:break-word;'>"
                f"<span style='font-family:Segoe UI,sans-serif;font-size:12.5px;"
                f"font-weight:700;'>"
                f"<font color='{fg}'>{content}</font></span></p>"
            )
            continue

        # # h1
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            content = _inline(_esc(m.group(1)), accent, input_bg, fg)
            out.append(
                f"<p style='margin:14px 0 5px;padding-bottom:5px;"
                f"border-bottom:1px solid {div_line};word-wrap:break-word;'>"
                f"<span style='font-family:Segoe UI,sans-serif;font-size:13px;"
                f"font-weight:700;'>"
                f"<font color='{fg}'>{content}</font></span></p>"
            )
            continue

        # - / * bullet
        m = re.match(r"^[\-\*]\s+(.+)$", line)
        if m:
            content = _inline(_esc(m.group(1)), accent, input_bg, fg)
            out.append(
                f"<table border='0' cellpadding='0' cellspacing='0' "
                f"style='margin:1px 0;'><tr>"
                f"<td width='14' valign='top' "
                f"style='padding-top:3px;font-family:Consolas;font-size:8px;'>"
                f"<font color='{num_col}'>•</font></td>"
                f"<td style='font-family:Segoe UI,sans-serif;font-size:12px;"
                f"line-height:1.55;word-wrap:break-word;'>"
                f"<font color='{fg}'>{content}</font></td>"
                f"</tr></table>"
            )
            continue

        # 1. numbered
        m = re.match(r"^(\d+)\.\s+(.+)$", line)
        if m:
            content = _inline(_esc(m.group(2)), accent, input_bg, fg)
            out.append(
                f"<table border='0' cellpadding='0' cellspacing='0' "
                f"style='margin:1px 0;'><tr>"
                f"<td width='20' valign='top' align='right' "
                f"style='padding-right:6px;padding-top:3px;"
                f"font-family:Consolas;font-size:10px;'>"
                f"<font color='{num_col}'>{m.group(1)}.</font></td>"
                f"<td style='font-family:Segoe UI,sans-serif;font-size:12px;"
                f"line-height:1.55;word-wrap:break-word;'>"
                f"<font color='{fg}'>{content}</font></td>"
                f"</tr></table>"
            )
            continue

        # blank line
        if not stripped:
            out.append("<p style='margin:0;padding:2px 0;'></p>")
            continue

        # plain text
        content = _inline(_esc(line), accent, input_bg, fg)
        out.append(
            f"<p style='margin:0;padding:1px 0;font-family:Segoe UI,sans-serif;"
            f"font-size:12px;line-height:1.6;word-wrap:break-word;'>"
            f"<font color='{fg}'>{content}</font></p>"
        )

    result = "\n".join(out)
    for tag, block in slots.items():
        result = result.replace(tag, block)
    return result


# ───────────────────────────────────────────────
# Chat Input
# ───────────────────────────────────────────────
class ChatInput(QTextEdit):
    returnPressed = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return and not event.modifiers():
            self.returnPressed.emit()
        else:
            super().keyPressEvent(event)


# ───────────────────────────────────────────────
# AI Chat Panel
# ───────────────────────────────────────────────
class AIChatPanel(QWidget):
    tasks_updated = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = [{"role": "system", "content": "You are a helpful network engineering assistant. Keep responses concise and format code/config blocks appropriately using markdown."}]
        self._thinking_start = 0
        # maps '#copy-N' → raw code string for clipboard
        self._code_store = {}
        self._build()

    def _build(self):
        c = THEMES[current_theme]
        self.setStyleSheet(f"background: {c['alt_base']}; border-left: 1px solid {c['border']};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(46)
        hdr.setStyleSheet(f"background: {c['alt_base']}; border-bottom: 1px solid {c['border']};")
        hh = QHBoxLayout(hdr)
        hh.setContentsMargins(16, 0, 16, 0)
        hh.setSpacing(12)

        status = QLabel(" ● Ready ")
        status.setStyleSheet(f"""
            background: {c['accent']}1a;
            color: {c['accent']};
            border: 1px solid {c['accent']}40;
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 9px;
            font-family: Consolas;
        """)
        hh.addWidget(status)

        hh.addStretch()

        clear_btn = QPushButton("⟳ New Session")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {c['meta']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
                font-family: "Segoe UI";
            }}
            QPushButton:hover {{
                color: {c['accent']};
                border-color: {c['accent']};
                background: {c['base']};
            }}
        """)
        clear_btn.clicked.connect(self._clear_history)
        hh.addWidget(clear_btn)

        layout.addWidget(hdr)

        # Chat Area
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(False)   # we handle all hrefs ourselves
        # anchorClicked fires for every <a href> click — used for copy
        self.chat_view.anchorClicked.connect(self._on_link_clicked)
        self.chat_view.setStyleSheet(f"""
            QTextBrowser {{
                background: {c['base']};
                color: {c['fg']};
                border: none;
                padding: 14px 16px;
                font-family: "Segoe UI";
                font-size: 12px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 4px;
                border: none;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {c['accent']}33;
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {c['accent']}66;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
        layout.addWidget(self.chat_view, 1)

        # Input Area
        inp_container = QWidget()
        inp_container.setStyleSheet(f"background: {c['alt_base']}; border-top: 1px solid {c['border']};")
        iv = QVBoxLayout(inp_container)
        iv.setContentsMargins(12, 31, 12, 31)
        iv.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)

        self.inp = ChatInput()
        self.inp.returnPressed.connect(self._send)
        self.inp.setPlaceholderText("Ask about your network...")
        self.inp.setFixedHeight(50)
        self.inp.setStyleSheet(f"""
            QTextEdit {{
                background: {c['input']};
                color: {c['input_text']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 10px;
                font-family: "Segoe UI";
                font-size: 13px;
            }}
            QTextEdit:focus {{ border: 1px solid {c['accent']}; }}
        """)
        row.addWidget(self.inp)

        send_btn = QPushButton("↑")
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setFixedSize(50, 50)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {c['accent']};
                border: 1px solid {c['accent']}66;
                border-radius: 8px;
                font-size: 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {c['accent']};
                color: {c['bg']};
            }}
        """)
        send_btn.clicked.connect(self._send)
        row.addWidget(send_btn)

        iv.addLayout(row)
        layout.addWidget(inp_container)

        self._append_html(f"<div style='color:{c['meta']}; text-align:center; margin-top:16px; font-family:Consolas; font-size:9px; letter-spacing:1px;'>YOUR AI NETWORK ASSISTANT IS READY</div>")

    def _show_status_feedback(self, text, level="info"):
        c = THEMES[current_theme]
        
        color_map = {
            "info": c['accent'],
            "success": c['success'],
            "error": c['error']
        }
        color = color_map.get(level, c['accent'])
        
        for child in self.findChildren(QLabel):
            if "Ready" in child.text() or "COPIED" in child.text() or "SAVED" in child.text():
                original_text = " ● Ready "
                child.setText(text)
                child.setStyleSheet(f"""
                    background: {color}22;
                    color: {color};
                    border: 1px solid {color}66;
                    border-radius: 10px;
                    padding: 2px 8px;
                    font-size: 9px;
                    font-family: Consolas;
                """)
                QTimer.singleShot(1500, lambda: (
                    child.setText(original_text),
                    child.setStyleSheet(f"""
                        background: {c['accent']}1a;
                        color: {c['accent']};
                        border: 1px solid {c['accent']}40;
                        border-radius: 10px;
                        padding: 2px 8px;
                        font-size: 9px;
                        font-family: Consolas;
                    """)
                ))
                break

    # ── copy handler — fires when any <a href> is clicked in the chat view ────
    def _on_link_clicked(self, url):
        key = url.toString()
        if key.startswith("#copy-") and key in self._code_store:
            QApplication.clipboard().setText(self._code_store[key])
            self._show_status_feedback("✓ COPIED", "info")
        elif key.startswith("#add-task-") and key in self._code_store:
            code_to_add = self._code_store[key]
            task_name, ok = QInputDialog.getText(self, "Add to Task Library", "Enter a name for the new task:", QLineEdit.EchoMode.Normal, "new-ai-task")
            if ok and task_name:
                task_name = task_name.strip().replace(" ", "-")
                if task_name in Tasks:
                    reply = QMessageBox.question(self, "Task Exists", f"A task named '{task_name}' already exists. Overwrite it?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                    if reply == QMessageBox.StandardButton.No:
                        return
                Tasks[task_name] = code_to_add
                save_config()
                self.tasks_updated.emit()
                self._show_status_feedback("✓ SAVED", "success")

    def _clear_history(self):
        self.messages = [{"role": "system", "content": "You are a helpful network engineering assistant. Keep responses concise and format code/config blocks appropriately using markdown."}]
        self.chat_view.clear()
        self._code_store.clear()
        c = THEMES[current_theme]
        self._append_html(f"<div style='color:{c['meta']}; text-align:center; margin-top:16px; font-family:Consolas; font-size:9px; letter-spacing:1px;'>AI ASSISTANT READY</div>")

    def _send(self):
        txt = self.inp.toPlainText().strip()
        if not txt: return

        self._append_msg("You", txt, True)
        self.inp.setFixedHeight(50)
        self.inp.clear()
        self.inp.setDisabled(True)

        cursor = self.chat_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._thinking_start = cursor.position()

        self._append_thinking_indicator()
        self.messages.append({"role": "user", "content": txt})

        self.worker = AIWorker(self.messages)
        self.worker.result.connect(self._on_ai_reply)
        self.worker.error.connect(self._on_ai_error)
        self.worker.finished.connect(lambda: self.inp.setDisabled(False))
        self.worker.finished.connect(lambda: self.inp.setFocus())
        self.worker.start()

    def _on_ai_reply(self, text):
        self._remove_last_message()
        self.messages.append({"role": "assistant", "content": text})
        self._append_msg("AI Assistant", text, False)

    def _on_ai_error(self, err):
        self._remove_last_message()
        self._append_msg("System", f"I'm having trouble connecting. Please check your internet connection and API key.\n<br><small style='color:{THEMES[current_theme]['meta']};'>Details: {err}</small>", False, is_error=True)

    def restore_history(self, messages):
        self.messages = messages
        self._code_store.clear()
        self.chat_view.clear()
        c = THEMES[current_theme]
        self._append_html(f"<div style='color:{c['meta']}; text-align:center; margin-top:16px;'><i>AI Assistant Ready (History Restored)</i></div>")
        for msg in self.messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user":
                self._append_msg("You", content, True)
            elif role == "assistant":
                self._append_msg("AI Assistant", content, False)

    def _append_thinking_indicator(self):
        c = THEMES[current_theme]
        accent = c['accent']
        border = c['border']
        html = f"""
        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">
        <tr>
            <td width="26" valign="top" align="center">
                <div style="border:1px solid {border};border-radius:4px;
                            padding:3px 4px;font-family:Consolas;font-size:9px;
                            letter-spacing:2px;text-align:center;">
                    <font color="{c['meta']}">&middot;&middot;&middot;</font>
                </div>
            </td>
            <td width="8"></td>
            <td align="left" valign="top">
                <div style="font-size:8px;font-family:Consolas;margin-bottom:3px;
                            font-weight:bold;letter-spacing:1.2px;">
                    <font color="{accent}"> AI </font>
                </div>
                <div style="background:{c['card_bg']};border:1px solid {border};
                            padding:8px 12px;border-radius:3px 6px 6px 6px;
                            font-family:'Segoe UI',sans-serif;font-size:12px;
                            font-style:italic;">
                    <font color="{c['meta']}">Thinking...</font>
                </div>
            </td>
        </tr>
        </table>
        """
        self._append_html(html)

    def _remove_last_message(self):
        if self._thinking_start > 0:
            cursor = self.chat_view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.setPosition(self._thinking_start, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()

    def _append_msg(self, sender, text, is_user, is_error=False):
        c = THEMES[current_theme]
        accent   = c['accent']
        fg       = c['fg']
        meta     = c['meta']
        card_bg  = c['card_bg']
        input_bg = c['input']
        border   = c['border']

        if is_error:
            safe = text.replace(chr(10), "<br>")
            html = f"""
            <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">
            <tr>
                <td align="right" valign="top">
                    <div style="font-size:8px;font-family:Consolas;margin-bottom:3px;
                                font-weight:bold;letter-spacing:1.2px;">
                        <font color="{accent}">YOU</font>
                    </div>
                    <div style="background:{c['highlight']};
                                border:1px solid {c['error']};
                                padding:8px 12px;border-radius:6px 3px 6px 6px;
                                font-family:'Segoe UI',sans-serif;font-size:12px;
                                line-height:1.55;word-wrap:break-word;">
                        <font color="{fg}">{safe}</font>
                    </div>
                </td>
                <td width="8"></td>
                <td width="26" valign="top" align="center">
                    <div style="border:1px solid {c['error']};border-radius:4px;
                                padding:3px 4px;text-align:center;">
                        <font color="{c['error']}" style="font-size:10px;">!</font>
                    </div>
                </td>
            </tr>
            </table>
            """

        elif not is_user:
            body = _render_ai_text(
                text, accent, card_bg, input_bg, border, fg, meta,
                self._code_store   # pass store so copy links are registered
            )
            html = f"""
            <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">
            <tr>
                <td width="26" valign="top" align="center">
                    <div style="border:1px solid {border};border-radius:4px;
                                padding:3px 4px;text-align:center;">
                        <font color="{accent}" style="font-size:11px;">✦</font>
                    </div>
                </td>
                <td width="8"></td>
                <td align="left" valign="top">
                    <div style="font-size:8px;font-family:Consolas;margin-bottom:3px;
                                font-weight:bold;letter-spacing:1.2px;">
                        <font color="{accent}"> AI </font>
                    </div>
                    <div style="background:{card_bg};border:1px solid {border};
                                padding:10px 13px;border-radius:3px 6px 6px 6px;
                                font-family:'Segoe UI',sans-serif;font-size:12px;
                                line-height:1.6;word-wrap:break-word;">
                        {body}
                    </div>
                </td>
            </tr>
            </table>
            """

        else:
            safe = _esc(text).replace(chr(10), "<br>")
            html = f"""
            <table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">
            <tr>
                <td align="right" valign="top">
                    <div style="font-size:8px;font-family:Consolas;margin-bottom:3px;
                                font-weight:bold;letter-spacing:1.2px;">
                        <font color="{accent}">YOU</font>
                    </div>
                    <div style="background:{card_bg};border:1px solid {border};
                                padding:8px 12px;border-radius:6px 3px 6px 6px;
                                font-family:'Segoe UI',sans-serif;font-size:12px;
                                line-height:1.55;word-wrap:break-word;">
                        <font color="{fg}">{safe}</font>
                    </div>
                </td>
                <td width="8"></td>
                <td width="26" valign="top" align="center">
                    <div style="border:1px solid {border};border-radius:4px;
                                padding:3px 4px;text-align:center;">
                        <font color="{accent}" style="font-size:11px;">◇</font>
                    </div>
                </td>
            </tr>
            </table>
            """

        self._append_html(html)

    def _append_html(self, html):
        self.chat_view.append(html)
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())


# ───────────────────────────────────────────────
# Main Window
# ───────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NSTX — Smart Terminal ")
        self.resize(1600, 900)
        self._active_worker = None
        load_config()
        self._session_log = SessionLog(self)
        self._apply_theme()
        self._build_ui()
        self._build_menu()
        self._device_panel.rebuild()
        self._update_sel_label()
        self._refresh_quick_toolbar()
        self._refresh_Tasks()

        # Clock
        self._clock = QTimer()
        self._clock.timeout.connect(self._tick)
        self._clock.start(1000)

    # ── Theme ──────────────────────────────────────────────
    def _apply_theme(self):
        c = THEMES[current_theme]
        self.setStyleSheet(f"""
        * {{ font-family: "Segoe UI", sans-serif; }}
        QMainWindow {{ background: {c['bg']}; }}
        QMenuBar {{ background: {c['bg']}; color: {c['meta']}; border-bottom: 1px solid {c['border']}; padding: 2px; }}
        QMenuBar::item:selected {{ background: {c['border']}; color: {c['accent']}; }}
        QMenu {{ background: {c['base']}; color: {c['fg']}; border: 1px solid {c['border']}; }}
        QMenu::item {{ padding: 6px 24px; }}
        QMenu::item:selected {{ background: {c['highlight']}; color: {c['accent']}; }}
        QMenu::separator {{ background: {c['border']}; height: 1px; margin: 3px 0; }}
        QSplitter::handle {{ background: {c['border']}; }}
        QStatusBar {{ background: {c['bg']}; color: {c['meta']}; border-top: 1px solid {c['border']}; }}
        QToolTip {{ background: {c['base']}; color: {c['fg']}; border: 1px solid {c['border']}; padding: 4px; }}
        """)
        
        # Palette for standard widgets
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(c['bg']))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(c['fg']))
        palette.setColor(QPalette.ColorRole.Base, QColor(c['base']))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c['alt_base']))
        palette.setColor(QPalette.ColorRole.Text, QColor(c['fg']))
        palette.setColor(QPalette.ColorRole.Button, QColor(c['button']))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(c['button_text']))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(c['highlight']))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(c['accent']))
        QApplication.instance().setPalette(palette)

    # ── Menu ───────────────────────────────────────────────
    def _build_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("File")
        fm.addAction("Import Devices (JSON)").triggered.connect(self._import)
        fm.addAction("Export Devices (JSON)").triggered.connect(self._export)
        fm.addSeparator()
        fm.addAction("Exit").triggered.connect(self.close)

        dm = mb.addMenu("Devices")
        dm.addAction("Add Device  Ctrl+N").triggered.connect(self._add_device)
        dm.addAction("Ping Selected").triggered.connect(lambda: self._ping("sel"))
        dm.addAction("Ping All").triggered.connect(lambda: self._ping("all"))
        dm.addSeparator()
        dm.addAction("Select All  Ctrl+A").triggered.connect(self._device_panel.select_all)
        dm.addAction("Deselect All  Esc").triggered.connect(self._device_panel.deselect_all)
        dm.addSeparator()
        dm.addAction("Remove Selected").triggered.connect(self._remove_selected)
        dm.addAction("Clear All Devices").triggered.connect(self._clear_all)

        tm = mb.addMenu("Tools")
        tm.addAction("Task Library").triggered.connect(self._open_Tasks)
        tm.addAction("Config Share").triggered.connect(self._open_config_share)
        tm.addAction("Normal SSH Terminal").triggered.connect(self._open_normal_ssh)
        tm.addAction("Change Theme ").triggered.connect(self.toggle_theme)
        tm.addAction("Session Log").triggered.connect(self._session_log.show)
        tm.addSeparator()
        tm.addAction("Clear Console  Ctrl+L").triggered.connect(self._console.clear)

        self._qc_menu = mb.addMenu("Quick Commands")
        self._refresh_qc_menu()

    def _refresh_qc_menu(self):
        self._qc_menu.clear()
        self._qc_menu.addAction("Manage Commands...").triggered.connect(self.manage_quick_commands)
        self._qc_menu.addSeparator()
        for item in quick_commands:
            self._qc_menu.addAction(f"{item['label']} ({item['cmd']})").triggered.connect(
                lambda c=False, x=item['cmd']: self._fire(x)
            )

    def manage_quick_commands(self):
        dlg = QuickCmdDialog(self)
        dlg.exec()
        save_config()
        self._refresh_qc_menu()
        self._refresh_quick_toolbar()

    # ── UI Build ───────────────────────────────────────────
    def _build_ui(self):
        # Cleanup old shortcuts to prevent duplication/GC issues
        if hasattr(self, "_shortcuts"):
            for s in self._shortcuts: s.setParent(None)
        self._shortcuts = []

        c = THEMES[current_theme]
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── SIDEBAR (Formerly Left Panel) ─────────────────
        side_panel = QWidget()
        side_panel.setMinimumWidth(260)
        side_panel.setMaximumWidth(340)
        # Moved to left side -> use border-right
        side_panel.setStyleSheet(f"background: {c['bg']}; border-right: 1px solid {c['border']};")
        lv = QVBoxLayout(side_panel)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        # Brand header
        hdr = QWidget()
        hdr.setFixedHeight(64)
        hdr.setStyleSheet(f"background: {c['alt_base']}; border-bottom: 1px solid {c['border']};")
        hv = QVBoxLayout(hdr)
        hv.setContentsMargins(14, 8, 14, 8)
        title = QLabel("NSTX")
        title.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {c['accent']}; letter-spacing: 4px;")
        sub = QLabel("Future SSH Terminal")
        sub.setFont(QFont("Consolas", 8))
        sub.setStyleSheet(f"color: {c['meta']};")
        hv.addWidget(title)
        hv.addWidget(sub)
        lv.addWidget(hdr)

        # Search
        search_wrap = QWidget()
        search_wrap.setStyleSheet(f"background: {c['bg']}; border-bottom: 1px solid {c['border']};")
        sv = QHBoxLayout(search_wrap)
        sv.setContentsMargins(8, 6, 8, 6)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search devices...")
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {c['input']}; border: 1px solid {c['border']}; color: {c['input_text']};
                padding: 6px 10px; border-radius: 4px; font-family: Consolas; font-size: 11px;
            }}
            QLineEdit:focus {{ border-color: {c['accent']}; }}
        """)
        self._search.textChanged.connect(self._filter)
        sv.addWidget(self._search)
        lv.addWidget(search_wrap)

        # Device panel
        self._device_panel = DevicePanel()
        self._device_panel.selection_changed.connect(self._update_sel_label)
        self._device_panel.edit_requested.connect(self._edit_device)
        lv.addWidget(self._device_panel, 1)

        # Bottom toolbar
        bot = QWidget()
        bot.setFixedHeight(112)
        bot.setStyleSheet(f"background: {c['alt_base']}; border-top: 1px solid {c['border']};")
        bv = QGridLayout(bot)
        bv.setContentsMargins(8, 8, 8, 8)
        bv.setSpacing(4)

        def mk(label, color=c['button_text']):
            b = QPushButton(label)
            b.setStyleSheet(f"""
                QPushButton {{ background:{c['button']}; color:{color}; border:1px solid {c['border']};
                              padding:5px; border-radius:4px; font-size:11px; }}
                QPushButton:hover {{ background:{c['button_hover']}; color:{color}; border-color:{color}; }}
            """)
            return b

        btn_add = mk("+ Add Device", c['accent'])
        btn_sel = mk("Select All")
        btn_ping = mk("Ping", "#ffaa00")
        btn_del = mk("Remove", "#ff4455")
        btn_share = mk("⟳ Config Share", "#bb88ff")
        btn_add.clicked.connect(self._add_device)
        btn_sel.clicked.connect(self._device_panel.select_all)
        btn_ping.clicked.connect(lambda: self._ping("sel"))
        btn_del.clicked.connect(self._remove_selected)
        btn_share.clicked.connect(self._open_config_share)
        bv.addWidget(btn_add, 0, 0)
        bv.addWidget(btn_sel, 0, 1)
        bv.addWidget(btn_ping, 1, 0)
        bv.addWidget(btn_del, 1, 1)
        bv.addWidget(btn_share, 2, 0, 1, 2)  # spans full width
        lv.addWidget(bot)

        # ── RIGHT PANEL ───────────────────────────────────
        # ── TERMINAL CONTENT ──────────────────────────────
        term_splitter = QSplitter(Qt.Orientation.Horizontal)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        # Top toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(46)
        toolbar.setStyleSheet(f"background: {c['alt_base']}; border-bottom: 1px solid {c['border']};")
        tv = QHBoxLayout(toolbar)
        tv.setContentsMargins(12, 0, 12, 0)
        tv.setSpacing(6)

        self._sel_label = QLabel("No devices selected")
        self._sel_label.setStyleSheet(f"color: {c['meta']}; font-size: 11px; font-family: Consolas;")
        tv.addWidget(self._sel_label)
        tv.addStretch()

        # Quick cmd chips container
        self._qc_toolbar_layout = QHBoxLayout()
        self._qc_toolbar_layout.setSpacing(6)
        tv.addLayout(self._qc_toolbar_layout)

        tv.addSpacing(8)
        self._stop_btn = QPushButton("■ Stop")
        self._stop_btn.setFixedHeight(28)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet("""
            QPushButton { background:#1a0008; color:#ff4455; border:1px solid #440011;
                          padding:2px 12px; border-radius:4px; font-size:11px; }
            QPushButton:hover { background:#440011; border-color:#ff4455; }
            QPushButton:disabled { color:#555; border-color:#333; background:transparent; }
        """) # Keep stop button red/dark for visibility
        self._stop_btn.clicked.connect(self._stop)
        tv.addWidget(self._stop_btn)

        ai_btn = QPushButton("✤")
        ai_btn.setFixedSize(28, 28)
        ai_btn.setToolTip("Toggle AI Assistant")
        ai_btn.setStyleSheet(f"""
            QPushButton {{ background:{c['button']}; color:{c['accent']}; border:1px solid {c['border']}; border-radius:4px; font-size:14px; }}
            QPushButton:hover {{ background:{c['highlight']}; color:{c['accent']}; border-color:{c['accent']}; }}
        """)
        ai_btn.clicked.connect(lambda: self._chat_panel.setVisible(not self._chat_panel.isVisible()))
        tv.addWidget(ai_btn)

        clr = QPushButton("⌫")
        clr.setFixedSize(28, 28)
        clr.setToolTip("Clear console")
        clr.setStyleSheet(f"""
            QPushButton {{ background:{c['button']}; color:{c['meta']}; border:1px solid {c['border']}; border-radius:4px; }}
            QPushButton:hover {{ color:{c['error']}; border-color:{c['error']}; }}
        """)
        clr.clicked.connect(lambda: self._console.clear())
        tv.addWidget(clr)

        rv.addWidget(toolbar)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setMaximumHeight(3)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(f"""
            QProgressBar {{ background: {c['input']}; border: none; }}
            QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {c['accent']},stop:1 {c['highlight']}); }}
        """)
        rv.addWidget(self._progress)

        # Console
        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._console.setFont(QFont("Cascadia Code", 10))
        self._console.setStyleSheet(f"""
            QTextEdit {{
                background: {c['console']};
                color: {c['console_text']};
                border: none;
                padding: 12px;
                selection-background-color: {c['highlight']};
            }}
        """)
        self._console.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self._hl = TermHighlighter(self._console.document())
        rv.addWidget(self._console, 1)

        # Mode indicator + Task bar
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet(f"background: {c['alt_base']}; border-top: 1px solid {c['border']};")
        bb = QVBoxLayout(bottom_bar)
        bb.setContentsMargins(10, 6, 10, 6)
        bb.setSpacing(6)

        # Task row
        Task_row = QHBoxLayout()
        Task_lbl = QLabel("Task:")
        Task_lbl.setStyleSheet(f"color:{c['meta']}; font-size:10px; font-family:Consolas;")
        self._Task_combo = QComboBox()
        self._Task_combo.setFixedHeight(26)
        self._Task_combo.setStyleSheet(f"""
            QComboBox {{ background:{c['input']}; border:1px solid {c['border']}; color:{c['button_text']};
                        padding:2px 8px; border-radius:4px; font-family:Consolas; font-size:10px; }}
            QComboBox:hover {{ border-color:{c['accent']}; }}
            QComboBox QAbstractItemView {{ background:{c['input']}; color:{c['fg']}; border:1px solid {c['border']}; }}
        """)
        Task_run = QPushButton("▶ Run")
        Task_run.setFixedHeight(26)
        Task_run.setStyleSheet(f"""
            QPushButton {{ background:{c['button']}; color:{c['accent']}; border:1px solid {c['accent']};
                          padding:2px 12px; border-radius:4px; font-size:10px; }}
            QPushButton:hover {{ background:{c['accent']}; color:#000; }}
        """)
        Task_run.clicked.connect(self._run_Task)
        Task_edit = QPushButton("⚙")
        Task_edit.setFixedSize(26, 26)
        Task_edit.setStyleSheet(f"""
            QPushButton {{ background:{c['button']}; color:{c['meta']}; border:1px solid {c['border']}; border-radius:4px; }}
            QPushButton:hover {{ color:{c['accent']}; border-color:{c['accent']}; }}
        """)
        Task_edit.clicked.connect(self._open_Tasks)

        Task_row.addWidget(Task_lbl)
        Task_row.addWidget(self._Task_combo)
        Task_row.addWidget(Task_run)
        Task_row.addWidget(Task_edit)
        Task_row.addStretch()

        # Mode badge
        self._mode_badge = QLabel("EXEC MODE")
        self._mode_badge.setStyleSheet(f"""
            QLabel {{ color:{c['button_text']}; background:{c['input']}; border:1px solid {c['border']};
                     padding:2px 10px; border-radius:10px; font-size:10px;
                     font-family:Consolas; letter-spacing:1px; }}
        """)
        Task_row.addWidget(self._mode_badge)

        self._hint = QLabel("Enter  →  send exec cmd   |   conf t  →  auto-expands   |   ↑↓  history   |   Tab  →  autocomplete")
        self._hint.setStyleSheet(f"color: {c['meta']}; font-size: 10px; font-family: Consolas;")

        bb.addLayout(Task_row)

        # Command input row
        cmd_row = QHBoxLayout()
        cmd_row.setSpacing(6)

        self._prompt_lbl = QLabel("▸")
        self._prompt_lbl.setStyleSheet(f"color: {c['accent']}; font-size: 18px; padding: 0 4px;")
        self._prompt_lbl.setFixedWidth(22)

        self._input = SmartInputBox()
        self._input.send_requested.connect(self._on_send)
        self._input.mode_changed.connect(self._on_mode_change)
        self._input.dynamic_completion_requested.connect(self._on_dynamic_completion)

        cmd_row.addWidget(self._prompt_lbl)
        cmd_row.addWidget(self._input, 1)
        bb.addLayout(cmd_row)
        bb.addWidget(self._hint)

        rv.addWidget(bottom_bar)

        splitter.addWidget(right)
        term_splitter.addWidget(right)
        
        # ── AI CHAT PANEL ─────────────────────────────────
        self._chat_panel = AIChatPanel()
        self._chat_panel.tasks_updated.connect(self._refresh_Tasks)
        splitter.addWidget(self._chat_panel)
        term_splitter.addWidget(self._chat_panel)
        self._chat_panel.hide()
        
        splitter.setSizes([280, 1000, 320])
        # Wrap splitter + autopilot in a QTabWidget
        term_splitter.setSizes([1000, 320])

        # Wrap terminal splitter + autopilot in a QTabWidget
        self._main_tabs = QTabWidget()
        self._main_tabs.setTabPosition(QTabWidget.TabPosition.South)
        self._main_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {c['bg']}; }}
            QTabBar::tab {{
                background: {c['alt_base']}; color: {c['meta']};
                padding: 4px 12px; border-top: 1px solid {c['border']};
                font-family: Consolas; font-size: 10px; letter-spacing: 1px;
            }}
            QTabBar::tab:selected {{
                color: {c['accent']}; border-top: 2px solid {c['accent']};
                background: {c['bg']};
            }}
            QTabBar::tab:hover {{ color: {c['fg']}; }}
        """)
        self._main_tabs.addTab(term_splitter, " Terminal  ")
        self._autopilot_panel = AutopilotPanel(devices, API_KEY, AI_URL, theme=current_theme)
        self._main_tabs.addTab(self._autopilot_panel, "Autopilot  ")
        
        # Add Sidebar (left) and Tabs (right) to main splitter
        main_splitter.addWidget(side_panel)
        main_splitter.addWidget(self._main_tabs)
        main_splitter.setSizes([300, 1300])
        root.addWidget(main_splitter)

        # Status bar
        self.setStatusBar(QStatusBar())
        self._status = QLabel("Ready")
        self._status.setStyleSheet(f"color: {c['meta']}; padding: 0 8px;")
        self._clock_lbl = QLabel()
        self._clock_lbl.setStyleSheet(f"color: {c['accent']}; padding: 0 8px;")
        self.statusBar().addWidget(self._status)
        self.statusBar().addPermanentWidget(self._clock_lbl)
        self.statusBar().setStyleSheet(f"background: {c['alt_base']}; border-top: 1px solid {c['border']};")

        # Shortcuts
        def add_sh(seq, func):
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(func)
            self._shortcuts.append(s)

        add_sh("Ctrl+N", self._add_device)
        add_sh("Ctrl+L", self._handle_clear)
        add_sh("Ctrl+A", self._device_panel.select_all)
        add_sh("Ctrl+Space", self._stop)

        self._refresh_Tasks()

    def toggle_theme(self):
        global current_theme
        current_theme = "light" if current_theme == "dark" else "dark"
        save_config()
        
        # Re-apply theme to main window
        self._apply_theme()
        self._session_log.update_theme()
        
        
        # Save state
        saved_search = self._search.text()
        saved_console = self._console.toPlainText()
        saved_history = self._chat_panel.messages if hasattr(self, "_chat_panel") and self._chat_panel.messages else []
        saved_chat_vis = self._chat_panel.isVisible() if hasattr(self, "_chat_panel") else False
        
        # Rebuild UI
        self._build_ui()
        
        # Restore state
        self._search.setText(saved_search)
        self._console.setPlainText(saved_console)
        self._console.moveCursor(QTextCursor.MoveOperation.End)
        self._device_panel.rebuild(saved_search)
        self._update_sel_label()
        self._refresh_quick_toolbar()
        self._refresh_Tasks()
        
        if hasattr(self, "_chat_panel"):
            if saved_history:
                self._chat_panel.restore_history(saved_history)
            if saved_chat_vis:
                self._chat_panel.show()

    def _refresh_quick_toolbar(self):
        c = THEMES[current_theme]
        # Clear existing
        while self._qc_toolbar_layout.count():
            child = self._qc_toolbar_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Add new
        for item in quick_commands:
            b = QPushButton(item['label'])
            b.setFixedHeight(28)
            b.setToolTip(item['cmd'])
            b.setStyleSheet(f"""
                QPushButton {{ background:{c['button']}; color:{c['meta']}; border:1px solid {c['border']};
                              padding:2px 10px; border-radius:12px; font-family:Consolas; font-size:10px; }}
                QPushButton:hover {{ background:{c['button_hover']}; color:{c['accent']}; border-color:{c['accent']}; }}
            """)
            b.clicked.connect(lambda c=False, x=item['cmd']: self._fire(x))
            self._qc_toolbar_layout.addWidget(b)

    # ── Event Handlers ─────────────────────────────────────

    def _on_send(self, text):
        # Autocomplete hint
        if text.startswith("__autocomplete__:"):
            completions = text.split(":")[1].split(",")
            self._console.append(f"\n  [TAB]  {' | '.join(completions)}")
            return

        if not selected_indexes:
            QMessageBox.warning(self, "No Selection",
                "Please select at least one device from the left panel.")
            return

        self._console.append(
            f"\n[{datetime.now().strftime('%H:%M:%S')}]  ▸  {text[:80]}"
            f"{'...' if len(text) > 80 else ''}  →  {len(selected_indexes)} device(s)"
        )

        idxs = sorted(selected_indexes)  # copy - selection stays!
        self._progress.setVisible(True)
        self._progress.setMaximum(len(idxs))
        self._progress.setValue(0)
        self._stop_btn.setEnabled(True)

        w = SSHWorker(idxs, text)
        self._active_worker = w
        workers.append(w)

        w.out.connect(self._console.append)
        w.refresh.connect(self._device_panel.refresh_cards)
        w.progress.connect(lambda cur, tot: (
            self._progress.setValue(cur),
            self._status.setText(f"Executing on {cur}/{tot} device(s)...")
        ))
        w.log_entry.connect(self._session_log.add)

        def done():
            if w in workers:
                workers.remove(w)
            self._progress.setVisible(False)
            self._stop_btn.setEnabled(False)
            self._active_worker = None
            self._status.setText("Ready")
            # Scroll console to bottom
            self._console.moveCursor(QTextCursor.MoveOperation.End)

        w.finished.connect(done)
        w.start()
        self._status.setText(f"Running: {text[:50]}...")

    def _on_dynamic_completion(self, partial_text):
        # Only works if exactly one device is selected (to avoid ambiguity)
        if len(selected_indexes) != 1:
            self._input.show_static_completions()
            return
        
        idx = next(iter(selected_indexes))
        d = devices[idx]
        if not d.get("connected"):
            self._input.show_static_completions()
            return

        # Start worker to fetch completions
        self._ac_worker = AutoCompleteWorker(idx, partial_text)
        self._ac_worker.results_ready.connect(self._input.show_dynamic_completions)
        self._ac_worker.finished.connect(lambda: setattr(self, "_ac_worker", None))
        self._ac_worker.start()

    def _on_mode_change(self, mode):
        c = THEMES[current_theme]
        labels = {
            "config": ("CONFIG MODE", "#bb88ff", c['bg']),
            "show":   ("SHOW MODE",   c['accent'], c['bg']),
            "exec":   ("EXEC MODE",   c['meta'], c['bg']),
            "special_save": ("SAVE", "#00ff88", "#001a0f"),
        }
        label, color, bg = labels.get(mode, ("EXEC MODE", "#7a9fc0", "#0d1117"))
        self._mode_badge.setText(label)
        self._mode_badge.setStyleSheet(f"""
            QLabel {{ color:{color}; background:{bg}; border:1px solid {color}44;
                     padding:2px 10px; border-radius:10px; font-size:10px;
                     font-family:Consolas; letter-spacing:1px; }}
        """)
        self._prompt_lbl.setStyleSheet(f"color: {color}; font-size: 18px; padding: 0 4px;")

    def _fire(self, cmd):
        self._input.setPlainText(cmd)
        self._on_send(cmd)
        self._input.clear()

    def _handle_clear(self):
        if self._main_tabs.currentIndex() == 1:
            if hasattr(self._autopilot_panel, "clear_session"):
                self._autopilot_panel.clear_session()
        else:
            self._console.clear()

    def _stop(self):
        if self._active_worker:
            self._active_worker.stop()

    def _filter(self, text):
        self._device_panel.rebuild(filter_text=text)

    def _update_sel_label(self):
        n = len(selected_indexes)
        if n == 0:
            self._sel_label.setText("No devices selected  —  click to select")
        elif n == 1:
            idx = next(iter(selected_indexes))
            d = devices[idx]
            name = d.get("hostname") or d["host"]
            self._sel_label.setText(f"●  {name}")
        else:
            self._sel_label.setText(f"●  {n} devices selected")

    # ── Device CRUD ────────────────────────────────────────

    def _add_device(self):
        dlg = DeviceDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if not data["host"] or not data["username"]:
                QMessageBox.warning(self, "Error", "IP and username required.")
                return
            devices.append(data)
            save_config()
            self._device_panel.rebuild(self._search.text())
            self._update_sel_label()

    def _edit_device(self, idx):
        if idx < 0 or idx >= len(devices):
            return

        old_device = devices[idx]
        dlg = DeviceDialog(self, data=old_device)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Invalidate any existing persistent session for this device.
            # This forces a reconnect with the new credentials on the next command.
            sess_key = f"{old_device['host']}:{old_device.get('port', 22)}:{old_device.get('username','')}"
            if sess_key in device_sessions:
                try:
                    device_sessions[sess_key].disconnect()
                except Exception:
                    pass  # Ignore errors on disconnect
                del device_sessions[sess_key]

            data = dlg.get_data()
            data["connected"] = old_device.get("connected", False)
            devices[idx] = data
            save_config()
            self._device_panel.rebuild(self._search.text())

    def _remove_selected(self):
        if not selected_indexes:
            return
        for idx in sorted(selected_indexes, reverse=True):
            if 0 <= idx < len(devices):
                devices.pop(idx)
        selected_indexes.clear()
        save_config()
        self._device_panel.rebuild(self._search.text())
        self._update_sel_label()

    def _clear_all(self):
        if QMessageBox.question(self, "Confirm", "Remove all devices?") == QMessageBox.StandardButton.Yes:
            devices.clear()
            selected_indexes.clear()
            save_config()
            self._device_panel.rebuild()
            self._update_sel_label()

    # ── Ping ───────────────────────────────────────────────

    def _ping(self, mode):
        idxs = list(range(len(devices))) if mode == "all" else sorted(selected_indexes)
        if not idxs:
            return
        self._console.append(f"\n[{datetime.now().strftime('%H:%M:%S')}]  Pinging {len(idxs)} device(s)...")
        w = PingWorker(idxs)
        workers.append(w)
        w.result.connect(self._on_ping)
        w.finished.connect(lambda: workers.remove(w) if w in workers else None)
        w.start()

    def _on_ping(self, idx, alive, rtt):
        d = devices[idx]
        name = d.get("hostname") or d["host"]
        if alive:
            self._console.append(f"  [OK] {name} ({d['host']})  {rtt:.0f}ms")
        else:
            self._console.append(f"  [ERROR] {name} ({d['host']})  unreachable")
        self._device_panel.refresh_cards()
        self._update_sel_label()

    # ── Tasks ─────────────────────────────────────────────

    def _refresh_Tasks(self):
        self._Task_combo.clear()
        self._Task_combo.addItem("(select Task)")
        for name in Tasks:
            self._Task_combo.addItem(name)

    def _run_Task(self):
        name = self._Task_combo.currentText()
        if name not in Tasks:
            return
        if not selected_indexes:
            QMessageBox.warning(self, "No Selection", "Select devices first.")
            return
        body = Tasks[name]
        # Run as a config block
        self._on_send(body)

    def _open_Tasks(self):
        dlg = TaskEditor(self)
        dlg.exec()
        self._refresh_Tasks()

    def _open_config_share(self):
        dlg = ConfigShareDialog(self, console_cb=self._console.append)
        dlg.exec()
        self._device_panel.refresh_cards()

    def _open_normal_ssh(self):
        if not selected_indexes:
            QMessageBox.warning(self, "No Selection", "Select a device first.")
            return
        idx = next(iter(selected_indexes))
        
        if not hasattr(self, "_ssh_windows"):
            self._ssh_windows = []
        
        # Filter out deleted/closed windows safely
        valid_windows = []
        for w in self._ssh_windows:
            try:
                if w.isVisible(): valid_windows.append(w)
            except RuntimeError: pass
        self._ssh_windows = valid_windows
        
        win = NormalSSHDialog(idx)
        win.show()
        self._ssh_windows.append(win)

    # ── Import / Export ────────────────────────────────────

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            count = 0
            for d in data:
                d.setdefault("connected", False)
                d.setdefault("hostname", None)
                d.setdefault("tags", [])
                d.setdefault("notes", "")
                d.setdefault("secret", "")
                d.setdefault("port", 22)
                devices.append(d)
                count += 1
            save_config()
            self._device_panel.rebuild(self._search.text())
            QMessageBox.information(self, "Imported", f"Imported {count} device(s).")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "devices.json", "JSON (*.json)")
        if not path:
            return
        try:
            safe = [{k: v for k, v in d.items() if k != "connected"} for d in devices]
            with open(path, "w") as f:
                json.dump(safe, f, indent=2)
            QMessageBox.information(self, "Exported", f"Exported {len(devices)} device(s).")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Clock ──────────────────────────────────────────────

    def _tick(self):
        self._clock_lbl.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    # ── Close ──────────────────────────────────────────────

    def closeEvent(self, event):
        save_config()
        for w in list(workers):
            w.wait()
        # Close persistent sessions
        for k, conn in device_sessions.items():
            try: conn.disconnect()
            except: pass
        event.accept()


# ───────────────────────────────────────────────
# ENTRY POINT
# ───────────────────────────────────────────────
if __name__ == "__main__":
    # Set AppUserModelID early for Windows taskbar grouping
    try:
        myapp = 'NSTX.Smart_Terminal.v4'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myapp)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("NSTX")
    
    # Use dynamic path for icon to avoid syntax errors and hardcoded paths
    icon_path = resource_path("icon.ico")
    
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        print(f"Warning: Icon file not found at {icon_path}")
    
    app.setStyle("Fusion")

    # Dark fusion palette base
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#070a0f"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#c8d6e5"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#0d1117"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#0a1018"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#c8d6e5"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#0d1117"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#c8d6e5"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#1e3a5f"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#00d4ff"))
    app.setPalette(palette)

    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())
