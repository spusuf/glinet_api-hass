"""Constants for the GL-iNet API integration."""
DOMAIN = "glinet_api"

DEFAULT_HOST = "192.168.8.1"
DEFAULT_USERNAME = "root"

MAX_FAN_SPEED = 5600

CONF_TITLE = "title"
CONF_USE_HTTPS = "use_https"
CONF_TRACKED_CLASSES = "tracked_classes"
CONF_MONITOR_CLASSES = "monitor_classes"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_MAC_GROUPS = "mac_groups"
CONF_GUEST_GROUPS = "guest_groups"
CONF_TRUSTED_MODE = "trusted_mode"

DEFAULT_SCAN_INTERVAL = 30

DEFAULT_TRACKED = ["phone"]
DEFAULT_MONITORED = ["smartappliances", "server"]

MODEL_MAP = {
    "be9300": "Flint 3",
    "mt6000": "Flint 2",
    "ax1800": "Flint",
    "axt1800": "Slate AX",
    "mt3000": "Beryl AX",
    "mt2500": "Brume 2",
}

ALL_DEVICE_CLASSES = [
    "phone",
    "television",
    "computer",
    "smartappliances",
    "sound",
    "server",
    "games",
    "laptop",
    "wearable",
    "tablet",
    "gateway",
    "camera",
    "printer",
    "nas",
    "switch"
]

GUEST_CLIENT_TYPES = [3, 4, 10, 12]

CLIENT_TYPE_MAP = {
    0:  "2.4 GHz",
    1:  "5 GHz",
    2:  "Wired",
    3:  "2.4 GHz Guest",
    4:  "5 GHz Guest",
    5:  "Unknown",
    6:  "Dongle",
    7:  "Bypass Route",
    8:  "Unknown",
    9:  "MLO",
    10: "MLO Guest",
    11: "6 GHz",
    12: "6 GHz Guest",
}

KNOWN_SERVICES = {
    "wgserver": {
        "name": "WireGuard Server",
        "actions": {
            "on": {"endpoint": "wg-server/start", "payload": {}},
            "off": {"endpoint": "wg-server/stop", "payload": {}}
        },
        "attributes": {
            "tunnel_ip": {"endpoint": "wg-server/get_status", "attribute": "tunnel_ip"},
        },
        "icon": "mdi:vpn"
    },
    "ovpnserver": {
        "name": "OpenVPN Server",
        "actions": {
            "on": {"endpoint": "ovpn-server/start", "payload": {}},
            "off": {"endpoint": "ovpn-server/stop", "payload": {}}
        },
        "attributes": {
            "tunnel_ip": {"endpoint": "ovpn-server/get_status", "attribute": "tunnel_ip"},
            "protocol": {"endpoint": "ovpn-server/get_config", "attribute": "protocol"},
            "port": {"endpoint": "ovpn-server/get_config", "attribute": "port"},
        },
        "icon": "mdi:vpn"
    },
    "adguard": {
        "name": "AdGuard Home",
        "actions": {
            "on": {"endpoint": "adguardhome/set_config", "payload": {"enabled": True}},
            "off": {"endpoint": "adguardhome/set_config", "payload": {"enabled": False}}
        },
        "attributes": {
        },
        "icon": "mdi:vpn"
    },
    "tor": {
        "name": "Tor",
        "actions": {
            "on": {"endpoint": "tor/set_config", "payload": {"enable": True}},
            "off": {"endpoint": "tor/set_config", "payload": {"enable": False}}
        },
        "attributes": {
        },
        "icon": "mdi:vpn"
    },
    "bark": {
        "name": "Bark",
        "actions": {
            "on": {"endpoint": "bark/set_config", "payload": {"enable": True}},
            "off": {"endpoint": "bark/set_config", "payload": {"enable": False}}
        },
        "attributes": {
        },
        "icon": "mdi:account-child"
    },
    "parental_control": {
        "name": "Parental Control",
        "actions": {
            "on": {"endpoint": "parental_control/set_config", "payload": {"enable": True}},
            "off": {"endpoint": "parental_control/set_config", "payload": {"enable": False}}
        },
        "attributes": {
        },
        "icon": "mdi:account-child"
    },
    "tailscale": {
        "name": "Tailscale",
        "actions": {
            "on": {"endpoint": "tailscale/set_config", "payload": {"enabled": True}},
            "off": {"endpoint": "tailscale/set_config", "payload": {"enabled": False}}
        },
        "attributes": {
            "wan_enabled": {"endpoint": "tailscale/get_config", "attribute": "wan_enabled"},
            "lan_enabled": {"endpoint": "tailscale/get_config", "attribute": "lan_enabled"},
        },
        "icon": "mdi:vpn"
    },

    "zerotier": {
        "name": "ZeroTier",
        "actions": {
            "on": {"endpoint": "zerotier/set_config", "payload": {"enabled": True}},
            "off": {"endpoint": "zerotier/set_config", "payload": {"enabled": False}}
        },
        "attributes": {
            "wan_enabled": {"endpoint": "zerotier/get_config", "attribute": "wan_enabled"},
            "lan_enabled": {"endpoint": "zerotier/get_config", "attribute": "lan_enabled"},
        },
        "icon": "mdi:vpn"
    },
}
