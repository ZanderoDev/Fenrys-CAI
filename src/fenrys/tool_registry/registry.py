from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from typing import Any

from fenrys.models import ToolSpec

AGENT_FOCUS = {
    "recon": "network discovery, ports, services, DNS, subdomains, HTTP probing",
    "web": "web crawling, content discovery, web vulnerabilities, APIs and SQLi",
    "network": "SMB, RPC, NetBIOS, Windows/network protocol enumeration",
    "pwn": "ELF/binary triage, debugging, ROP, exploit development",
    "forensics": "files, metadata, disk/memory artifacts and steganography",
    "osint": "public intelligence, usernames, domains and attack surface discovery",
    "vulnintel": "CVE correlation, nuclei, exploit research and prioritization",
    "crypto": "encodings, cryptography, hash cracking and puzzle solving",
    "misc": "local challenge artifacts, scripting and general CTF analysis",
}

# Hardcoded tool schemas from HexStrike-AI (71 available tools)
# These are the actual tools registered in HexStrike MCP server
HEXSTRIKE_TOOLS: dict[str, dict[str, Any]] = {
    # ─── Network Scanning ───
    "nmap_scan": {
        "description": "Nmap network scanner with version detection",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target IP or hostname"},
                "scan_type": {"type": "string", "default": "-sV", "description": "Scan type"},
                "ports": {"type": "string", "default": "", "description": "Port range"},
                "additional_args": {"type": "string", "default": "", "description": "Extra flags"}
            },
            "required": ["target"]
        }
    },
    "nmap_advanced_scan": {
        "description": "Advanced Nmap scan with NSE scripts and timing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target IP or hostname"},
                "scan_type": {"type": "string", "default": "-sV"},
                "ports": {"type": "string", "default": ""},
                "timing": {"type": "string", "default": "-T4"},
                "nse_scripts": {"type": "string", "default": ""},
                "os_detection": {"type": "boolean", "default": False},
                "version_detection": {"type": "boolean", "default": True},
                "aggressive": {"type": "boolean", "default": False},
                "stealth": {"type": "boolean", "default": False},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "rustscan_fast_scan": {
        "description": "Fast port scanner using Rust, feeds into Nmap",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target IP or hostname"},
                "ports": {"type": "string", "default": ""},
                "ulimit": {"type": "integer", "default": 5000},
                "batch_size": {"type": "integer", "default": 4500},
                "timeout": {"type": "integer", "default": 1500},
                "scripts": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "masscan_high_speed": {
        "description": "High-speed port scanner (10M pps)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target IP, CIDR, or range"},
                "ports": {"type": "string", "default": "1-65535"},
                "rate": {"type": "integer", "default": 1000},
                "interface": {"type": "string", "default": ""},
                "router_mac": {"type": "string", "default": ""},
                "source_ip": {"type": "string", "default": ""},
                "banners": {"type": "boolean", "default": True},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "autorecon_comprehensive": {
        "description": "Comprehensive automated reconnaissance",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target IP or hostname"},
                "output_dir": {"type": "string", "default": ""},
                "timeout": {"type": "integer", "default": 3600},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },

    # ─── Subdomain Enumeration ───
    "amass_scan": {
        "description": "Subdomain enumeration using Amass",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "mode": {"type": "string", "default": "enum"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["domain"]
        }
    },
    "subfinder_scan": {
        "description": "Fast passive subdomain enumeration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "silent": {"type": "boolean", "default": True},
                "all_sources": {"type": "boolean", "default": False},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["domain"]
        }
    },
    "httpx_probe": {
        "description": "HTTP probe for technology detection and status",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target URL or domain"},
                "probe": {"type": "boolean", "default": True},
                "tech_detect": {"type": "boolean", "default": True},
                "status_code": {"type": "boolean", "default": True},
                "content_length": {"type": "boolean", "default": True},
                "title": {"type": "boolean", "default": True},
                "web_server": {"type": "boolean", "default": True},
                "threads": {"type": "integer", "default": 25},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "dnsenum_scan": {
        "description": "DNS enumeration with brute force",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "dns_server": {"type": "string", "default": ""},
                "wordlist": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["domain"]
        }
    },
    "arp_scan_discovery": {
        "description": "ARP scan for local network discovery",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target range or CIDR"},
                "interface": {"type": "string", "default": ""},
                "local_network": {"type": "boolean", "default": False},
                "timeout": {"type": "integer", "default": 5},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },

    # ─── Web Security ───
    "katana_crawl": {
        "description": "Web crawler with JS rendering and form extraction",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL"},
                "depth": {"type": "integer", "default": 3},
                "js_crawl": {"type": "boolean", "default": True},
                "form_extraction": {"type": "boolean", "default": True},
                "output_format": {"type": "string", "default": "json"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["url"]
        }
    },
    "ffuf_scan": {
        "description": "Fast web fuzzer for directory/files/parameters",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL with FUZZ keyword"},
                "wordlist": {"type": "string", "description": "Path to wordlist"},
                "mode": {"type": "string", "default": "dir"},
                "match_codes": {"type": "string", "default": "200,301,302,403"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["url", "wordlist"]
        }
    },
    "nuclei_scan": {
        "description": "Template-based vulnerability scanner",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target URL or host"},
                "severity": {"type": "string", "default": "", "description": "Filter by severity"},
                "tags": {"type": "string", "default": ""},
                "template": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "sqlmap_scan": {
        "description": "Automatic SQL injection detection and exploitation",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL"},
                "data": {"type": "string", "default": "", "description": "POST data"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["url"]
        }
    },
    "dalfox_xss_scan": {
        "description": "Powerful XSS scanner",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL"},
                "pipe_mode": {"type": "boolean", "default": False},
                "blind": {"type": "string", "default": ""},
                "mining_dom": {"type": "boolean", "default": True},
                "mining_dict": {"type": "boolean", "default": True},
                "custom_payload": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["url"]
        }
    },
    "nikto_scan": {
        "description": "Web server vulnerability scanner",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target host or URL"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "dirsearch_scan": {
        "description": "Web path/directory brute forcing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL"},
                "extensions": {"type": "string", "default": "php,html,js"},
                "wordlist": {"type": "string", "default": ""},
                "threads": {"type": "integer", "default": 30},
                "recursive": {"type": "boolean", "default": False},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["url"]
        }
    },
    "feroxbuster_scan": {
        "description": "Fast content discovery tool",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL"},
                "wordlist": {"type": "string", "default": ""},
                "threads": {"type": "integer", "default": 50},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["url"]
        }
    },
    "wafw00f_scan": {
        "description": "WAF detection tool",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target URL or host"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "hakrawler_crawl": {
        "description": "Web crawler for discovering endpoints",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL"},
                "depth": {"type": "integer", "default": 2},
                "forms": {"type": "boolean", "default": True},
                "robots": {"type": "boolean", "default": True},
                "sitemap": {"type": "boolean", "default": True},
                "wayback": {"type": "boolean", "default": True},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["url"]
        }
    },
    "gau_discovery": {
        "description": "Fetch known URLs from AlienVault OTX, Wayback, Common Crawl",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "providers": {"type": "string", "default": "wayback,otx,commoncrawl"},
                "include_subs": {"type": "boolean", "default": False},
                "blacklist": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["domain"]
        }
    },
    "waybackurls_discovery": {
        "description": "Fetch URLs from Wayback Machine",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "get_versions": {"type": "boolean", "default": False},
                "no_subs": {"type": "boolean", "default": False},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["domain"]
        }
    },
    "arjun_parameter_discovery": {
        "description": "HTTP parameter discovery suite",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL"},
                "method": {"type": "string", "default": "GET"},
                "wordlist": {"type": "string", "default": ""},
                "delay": {"type": "integer", "default": 0},
                "threads": {"type": "integer", "default": 2},
                "stable": {"type": "boolean", "default": True},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["url"]
        }
    },
    "paramspider_mining": {
        "description": "Mining parameters from dark corners of web",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "level": {"type": "string", "default": "medium"},
                "exclude": {"type": "string", "default": ""},
                "output": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["domain"]
        }
    },

    # ─── Network Enumeration ───
    "smbmap_scan": {
        "description": "SMB share enumeration and file listing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target host"},
                "username": {"type": "string", "default": ""},
                "password": {"type": "string", "default": ""},
                "domain": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "enum4linux_ng_advanced": {
        "description": "Advanced NetBIOS/SMB enumeration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target host"},
                "username": {"type": "string", "default": ""},
                "password": {"type": "string", "default": ""},
                "domain": {"type": "string", "default": ""},
                "shares": {"type": "boolean", "default": True},
                "users": {"type": "boolean", "default": True},
                "groups": {"type": "boolean", "default": True},
                "policy": {"type": "boolean", "default": True},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "netexec_scan": {
        "description": "Swiss army knife for pentesting Windows/Active Directory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target host"},
                "protocol": {"type": "string", "default": "smb"},
                "username": {"type": "string", "default": ""},
                "password": {"type": "string", "default": ""},
                "hash_value": {"type": "string", "default": ""},
                "module": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "rpcclient_enumeration": {
        "description": "RPC client for Windows enumeration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target host"},
                "username": {"type": "string", "default": ""},
                "password": {"type": "string", "default": ""},
                "domain": {"type": "string", "default": ""},
                "commands": {"type": "string", "default": "enumdomusers"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },
    "nbtscan_netbios": {
        "description": "NetBIOS name scanner",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target range"},
                "verbose": {"type": "boolean", "default": True},
                "timeout": {"type": "integer", "default": 1000},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target"]
        }
    },

    # ─── Binary Analysis ───
    "checksec_analyze": {
        "description": "Check binary protections (RELRO, Stack, NX, PIE, RPATH)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary": {"type": "string", "description": "Path to binary"}
            },
            "required": ["binary"]
        }
    },
    "gdb_analyze": {
        "description": "GDB debugger for binary analysis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary": {"type": "string", "description": "Path to binary"},
                "commands": {"type": "string", "description": "GDB commands"},
                "script_file": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["binary", "commands"]
        }
    },
    "pwntools_exploit": {
        "description": "Execute pwntools exploit script",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_content": {"type": "string", "description": "Python pwntools code"},
                "target_binary": {"type": "string", "default": ""},
                "target_host": {"type": "string", "default": ""},
                "target_port": {"type": "integer", "default": 0},
                "exploit_type": {"type": "string", "default": "local"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["script_content"]
        }
    },
    "ropper_gadget_search": {
        "description": "Search for ROP gadgets in binaries",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary": {"type": "string", "description": "Path to binary"},
                "gadget_type": {"type": "string", "default": "rop"},
                "quality": {"type": "integer", "default": 5},
                "arch": {"type": "string", "default": ""},
                "search_string": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["binary"]
        }
    },
    "radare2_analyze": {
        "description": "Radare2 reverse engineering framework",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary": {"type": "string", "description": "Path to binary"},
                "commands": {"type": "string", "description": "R2 commands"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["binary", "commands"]
        }
    },
    "objdump_analyze": {
        "description": "Disassemble binary with objdump",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary": {"type": "string", "description": "Path to binary"},
                "disassemble": {"type": "boolean", "default": True},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["binary"]
        }
    },
    "binwalk_analyze": {
        "description": "Firmware analysis and extraction",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to file"},
                "extract": {"type": "boolean", "default": False},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["file_path"]
        }
    },
    "xxd_hexdump": {
        "description": "Create hex dump of file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to file"},
                "offset": {"type": "integer", "default": 0},
                "length": {"type": "integer", "default": 256},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["file_path"]
        }
    },
    "strings_extract": {
        "description": "Extract printable strings from binary",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to file"},
                "min_len": {"type": "integer", "default": 4},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["file_path"]
        }
    },
    "ghidra_analysis": {
        "description": "Ghidra reverse engineering tool",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary": {"type": "string", "description": "Path to binary"},
                "project_name": {"type": "string", "default": "fenrys_project"},
                "script_file": {"type": "string", "default": ""},
                "analysis_timeout": {"type": "integer", "default": 300},
                "output_format": {"type": "string", "default": "text"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["binary"]
        }
    },
    "angr_symbolic_execution": {
        "description": "angr symbolic execution engine",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary": {"type": "string", "description": "Path to binary"},
                "script_content": {"type": "string", "default": ""},
                "find_address": {"type": "string", "default": ""},
                "avoid_addresses": {"type": "string", "default": ""},
                "analysis_type": {"type": "string", "default": "symbolic"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["binary"]
        }
    },

    # ─── Forensics ───
    "exiftool_extract": {
        "description": "Extract metadata from files",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to file"},
                "output_format": {"type": "string", "default": "json"},
                "tags": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["file_path"]
        }
    },
    "volatility3_analyze": {
        "description": "Memory forensics with Volatility 3",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_file": {"type": "string", "description": "Path to memory dump"},
                "plugin": {"type": "string", "description": "Volatility plugin"},
                "output_file": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["memory_file", "plugin"]
        }
    },
    "foremost_carving": {
        "description": "File carving tool for data recovery",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_file": {"type": "string", "description": "Path to file"},
                "output_dir": {"type": "string", "default": ""},
                "file_types": {"type": "string", "default": "all"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["input_file"]
        }
    },
    "steghide_analysis": {
        "description": "Steganography tool for hiding/extracting data in images",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "extract or embed"},
                "cover_file": {"type": "string", "description": "Cover file path"},
                "embed_file": {"type": "string", "default": ""},
                "passphrase": {"type": "string", "default": ""},
                "output_file": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["action", "cover_file"]
        }
    },

    # ─── Password Cracking ───
    "hashcat_crack": {
        "description": "GPU-accelerated password cracking",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hash_file": {"type": "string", "description": "Path to hash file"},
                "hash_type": {"type": "string", "default": "0"},
                "attack_mode": {"type": "string", "default": "0"},
                "wordlist": {"type": "string", "default": ""},
                "mask": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["hash_file"]
        }
    },
    "john_crack": {
        "description": "John the Ripper password cracker",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hash_file": {"type": "string", "description": "Path to hash file"},
                "wordlist": {"type": "string", "default": ""},
                "format_type": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["hash_file"]
        }
    },
    "hashpump_attack": {
        "description": "Hash length extension attack tool",
        "inputSchema": {
            "type": "object",
            "properties": {
                "signature": {"type": "string", "description": "Original signature"},
                "data": {"type": "string", "description": "Original data"},
                "key_length": {"type": "integer", "description": "Key length"},
                "append_data": {"type": "string", "description": "Data to append"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["signature", "data", "key_length", "append_data"]
        }
    },

    # ─── Exploitation ───
    "metasploit_run": {
        "description": "Execute Metasploit modules",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {"type": "string", "description": "MSF module path"},
                "options": {"type": "object", "default": {}, "description": "Module options"}
            },
            "required": ["module"]
        }
    },
    "msfvenom_generate": {
        "description": "Generate MSF payloads",
        "inputSchema": {
            "type": "object",
            "properties": {
                "payload": {"type": "string", "description": "Payload type"},
                "format_type": {"type": "string", "default": "raw"},
                "output_file": {"type": "string", "default": ""},
                "encoder": {"type": "string", "default": ""},
                "iterations": {"type": "integer", "default": 0},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["payload"]
        }
    },
    "hydra_attack": {
        "description": "Network login cracker",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target host"},
                "service": {"type": "string", "description": "Service (ssh, ftp, etc)"},
                "username": {"type": "string", "default": ""},
                "username_file": {"type": "string", "default": ""},
                "password": {"type": "string", "default": ""},
                "password_file": {"type": "string", "default": ""},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["target", "service"]
        }
    },

    # ─── Vulnerability Intelligence ───
    "monitor_cve_feeds": {
        "description": "Monitor CVE feeds and alerts",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "default": 24},
                "severity_filter": {"type": "string", "default": ""},
                "keywords": {"type": "string", "default": ""}
            }
        }
    },
    "generate_exploit_from_cve": {
        "description": "Generate exploit code from CVE",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cve_id": {"type": "string", "description": "CVE identifier"},
                "target_os": {"type": "string", "default": "linux"},
                "target_arch": {"type": "string", "default": "x64"},
                "exploit_type": {"type": "string", "default": "reverse_shell"},
                "evasion_level": {"type": "string", "default": "basic"}
            },
            "required": ["cve_id"]
        }
    },
    "discover_attack_chains": {
        "description": "Discover multi-stage attack chains",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_software": {"type": "string", "description": "Target software stack"},
                "attack_depth": {"type": "integer", "default": 3},
                "include_zero_days": {"type": "boolean", "default": False}
            },
            "required": ["target_software"]
        }
    },
    "correlate_threat_intelligence": {
        "description": "Correlate IOCs with threat intelligence",
        "inputSchema": {
            "type": "object",
            "properties": {
                "indicators": {"type": "string", "description": "Comma-separated IOCs"},
                "timeframe": {"type": "string", "default": "30d"},
                "sources": {"type": "string", "default": "all"}
            },
            "required": ["indicators"]
        }
    },

    # ─── Python Execution ───
    "execute_python_script": {
        "description": "Execute Python script in sandboxed environment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "Python code to execute"},
                "env_name": {"type": "string", "default": "default"},
                "filename": {"type": "string", "default": ""}
            },
            "required": ["script"]
        }
    },
    "install_python_package": {
        "description": "Install Python package in venv",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package name"},
                "env_name": {"type": "string", "default": "default"}
            },
            "required": ["package"]
        }
    },

    # ─── File Operations ───
    "create_file": {
        "description": "Create a file with content",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "File content"},
                "binary": {"type": "boolean", "default": False}
            },
            "required": ["filename", "content"]
        }
    },
    "modify_file": {
        "description": "Modify or append to a file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "New content"},
                "append": {"type": "boolean", "default": False}
            },
            "required": ["filename", "content"]
        }
    },
    "list_files": {
        "description": "List files in a directory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "default": "."}
            }
        }
    },

    # ─── General Execution ───
    "execute_command": {
        "description": "Execute arbitrary shell command (use with caution)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command"},
                "use_cache": {"type": "boolean", "default": True}
            },
            "required": ["command"]
        }
    },

    # ─── OSINT ───
    "sherlock": {
        "description": "Hunt down social media accounts by username",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "Target username"},
                "additional_args": {"type": "string", "default": ""}
            },
            "required": ["username"]
        }
    },

    # ─── Recon-ng ───
    "recon-ng": {
        "description": "Reconnaissance framework with modules",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {"type": "string", "description": "Module name"},
                "options": {"type": "object", "default": {}},
                "command": {"type": "string", "default": ""}
            },
            "required": ["module"]
        }
    },

    # ─── Output & Reporting ───
    "create_scan_summary": {
        "description": "Create visual scan summary report",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "tools_used": {"type": "string"},
                "vulnerabilities_found": {"type": "integer", "default": 0},
                "execution_time": {"type": "string", "default": ""},
                "findings": {"type": "string", "default": ""}
            },
            "required": ["target", "tools_used"]
        }
    },
}

# Agent to tool mapping
AGENT_TOOL_NAMES: dict[str, list[str]] = {
    "recon": ["nmap_scan", "nmap_advanced_scan", "rustscan_fast_scan", "masscan_high_speed",
              "amass_scan", "subfinder_scan", "httpx_probe", "autorecon_comprehensive",
              "arp_scan_discovery", "dnsenum_scan"],
    "web": ["katana_crawl", "ffuf_scan", "nuclei_scan", "sqlmap_scan", "dalfox_xss_scan",
            "nikto_scan", "dirsearch_scan", "feroxbuster_scan", "wafw00f_scan",
            "hakrawler_crawl", "gau_discovery", "waybackurls_discovery",
            "arjun_parameter_discovery", "paramspider_mining"],
    "network": ["smbmap_scan", "enum4linux_ng_advanced", "netexec_scan",
                "rpcclient_enumeration", "nbtscan_netbios", "arp_scan_discovery"],
    "pwn": ["checksec_analyze", "gdb_analyze", "pwntools_exploit", "ropper_gadget_search",
            "radare2_analyze", "objdump_analyze", "binwalk_analyze", "xxd_hexdump",
            "strings_extract", "ghidra_analysis", "angr_symbolic_execution"],
    "forensics": ["binwalk_analyze", "exiftool_extract", "volatility3_analyze",
                  "foremost_carving", "steghide_analysis", "strings_extract",
                  "xxd_hexdump", "hashcat_crack", "john_crack"],
    "osint": ["sherlock", "amass_scan", "subfinder_scan", "httpx_probe", "recon-ng"],
    "vulnintel": ["nuclei_scan", "monitor_cve_feeds", "generate_exploit_from_cve",
                  "discover_attack_chains", "correlate_threat_intelligence"],
    "crypto": ["execute_python_script", "hashcat_crack", "john_crack", "hashpump_attack"],
    "misc": ["execute_python_script", "execute_command", "create_file", "list_files",
             "strings_extract"],
}


@dataclass(slots=True)
class ToolAvailability:
    mcp_registered: bool = False
    backend_registered: bool = False
    binary_detected: bool = False


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, ToolAvailability] = {}
        self.specs: dict[str, ToolSpec] = {}

    def load_hexstrike_tools(self) -> None:
        """Load all hardcoded HexStrike tool schemas."""
        for name, info in HEXSTRIKE_TOOLS.items():
            description = info.get("description", "Security tool")
            schema = info.get("inputSchema", {})
            self.tools[name] = ToolAvailability(
                mcp_registered=True,
                backend_registered=True,
                binary_detected=False
            )
            self.specs[name] = ToolSpec(name, description, output_schema=schema)

    def sync(self, tools: list[dict[str, Any]] | list[str], backend_registered: bool | None = None) -> None:
        for item in tools:
            if isinstance(item, str):
                name, description, schema = item, "Registered security tool", {}
                mcp_registered = False
                item_backend = backend_registered
            else:
                name = item.get("name", "")
                description = item.get("description", "")
                schema = item.get("inputSchema") or item.get("input_schema") or {}
                mcp_registered = bool(item.get("mcp_registered", False))
                item_backend = item.get("backend_registered", backend_registered)
            if not name:
                continue
            availability = self.tools.setdefault(name, ToolAvailability())
            availability.mcp_registered |= mcp_registered
            if item_backend is not None:
                availability.backend_registered = bool(item_backend)
            self.tools[name].binary_detected = bool(shutil.which(name))
            self.specs[name] = ToolSpec(name, description or "Registered security tool", output_schema=schema)

    def detect_binaries(self, names: list[str] | None = None) -> None:
        for name in names or list(self.tools):
            self.tools.setdefault(name, ToolAvailability()).binary_detected = bool(shutil.which(name))

    def all_specs(self) -> list[ToolSpec]:
        return list(self.specs.values())

    def profile_for(self, agent: str, limit: int = 40) -> list[ToolSpec]:
        """Return tools for a specific agent, using hardcoded HEXSTRIKE_TOOLS schemas."""
        selected: list[ToolSpec] = []
        seen: set[str] = set()

        # First, add the agent's primary tools (hardcoded)
        for name in AGENT_TOOL_NAMES.get(agent, []):
            if name in self.specs and name not in seen:
                selected.append(self.specs[name])
                seen.add(name)

        # Then, add related tools by relevance scoring
        focus = AGENT_FOCUS.get(agent, "general cybersecurity analysis")
        words = set(focus.lower().replace(",", " ").split())
        scored: list[tuple[int, ToolSpec]] = []
        for spec in self.specs.values():
            if spec.name in seen:
                continue
            haystack = f"{spec.name} {spec.description}".lower()
            score = sum(1 for word in words if len(word) > 3 and word in haystack)
            scored.append((score, spec))
        scored = [(score, spec) for score, spec in scored if score > 0]
        scored.sort(key=lambda pair: (pair[0], pair[1].name), reverse=True)
        selected.extend(spec for _, spec in scored[:max(0, limit - len(selected))])
        return selected

    def status(self) -> dict[str, dict[str, bool]]:
        return {name: asdict(value) for name, value in sorted(self.tools.items())}
