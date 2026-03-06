"""
GL-iNet Router API Standalone Tool
"""
import asyncio
import json
import sys
import argparse
import inspect
from getpass import getpass
from api import GLiNetAPI

async def print_clients(api):
    """Pretty print connected clients."""
    clients = await api.get_clients()
    if not isinstance(clients, list):
        print(json.dumps(clients, indent=2))
        return
    
    # Sort online first
    clients.sort(key=lambda x: x.get("online", False), reverse=True)
    
    headers = ["Client", "MAC", "Hostname", "Alias", "Class", "IP", "Status"]
    # Filter fields we care about
    rows = []
    for c in clients:
        rows.append([
            str(c.get("name") or "Unknown")[:15],
            c.get("mac"),
            str(c.get("hostname") or "")[:15],
            str(c.get("alias") or "")[:10],
            str(c.get("class") or "")[:10],
            c.get("ip", ""),
            "Connected" if c.get("online") else "Disconnected"
        ])
    
    if not rows:
        print("[*] No clients found.")
        return

    col_widths = [max(len(str(row[i])) for row in rows + [headers]) for i in range(len(headers))]
    fmt = "  ".join([f"{{:<{w}}}" for w in col_widths])
    
    print("\n" + fmt.format(*headers))
    print("-" * (sum(col_widths) + len(headers) * 2))
    for row in rows:
        print(fmt.format(*row))
    print()

async def print_interfaces(api):
    """Pretty print network interfaces."""
    wifi = await api.get_wifi_ifaces()
    mlo = await api.get_mlo_config()
    
    print("\n[ WiFi Interfaces ]")
    if isinstance(wifi, list):
        for iface in wifi:
            status = "UP" if iface.get("enabled") else "DOWN"
            print(f"  {iface.get('device', '?')}:{iface.get('iface_name', '?'):<10} | SSID: {iface.get('ssid', 'N/A'):<20} | Status: {status}")
    else:
        print("  None detected or error.")

    print("\n[ MLO Configurations ]")
    if isinstance(mlo, list):
        for m in mlo:
            status = "UP" if m.get("mlo_enable") else "DOWN"
            print(f"  {m.get('name', '?'):<15} | SSID: {m.get('mlo_ssid', 'N/A'):<20} | Status: {status}")
    else:
        print("  No MLO configuration found.")
    print()

async def print_system(api):
    """Pretty print system status summary."""
    info = await api.system_get_info()
    status = await api.system_get_status()
    fan = await api.fan_get_status()
    led = await api.led_get_config()
    
    print("\n" + "="*50)
    print(" SYSTEM SUMMARY ".center(50, "="))
    print("="*50)
    print(f"Model:      {info.get('model', 'Unknown')} ({info.get('vendor', 'GL.iNet')})")
    print(f"Firmware:   {info.get('firmware_version')} [{info.get('firmware_type')}]")
    
    uptime_sec = status.get('uptime', 0)
    days = uptime_sec // 86400
    hours = (uptime_sec % 86400) // 3600
    mins = (uptime_sec % 3600) // 60
    print(f"Uptime:     {days}d {hours}h {mins}m")
    
    load = status.get('load', [0, 0, 0])
    print(f"Load Avg:   {load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}")
    
    mem = status.get('memory', {})
    if mem:
        total = mem.get('total', 1)
        used = total - mem.get('free', 0)
        print(f"Memory:     {used//1024}/{total//1024} KB ({(used/total)*100:.1f}%)")

    print(f"Fan Status: {fan.get('mode', 'N/A')} | RPM: {fan.get('rpm', 0)} | Temp: {fan.get('temp', 0)}°C")
    print(f"LEDs:       {'ENABLED' if led.get('led_enable') else 'DISABLED'}")
    print("="*50 + "\n")

async def print_network(api):
    """Pretty print network/WAN status."""
    wan = await api.kmwan_get_status()
    cable = await api.get_cable_status()
    rules = await api.firewall_get_port_forward_list()
    
    print("\n[ WAN / Connectivity Status ]")
    if isinstance(wan, dict):
        # Check for common interfaces like 'wan', 'wwan', 'tethering'
        found_wan = False
        for iface, detail in wan.items():
            if isinstance(detail, dict) and "status" in detail:
                found_wan = True
                print(f"  {iface:<10}: {detail.get('status').upper()} | IP: {detail.get('ip', 'N/A')}")
        if not found_wan: print("  No active WAN interface detected.")
    else:
        print("  Could not retrieve KMWAN status.")

    print("\n[ Physical Port Status ]")
    if isinstance(cable, list):
        for port in cable:
            status = port.get('status', 'down').upper()
            speed = f"{port.get('speed')} Mbps" if status == "UP" else "--"
            print(f"  Port {port.get('port', '?')}: {status:<6} | Speed: {speed}")
    else:
        print("  Could not retrieve cable status.")

    print("\n[ Active Port Forwards ]")
    if isinstance(rules, list):
        enabled_rules = [r for r in rules if r.get('enabled')]
        if enabled_rules:
            for r in enabled_rules:
                print(f"  {r.get('name', 'Unnamed'):<15}: {r.get('src_port')} -> {r.get('dest_ip')}:{r.get('dest_port')}")
        else:
            print("  No active port forwarding rules.")
    print()

async def main():
    parser = argparse.ArgumentParser(
        description="GL-iNet API CLI Tool - Read-only standalone tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Connection params
    conn_group = parser.add_argument_group("connection arguments")
    conn_group.add_argument("--host", help="Router URL/IP (default: 192.168.8.1)")
    conn_group.add_argument("--user", help="Username (default: root)")
    conn_group.add_argument("--password", help="Password (will prompt if not provided)")
    conn_group.add_argument("--ssl", action="store_true", help="Verify SSL (default: False)")
    conn_group.add_argument("--http", action="store_true", help="Use HTTP instead of HTTPS")

    # Command to run
    parser.add_argument("command", choices=["help", "interfaces", "clients", "system", "network", "function"], default="help", nargs="?", help="Command to run")
    parser.add_argument("params", nargs="*", help="Function name (if using 'function') or parameters")

    args = parser.parse_args()

    # 1. Resolve credentials
    host = args.host
    user = args.user or "root"
    pw = args.password
    
    # Identify read-only commands
    dummy_api = GLiNetAPI("127.0.0.1")
    EXCLUDED = ["login", "challenge", "call", "call_with_params", "call_endpoint", "batch_call"]
    readonly_methods = {
        name: getattr(dummy_api, name)
        for name in dir(dummy_api)
        if not name.startswith("_") 
        and inspect.iscoroutinefunction(getattr(dummy_api, name))
        and name not in EXCLUDED
        and not name.startswith("set_")
        and "_set_" not in name
        and "reboot" not in name
    }

    if args.command == "help":
        print("\n--- GL-iNet API Standalone Tool ---")
        print("\nUsage:")
        print("  python3 glinet_tool.py <command>")
        print("\nCommands:")
        print("  system                     Display hardware, firmware, and resource summary")
        print("  clients                    List connected & known clients in a table")
        print("  interfaces                 Show WiFi (Standard & MLO) identities and status")
        print("  network                    Show WAN connectivity, port status, and forwarding rules")
        print("  function <function_name>   Gets the raw JSON output of a function")
        print("\nAvailable Functions for 'function' command:")
        for name in sorted(readonly_methods.keys()):
            print(f"  - {name}")
        print()
        return

    # 2. Resolve Host & Credentials
    if not host:
        host = input(f"Router URL/IP (default 192.168.8.1): ").strip() or "192.168.8.1"
        
    if not pw:
        pw = getpass(f"Password for {user}@{host}: ").strip()

    api = GLiNetAPI(host, user, pw, verify_ssl=args.ssl, use_https=not args.http)
    
    try:
        print(f"[*] Connecting to {api.host}...")
        await api.login()
        
        if args.command == "system":
            await print_system(api)
        elif args.command == "clients":
            await print_clients(api)
        elif args.command == "interfaces":
            await print_interfaces(api)
        elif args.command == "network":
            await print_network(api)
        elif args.command == "function":
            if not args.params:
                print("[!] Error: 'function' command requires a function name.")
                return
            
            func_name = args.params[0]
            func_params = args.params[1:]
            
            if func_name not in readonly_methods:
                print(f"[!] Error: '{func_name}' is not an available read-only function.")
                return
            
            method = getattr(api, func_name)
            sig = inspect.signature(method)
            
            bound_args = []
            for i, (p_name, p_param) in enumerate(sig.parameters.items()):
                if i < len(func_params):
                    val = func_params[i]
                    if p_param.annotation == bool:
                        val = val.lower() in ["true", "1", "yes", "on", "t"]
                    elif p_param.annotation == int:
                        val = int(val)
                    bound_args.append(val)
                elif p_param.default == inspect.Parameter.empty:
                    print(f"[!] Missing required parameter: {p_name}")
                    return

            result = await method(*bound_args)
            print(json.dumps(result, indent=2))
            
    except Exception as e:
        print(f"\n[!] Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(0)
