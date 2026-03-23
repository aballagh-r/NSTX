from __future__ import annotations
import re, json, time, requests, subprocess, platform
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit,
)
from PyQt6.QtCore  import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui   import QFont, QFontInfo, QColor, QTextCursor, QTextCharFormat


try:
    from __main__ import (
        device_sessions, Tasks, workers,
        SmartConfigParser, Vendor, save_config, devices, selected_indexes
    )
except ImportError:
    devices = []; selected_indexes = set(); device_sessions = {}; Tasks = {}; workers = []
    def save_config(): pass
    class Vendor:
        CISCO_IOS = "cisco_ios"; GENERIC = "generic"
        def __init__(self, v): pass
    class SmartConfigParser:
        def __init__(self, v): pass
        def extract_config_lines(self, t):
            return [l.strip() for l in t.splitlines() if l.strip()]

# ═══════════════════════════════════════════════════════════════════════════════
#  DESIGN TOKENS
# ═══════════════════════════════════════════════════════════════════════════════
C_LIGHT = {
    "bg":           "#FFFFFF",
    "panel":        "#F0F4F8",
    "panel2":       "#E8EDF2",
    "bar_bg":       "#F5F7FA",
    "border":       "#DDE3EB",
    "border2":      "#C8D0DA",
    "teal":         "#2196b6",
    "teal_light":   "#E3F4F8",
    "teal_dim":     "#1a7a96",
    "teal_text":    "#FFFFFF",
    "green":        "#22c55e",
    "red":          "#ef4444",
    "yellow":       "#f59e0b",
    "orange":       "#f97316",
    "text":         "#1a2332",
    "text_mid":     "#4a5568",
    "text_dim":     "#8a95a3",
    "text_hi":      "#000000",
    "sel_bg":       "#E3F4F8",
    "sev_critical": "#ef4444",
    "sev_high":     "#f97316",
    "sev_medium":   "#f59e0b",
    "sev_low":      "#2196b6",
    "sev_healthy":  "#22c55e",
}

C_DARK = {
    "bg":           "#0d1117", "panel":        "#070a0f", "panel2":       "#161b22",
    "bar_bg":       "#0a1018", "border":       "#1e2a3a", "border2":      "#30363d",
    "teal":         "#00d4ff", "teal_light":   "#1e3a5f", "teal_dim":     "#0088cc",
    "teal_text":    "#000000", "green":        "#00ff88", "red":          "#ff4455",
    "yellow":       "#ffaa00", "orange":       "#ff8800", "text":         "#c8d6e5",
    "text_mid":     "#8b949e", "text_dim":     "#484f58", "text_hi":      "#ffffff",
    "sel_bg":       "#1e3a5f", "sev_critical": "#ff4455", "sev_high":     "#ffaa00",
    "sev_medium":   "#ffcc00", "sev_low":      "#00d4ff", "sev_healthy":  "#00ff88",
}

C = C_LIGHT.copy()

SEV = {
    "critical": (C["sev_critical"], "CRITICAL"),
    "high":     (C["sev_high"],     "HIGH    "),
    "medium":   (C["sev_medium"],   "MEDIUM  "),
    "low":      (C["sev_low"],      "LOW     "),
    "healthy":  (C["sev_healthy"],  "HEALTHY "),
}

SANS = "'Segoe UI', 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif"
MONO = "'Cascadia Code', 'Cascadia Mono', 'Consolas', 'Lucida Console', monospace"

# ═══════════════════════════════════════════════════════════════════════════════
#  MODEL AUTO-SELECTION
# ═══════════════════════════════════════════════════════════════════════════════
_FALLBACK_CHAIN = [
    "stepfun/step-3.5-flash:free",
    "openrouter/free",
]

_MODEL_SCORES = {
    "stepfun/step-3.5-flash:free":         100,
    "openrouter/free":                      90,
}

_MAX_COST_PER_1M = 5.0


def _fetch_best_model(api_key: str, ai_url: str) -> str:
    try:
        base = ai_url.rstrip("/")
        for suffix in ("/chat/completions", "/v1/chat/completions"):
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                break
        r = requests.get(
            f"{base}/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json().get("data", [])

        candidates = []
        for m in data:
            mid = m.get("id", "")
            if not mid:
                continue
            price = m.get("pricing", {})
            try:
                cost_per_1m = float(price.get("prompt", 0)) * 1_000_000
            except Exception:
                cost_per_1m = 0.0
            if cost_per_1m > _MAX_COST_PER_1M:
                continue
            score = _MODEL_SCORES.get(mid, 1)
            candidates.append((score, mid))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

    except Exception:
        pass

    return _FALLBACK_CHAIN[0]


class ModelSelector(QThread):
    ready = pyqtSignal(str)

    def __init__(self, api_key: str, ai_url: str):
        super().__init__()
        self.api_key = api_key
        self.ai_url  = ai_url

    def run(self):
        self.ready.emit(_fetch_best_model(self.api_key, self.ai_url))


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════
AGENT_SYSTEM = """\
You are NSTX Autopilot — an advanced AI network engineer.
You have DIRECT SSH ACCESS to the devices listed in the context.
Your goal is to complete the user's request using the available tools.

TOOLS AVAILABLE:
1. [READ]  `run_commands`: Run non-interactive show/display/exec commands.
2. [WRITE] `apply_fix`:    Run configuration changes or installation commands.
3. [REPORT] `summarise`:   End the session with a final report.

GUIDELINES:
- **Adaptability**: You are working with a variety of vendors (Cisco, Linux, Juniper, etc.). Check the device details in the context and use the correct syntax for that specific OS.
- **Action**: Do not just explain. Use tools to AUDIT state, APPLY changes, and VERIFY results.
- **Syntax**:
  - For Network devices (Cisco/Juniper/etc): `apply_fix` handles configuration mode automatically. Do NOT include 'configure terminal' or 'end'.
  - For Linux: `apply_fix` runs shell commands as root. Use non-interactive flags (e.g., -y).
- **Format**: Output MUST be strictly valid JSON inside <TOOL> tags.

TOOL FORMATS:
<TOOL>{"tool": "run_commands", "device": "<name|IP>", "commands": ["show ver"]}</TOOL>
<TOOL>{"tool": "apply_fix", "device": "<name|IP>", "commands": ["cmd1", "cmd2"], "risk": "low", "reason": "fixing issue"}</TOOL>
<TOOL>{"tool": "summarise", "severity": "healthy|low|medium|high|critical", "diagnosis": "Final conclusion.", "fix_applied": true}</TOOL>
"""

# ═══════════════════════════════════════════════════════════════════════════════
#  SSH HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
_CONFIG_MODE_COMMANDS = {
    "configure terminal", "configure", "conf t", "conf terminal",
    "end", "exit", "quit",
}

_CONFIG_PREFIXES = (
    "interface ", "int ", "ip address ", "ip route ", "ip nat ",
    "no ip ", "no interface", "encapsulation ", "router ",
    "vlan ", "switchport ", "spanning-tree", "service ", "hostname ",
    "username ", "enable secret", "enable password", "banner ",
    "crypto ", "access-list ", "ip access-list ", "ntp ",
    "logging ", "snmp-server ", "line vty", "line con",
)


def _is_config_command(cmd: str) -> bool:
    """Return True if cmd looks like a config-mode command rather than a show command."""
    c = cmd.strip().lower()
    if c in _CONFIG_MODE_COMMANDS:
        return True
    if c.startswith(_CONFIG_PREFIXES):
        return True
    return False


def _detect_vendor(device: dict) -> str:
    dt = (device.get("device_type") or "").lower()
    if any(x in dt for x in ("cisco_ios", "cisco_xe", "ios")): return "cisco_ios"
    if "nxos" in dt or "nx_os" in dt:                          return "cisco_nxos"
    if "iosxr" in dt or "ios_xr" in dt:                        return "cisco_xr"
    if "asa" in dt:                                             return "cisco_asa"
    if "junos" in dt or "juniper" in dt:                        return "juniper"
    if any(x in dt for x in ("linux", "ubuntu", "debian", "rhel", "centos",
                              "kali", "alpine", "unix")):
        return "linux"
    if "dell" in dt or "os10" in dt:                            return "dell_os10"
    if "alcatel" in dt or "aos" in dt:                          return "alcatel_aos"
    if "fortinet" in dt or "fortigate" in dt:                   return "fortinet"
    if "paloalto" in dt or "panos" in dt:                       return "paloalto"
    return "generic"


def _ssh_run(device: dict, commands: list[str], status_cb=None) -> str:
    vendor = _detect_vendor(device)
    if vendor == "linux":
        return _ssh_run_linux(device, commands, status_cb=status_cb)

    try:
        from netmiko import ConnectHandler
    except ImportError:
        return "[netmiko not installed — pip install netmiko]"

    host = device["host"]
    port = device.get("port", 22)
    user = device.get("username", "")
    skey = f"{host}:{port}:{user}"
    conn = None

    if skey in device_sessions:
        c = device_sessions[skey]
        if c.is_alive():
            conn = c

    if conn is None:
        NETMIKO_MAP = {
            "cisco_ios":  "cisco_ios",
            "cisco_nxos": "cisco_nxos",
            "cisco_xr":   "cisco_xr",
            "cisco_asa":  "cisco_asa",
            "juniper":    "juniper_junos",
            "fortinet":   "fortinet",
            "paloalto":   "paloalto_panos",
            "dell_os10":  "dell_os10",
            "alcatel_aos":"alcatel_aos",
            "generic":    "generic",
        }
        p = {k: v for k, v in device.items()
             if k not in ("hostname", "connected", "tags", "notes")}
        p["device_type"] = NETMIKO_MAP.get(vendor, p.get("device_type", "generic"))
        p.update(conn_timeout=30, banner_timeout=30, auth_timeout=30, fast_cli=True)
        if not p.get("secret"):
            p.pop("secret", None)
        for attempt in range(3):
            try:
                conn = ConnectHandler(**p)
                device_sessions[skey] = conn
                break
            except Exception as e:
                if attempt == 2:
                    return f"[CONNECTION FAILED] {e}"
                time.sleep(1.5)

    parts = []
    for cmd in commands:
        # Guard: skip config-mode commands that would cause send_command to hang
        if _is_config_command(cmd):
            parts.append(
                f"$ {cmd}\n"
                f"[SKIPPED] '{cmd}' is a config-mode command — use apply_fix instead."
            )
            continue

        if status_cb:
            status_cb(f"Running: {cmd[:50]}…")

        try:
            out = conn.send_command(
                cmd,
                read_timeout=30,
                strip_prompt=True,
                strip_command=True,
            )
            parts.append(f"$ {cmd}\n{out}")
        except Exception as e:
            parts.append(f"$ {cmd}\n[ERROR: {e}]")

    return "\n\n".join(parts)


def _ssh_run_linux(device: dict, commands: list[str], status_cb=None) -> str:
    try:
        import paramiko
    except ImportError:
        return "[paramiko not installed — pip install paramiko]"

    host     = device["host"]
    port     = device.get("port", 22)
    user     = device.get("username", "")
    password = device.get("password", "")
    skey     = f"linux:{host}:{port}:{user}"
    client   = device_sessions.get(skey)

    if client is None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            kw = dict(hostname=host, username=user, port=port, timeout=12)
            if password:
                kw["password"] = password
            client.connect(**kw)
            device_sessions[skey] = client
        except Exception as e:
            # Diagnostic ping to help the Agent understand why it failed
            ping_res = "unreachable"
            try:
                param = "-n" if platform.system().lower() == "windows" else "-c"
                if subprocess.run(["ping", param, "1", host], capture_output=True, timeout=2).returncode == 0: ping_res = "reachable (alive)"
            except: pass
            return f"[SSH CONNECT FAILED] Host {host} is {ping_res} via ICMP, but SSH connection failed. Error: {e}"

    parts = []
    for cmd in commands:
        if status_cb:
            status_cb(f"Running: {cmd[:50]}…")
        try:
            _, stdout, stderr = client.exec_command(cmd, timeout=20)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            parts.append(f"$ {cmd}\n{out or err or '(no output)'}")
        except Exception as e:
            parts.append(f"$ {cmd}\n[ERROR: {e}]")

    return "\n\n".join(parts)


def _ssh_config(device: dict, commands: list[str], status_cb=None) -> str:
    vendor = _detect_vendor(device)
    if vendor == "linux":
        # Linux has no config mode — just run the commands directly
        return _ssh_run_linux(device, commands, status_cb=status_cb)

    host = device["host"]
    port = device.get("port", 22)
    user = device.get("username", "")
    skey = f"{host}:{port}:{user}"
    conn = device_sessions.get(skey)

    if not conn or not conn.is_alive():
        return (
            "[ERROR] No live session for this device.\n"
            "Run a show command first to establish a connection, then retry."
        )

    # Strip configure terminal / end — Netmiko adds them automatically.
    # Sending them explicitly causes Netmiko to double-enter config mode and hang.
    clean_cmds = [
        c for c in commands
        if c.strip().lower() not in _CONFIG_MODE_COMMANDS
    ]

    if not clean_cmds:
        return "[NO COMMANDS] All commands were stripped (configure terminal / end are added automatically)."

    if status_cb:
        status_cb(f"Entering config mode on {device.get('hostname') or host}…")

    try:
        result = conn.send_config_set(
            clean_cmds,
            read_timeout=45,        # explicit timeout — prevents silent hang
            cmd_verify=False,
            strip_prompt=True,
            strip_command=True,
            enter_config_mode=True,
            exit_config_mode=True,
        )
        return result
    except Exception as e:
        return f"[CONFIG ERROR] {e}"


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT WORKER THREAD
# ═══════════════════════════════════════════════════════════════════════════════
class AgentWorker(QThread):
    token       = pyqtSignal(str)
    tool_call   = pyqtSignal(dict)
    tool_result = pyqtSignal(str, str)
    summary     = pyqtSignal(dict)
    status      = pyqtSignal(str)
    done        = pyqtSignal()

    def __init__(self, user_message, conversation, target_devices,
                 api_key, ai_url, model_chain: list[str]):
        super().__init__()
        self.user_message   = user_message
        self.conversation   = list(conversation)
        self.target_devices = target_devices
        self.api_key        = api_key
        self.ai_url         = ai_url
        self.model_chain    = model_chain
        # Sanitize URL to prevent 405 Method Not Allowed on some endpoints
        if self.ai_url.endswith("/"): self.ai_url = self.ai_url[:-1]
        self._stop          = False

    def stop(self): self._stop = True

    def _call_model(self, model_id: str, messages: list) -> requests.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
            "HTTP-Referer":  "https://NSTX.local",
            "X-Title":       "NSTX Autopilot",
        }
        body = {
            "model": model_id, "messages": messages, "stream": True,
            "temperature": 0.2, "max_tokens": 4096,
        }
        r = requests.post(self.ai_url, headers=headers, json=body,
                          stream=True, timeout=60)
        r.raise_for_status()
        return r

    def _stream_llm(self, messages: list):
        """Try models in order, falling back silently on 402/429/5xx."""
        for model_id in self.model_chain:
            if self._stop:
                return
            try:
                r = self._call_model(model_id, messages)
                for raw_line in r.iter_lines():
                    if self._stop:
                        return
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue
                return  # success
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else 0
                # Fallback on most errors to keep the loop alive (vibe coding style)
                # Only stop on explicit Auth failures
                if code in (401, 403):
                    yield f"\n[AUTH ERROR {code}] Check API Key.\n"
                    return
                continue # Try next model
            except Exception as e:
                continue # Try next model
        yield "\n[All models unavailable — check your API key and OpenRouter balance.]\n"

    def _execute_tool(self, call: dict) -> str:
        tool = call.get("tool", "")

        # ── run_commands ────────────────────────────────────────────────────
        if tool == "run_commands":
            dev_arg = call.get("device", "all")
            if dev_arg.lower() == "all":
                targets = self.target_devices
            else:
                # Resolve device from within the worker's context, not globally
                targets = [d for d in self.target_devices if (d.get("hostname") or "").lower() == dev_arg.lower() or d.get("host") == dev_arg]

            if not targets:
                return f"[NO DEVICES MATCHED FOR '{dev_arg}']"

            cmds = call.get("commands", [])
            config_cmds = [c for c in cmds if _is_config_command(c)]
            show_cmds   = [c for c in cmds if not _is_config_command(c)]

            parts = []
            for dev in targets:
                name   = dev.get("hostname") or dev["host"]
                output = []

                if show_cmds:
                    def _status_cb(msg, _name=name):
                        self.status.emit(f"[{_name}] {msg}")

                    self.status.emit(f"[{name}] Connecting…")
                    result = _ssh_run(dev, show_cmds, status_cb=_status_cb)
                    output.append(result)

                if config_cmds:
                    # Strip mode-enter/exit and redirect to config path
                    clean = [c for c in config_cmds if c.strip().lower()
                             not in _CONFIG_MODE_COMMANDS]
                    if clean:
                        self.status.emit(f"[{name}] Applying config (redirected from run_commands)…")
                        output.append(
                            "[NOTE] Config commands were redirected to config mode automatically.\n"
                            + _ssh_config(dev, clean,
                                          status_cb=lambda msg, n=name: self.status.emit(f"[{n}] {msg}"))
                        )

                parts.append(f"=== {name} ===\n" + "\n\n".join(output))

            return "\n\n".join(parts)

        # ── apply_fix ───────────────────────────────────────────────────────
        elif tool == "apply_fix":
            dev_arg = call.get("device", "")
            if not dev_arg or dev_arg.lower() == "all":
                targets = self.target_devices
            else:
                # Resolve device from within the worker's context, not globally
                targets = [d for d in self.target_devices if (d.get("hostname") or "").lower() == dev_arg.lower() or d.get("host") == dev_arg]

            if not targets:
                return f"[NO DEVICES MATCHED FOR '{dev_arg}']"
            if call.get("risk", "safe") in ("high", "destructive"):
                return f"[FIX BLOCKED] Risk '{call.get('risk')}' requires manual approval."

            # Strip configure terminal / end — send_config_set adds them.
            # Leaving them in causes Netmiko to double-enter config mode and hang.
            cmds = [
                c for c in call.get("commands", [])
                if c.strip().lower() not in _CONFIG_MODE_COMMANDS
            ]

            if not cmds:
                return "[NO COMMANDS] Nothing to apply after stripping configure/end."

            parts = []
            for dev in targets:
                name = dev.get("hostname") or dev["host"]

                def _status_cb(msg, _name=name):
                    self.status.emit(f"[{_name}] {msg}")

                self.status.emit(f"[{name}] Entering config mode…")
                result = _ssh_config(dev, cmds, status_cb=_status_cb)
                parts.append(f"=== {name} ===\n{result}")

                key = f"Autopilot_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                Tasks[key] = {
                    "devices":  [],
                    "commands": "\n".join(cmds),
                    "notes":    call.get("reason", ""),
                    "created":  datetime.now().isoformat(),
                }
                save_config()

            return "\n\n".join(parts)

        # ── summarise ───────────────────────────────────────────────────────
        elif tool == "summarise":
            self.summary.emit(call)
            return "[summary recorded]"

        return f"[UNKNOWN TOOL: {tool}]"

    @staticmethod
    def _extract_tools(text: str) -> list:
        covered: list[tuple[int, int]] = []
        out: list[tuple[int, int, dict]] = []

        def overlaps(s, e):
            return any(s < ce and e > cs for cs, ce in covered)

        for m in re.finditer(r"<TOOL>\s*(\{.*?\})\s*</TOOL>", text, re.DOTALL):
            if overlaps(m.start(), m.end()):
                continue
            try:
                obj = json.loads(m.group(1).strip())
                out.append((m.start(), m.end(), obj))
                covered.append((m.start(), m.end()))
            except Exception:
                pass

        # 2. XML-style <tool_call> fallback (for models that hallucinate this format)
        # <tool_call> <function=NAME> <parameter=KEY> VALUE </parameter> </function> </tool_call>
        for m in re.finditer(r"<tool_call>\s*<function=(?P<name>\w+)>(?P<body>.*?)</function>\s*</tool_call>", text, re.DOTALL):
            if overlaps(m.start(), m.end()): continue
            try:
                tool_name = m.group("name")
                body = m.group("body")
                params = {}
                for pm in re.finditer(r"<parameter=(?P<key>\w+)>(?P<val>.*?)</parameter>", body, re.DOTALL):
                    key = pm.group("key")
                    val_str = pm.group("val").strip().replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
                    try: val = json.loads(val_str)
                    except: val = val_str
                    params[key] = val
                params["tool"] = tool_name
                out.append((m.start(), m.end(), params))
                covered.append((m.start(), m.end()))
            except Exception: pass

        for m in re.finditer(r"\{[^{}]*\"tool\"\s*:\s*\"[^\"]+\"[^{}]*\}", text, re.DOTALL):
            if overlaps(m.start(), m.end()):
                continue
            try:
                obj = json.loads(m.group(0).strip())
                if "tool" in obj:
                    out.append((m.start(), m.end(), obj))
                    covered.append((m.start(), m.end()))
            except Exception:
                pass

        out.sort(key=lambda x: x[0])
        return out

    def run(self):
        device_ctx_lines = []
        for d in self.target_devices:
            name   = d.get("hostname") or d.get("host", "")
            host   = d.get("host", "")
            port   = d.get("port", 22)
            dtype  = d.get("device_type", "unknown")
            vendor = _detect_vendor(d)
            conn   = "CONNECTED" if d.get("connected") else "not connected"
            device_ctx_lines.append(
                f"  name={name}  host={host}:{port}  "
                f"device_type={dtype}  vendor={vendor}  status={conn}"
            )
        device_ctx = "\n".join(device_ctx_lines) if device_ctx_lines else "  (none)"
        system = (
            AGENT_SYSTEM
            + f"\n\nAVAILABLE DEVICES ({len(self.target_devices)} total):\n{device_ctx}\n"
        )
        messages = [
            {"role": "system",  "content": system},
            *self.conversation,
            {"role": "user",    "content": self.user_message},
        ]

        for _round in range(8):
            if self._stop:
                break
            accumulated = ""
            for chunk in self._stream_llm(messages):
                if self._stop:
                    break
                accumulated += chunk
                self.token.emit(chunk)
            if self._stop:
                break
            tool_calls = self._extract_tools(accumulated)
            if not tool_calls:
                break
            results_text = ""
            for (_, _, call) in tool_calls:
                self.tool_call.emit(call)
                result = self._execute_tool(call)
                self.tool_result.emit(call.get("tool", "tool"), result)
                results_text += (
                    f"\n<TOOL_RESULT tool='{call.get('tool','')}' "
                    f"device='{call.get('device','')}'>\n{result}\n</TOOL_RESULT>\n"
                )
            messages.append({"role": "assistant", "content": accumulated})
            messages.append({"role": "user",      "content": results_text})
            if all(c.get("tool") == "summarise" for (_, _, c) in tool_calls):
                break

        self.done.emit()


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT VIEW
# ═══════════════════════════════════════════════════════════════════════════════
class AgentView(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.document().setDocumentMargin(0)
        self._token_buffer = ""

        prose = QFont("Segoe UI", 10)
        if not QFontInfo(prose).exactMatch():
            prose = QFont()
            prose.setPointSize(10)
        self.setFont(prose)

        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C['bg']}; color: {C['text']};
                border: none; padding: 20px 28px;
                selection-background-color: {C['sel_bg']};
                selection-color: {C['text_hi']};
            }}
            QScrollBar:vertical {{
                background: {C['bg']}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C['border']}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C['border2']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def _fmt(self, color=None, bold=False, size=10, mono=False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setFontPointSize(size)
        if mono:
            fmt.setFontFamilies(["Cascadia Code", "Cascadia Mono", "Consolas", "Courier New"])
        else:
            fmt.setFontFamilies(["Segoe UI", "SF Pro Display", "Helvetica Neue", "Arial"])
        return fmt

    def _append(self, text: str, fmt: QTextCharFormat):
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(text, fmt)
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    def write_token(self, token: str):
        """Stream tokens, silently swallowing <TOOL>...</TOOL> blocks."""
        self._token_buffer += token
        while True:
            buf = self._token_buffer
            m = re.search(r"<TOOL>.*?</TOOL>", buf, re.DOTALL)
            if m:
                safe = buf[:m.start()]
                if safe:
                    self._append(safe, self._fmt(C["text"], size=10))
                self._token_buffer = buf[m.end():]
                continue
            partial = re.search(r"<TOOL>", buf)
            if partial:
                safe = buf[:partial.start()]
                if safe:
                    self._append(safe, self._fmt(C["text"], size=10))
                self._token_buffer = buf[partial.start():]
                break
            if buf:
                self._append(buf, self._fmt(C["text"], size=10))
                self._token_buffer = ""
            break

    def write_user(self, text: str):
        self._token_buffer = ""
        self._append("\n\n", self._fmt(C["text"]))
        self._append(f"▶  {text}", self._fmt(C["teal"], bold=True, size=10))
        self._append("\n\n", self._fmt(C["text"]))

    def write_tool_call(self, call: dict):
        tool = call.get("tool", "")
        dev  = call.get("device", "")
        cmds = call.get("commands", [])
        line = f"  ⟳  {tool}"
        if dev:
            line += f"  on {dev}"
        if cmds:
            line += "  —  " + " | ".join(cmds[:3]) + ("…" if len(cmds) > 3 else "")
        self._append(f"\n{line}\n", self._fmt(C["text_dim"], size=9, mono=True))

    def write_tool_result(self, tool_name: str, result: str):
        self._append(f"\n{result}\n", self._fmt(C["text_mid"], size=9, mono=True))

    def write_system(self, text: str):
        self._append(f"\n{text}\n", self._fmt(C["text_dim"], size=9))

    def write_divider(self, label=""):
        if label:
            self._append(f"\n── {label} ", self._fmt(C["text_dim"], size=8))
            self._append("─" * max(1, 56 - len(label)) + "\n", self._fmt(C["border2"], size=8))
        else:
            self._append("\n" + "─" * 64 + "\n", self._fmt(C["border2"], size=8))

    def write_summary(self, s: dict):
        sev = s.get("severity", "low")
        sev_c, sev_t = SEV.get(sev, (C["text_dim"], sev.upper()))
        self.write_divider("DIAGNOSIS")
        self._append(f"  {sev_t}  confidence {s.get('confidence', 0)}%\n\n",
                     self._fmt(sev_c, bold=True, size=9))
        self._append(s.get("diagnosis", "") + "\n", self._fmt(C["text"], size=10))
        if s.get("root_cause"):
            self._append("\nRoot cause\n", self._fmt(C["text_dim"], bold=True, size=9))
            self._append(s["root_cause"] + "\n", self._fmt(C["text_mid"], size=9))
        if s.get("learning_note"):
            self._append("\nStudy note\n", self._fmt(C["teal"], bold=True, size=9))
            self._append(s["learning_note"] + "\n", self._fmt(C["text_mid"], size=9))
        self.write_divider()


# ═══════════════════════════════════════════════════════════════════════════════
#  TOP BAR
# ═══════════════════════════════════════════════════════════════════════════════
class TopBar(QWidget):
    abort_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet(
            f"background:{C['bar_bg']};border-bottom:1px solid {C['border']};"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 10, 0)
        lay.setSpacing(8)

        self._title = QLabel("NSTX  Autopilot")
        self._title.setStyleSheet(
            f"color:{C['teal']};font-family:{SANS};font-size:12px;"
            f"font-weight:700;background:transparent;letter-spacing:0.5px;"
        )
        lay.addWidget(self._title)
        lay.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color:{C['text_dim']};font-family:{SANS};font-size:10px;background:transparent;"
        )
        lay.addWidget(self._status_lbl)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setFixedHeight(28)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['bg']}; color: {C['text_mid']};
                border: 1px solid {C['border']}; border-radius: 5px;
                font-family: {SANS}; font-size: 10px; font-weight: 600; padding: 0 14px;
            }}
            QPushButton:hover  {{ background: #FFF0EC; color: {C['sev_high']}; border-color: {C['sev_high']}; }}
            QPushButton:pressed{{ background: #FFDDD0; }}
        """)
        self._stop_btn.clicked.connect(self.abort_requested)
        lay.addWidget(self._stop_btn)

        self._fade = QTimer(self)
        self._fade.setSingleShot(True)
        self._fade.timeout.connect(lambda: self._status_lbl.setText(""))

    def set_status(self, text: str):
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(
            f"color:{C['teal']};font-family:{SANS};font-size:10px;background:transparent;"
        )
        self._fade.stop()

    def clear_status(self):
        self._status_lbl.setText("Done")
        self._status_lbl.setStyleSheet(
            f"color:{C['green']};font-family:{SANS};font-size:10px;background:transparent;"
        )
        self._fade.start(2000)


# ═══════════════════════════════════════════════════════════════════════════════
#  BOTTOM INPUT BAR
# ═══════════════════════════════════════════════════════════════════════════════
class BottomBar(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)
        self.setStyleSheet(
            f"background:{C['bar_bg']};border-top:1px solid {C['border']};"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hint = QWidget()
        hint.setFixedHeight(22)
        hint.setStyleSheet(
            f"background:{C['panel2']};border-top:1px solid {C['border']};"
        )
        hl = QHBoxLayout(hint)
        hl.setContentsMargins(16, 0, 16, 0)
        hint_lbl = QLabel("Enter → send  |  ↑↓ → history")
        hint_lbl.setStyleSheet(
            f"color:{C['text_dim']};font-family:{MONO};font-size:8px;background:transparent;"
        )
        hl.addWidget(hint_lbl)
        hl.addStretch()
        ai_lbl = QLabel("AI MODE")
        ai_lbl.setStyleSheet(
            f"color:{C['teal']};font-family:{MONO};font-size:8px;"
            f"font-weight:700;background:transparent;letter-spacing:1px;"
        )
        hl.addWidget(ai_lbl)
        outer.addWidget(hint)

        row = QWidget()
        row.setStyleSheet(f"background:{C['bar_bg']};")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 8, 14, 8)
        rl.setSpacing(8)

        arrow = QLabel("▶")
        arrow.setFixedWidth(16)
        arrow.setStyleSheet(f"color:{C['teal']};font-size:12px;background:transparent;")
        rl.addWidget(arrow)

        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Ask anything — 'explain this router config'  ·  'check BGP'  ·  'why is CPU high?'"
        )
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; color: {C['text']};
                border: none; font-family: {SANS}; font-size: 11px; padding: 0;
                selection-background-color: {C['sel_bg']};
            }}
            QLineEdit:disabled {{ color: {C['text_dim']}; }}
        """)
        self._input.returnPressed.connect(self._send)
        rl.addWidget(self._input, 1)

        self._run_btn = QPushButton("▶  Run")
        self._run_btn.setFixedHeight(30)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['teal']}; color: {C['bg']};
                border: none; border-radius: 5px;
                font-family: {SANS}; font-size: 10px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover  {{ background: {C['teal_dim']}; }}
            QPushButton:disabled{{ background: {C['border']}; color: {C['text_dim']}; }}
        """)
        self._run_btn.clicked.connect(self._send)
        rl.addWidget(self._run_btn)
        outer.addWidget(row)

    def _send(self):
        text = self._input.text().strip()
        if text:
            self.submitted.emit(text)
            self._input.clear()

    def set_enabled(self, v: bool):
        self._input.setEnabled(v)
        self._run_btn.setEnabled(v)
        self._run_btn.setText("▶  Run" if v else "…")
        if v:
            self._input.setFocus()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN AUTOPILOT PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class AutopilotPanel(QWidget):
    def __init__(self, devices_list, api_key, ai_url, theme="light", parent=None):
        global C, SEV
        C.clear()
        C.update(C_DARK if theme == "dark" else C_LIGHT)
        SEV.clear()
        SEV.update({
            "critical": (C["sev_critical"], "CRITICAL"),
            "high":     (C["sev_high"],     "HIGH    "),
            "medium":   (C["sev_medium"],   "MEDIUM  "),
            "low":      (C["sev_low"],      "LOW     "),
            "healthy":  (C["sev_healthy"],  "HEALTHY "),
        })
        super().__init__(parent)
        self.devices   = devices_list
        self.api_key   = api_key
        self.ai_url    = ai_url
        self._worker: Optional[AgentWorker] = None
        self._conversation: list[dict] = []
        self._running  = False
        self._model_chain: list[str] = list(_FALLBACK_CHAIN)
        self._build()
        self._start_model_selection()

    def _start_model_selection(self):
        self._sel = ModelSelector(self.api_key, self.ai_url)
        self._sel.ready.connect(self._on_model_ready)
        self._sel.start()

    def _on_model_ready(self, model_id: str):
        self._model_chain = [model_id] + [m for m in _FALLBACK_CHAIN if m != model_id]

    def showEvent(self, event):
        super().showEvent(event)

    def _build(self):
        self.setStyleSheet(f"background:{C['bg']};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._topbar = TopBar()
        self._topbar.abort_requested.connect(self._abort)
        root.addWidget(self._topbar)

        self._view = AgentView()
        root.addWidget(self._view, 1)

        self._bottom = BottomBar()
        self._bottom.submitted.connect(self._submit)
        root.addWidget(self._bottom)

    def _submit(self, text: str):
        if self._running:
            self._view.write_system("Agent is busy — stop first.")
            return

        # Import at runtime to get the current selection from the main app
        try:
            from __main__ import selected_indexes as current_selection
        except ImportError:
            current_selection = selected_indexes

        if current_selection:
            targets = [self.devices[i] for i in sorted(current_selection) if 0 <= i < len(self.devices)]
        else:
            targets = []

        if not targets:
            self._view.write_system(
                "No devices selected. Please select at least one device in the sidebar."
            )
            return

        self._view.write_user(text)
        self._topbar.set_status("thinking…")
        self._bottom.set_enabled(False)
        self._running = True

        self._worker = AgentWorker(
            text, self._conversation, targets,
            self.api_key, self.ai_url, self._model_chain,
        )
        self._worker.token.connect(self._view.write_token)
        self._worker.tool_call.connect(self._view.write_tool_call)
        self._worker.tool_result.connect(self._view.write_tool_result)
        self._worker.summary.connect(self._on_summary)
        self._worker.status.connect(self._topbar.set_status)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_summary(self, s: dict):
        self._view.write_summary(s)
        self._conversation.append({
            "role":    "assistant",
            "content": f"[diagnosis: {s.get('diagnosis', '')}]",
        })

    def _on_done(self):
        self._running = False
        self._topbar.clear_status()
        self._bottom.set_enabled(True)

    def clear_session(self):
        self._view.clear()
        self._conversation.clear()
        self._view.write_system("Session cleared.")

    def _abort(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._view.write_system("Stopped.")
        self._running = False
        self._topbar.clear_status()
        self._bottom.set_enabled(True)


#═════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def create_autopilot_tab(tab_widget, devices_list, api_key, ai_url) -> AutopilotPanel:
    panel = AutopilotPanel(devices_list, api_key, ai_url)
    tab_widget.addTab(panel, "  Autopilot  ")
    return panel
