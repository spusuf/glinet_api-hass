# TO DO & API

- [x] Test combined MACs
- [x] Prepoulate host with gateway
- [x] Autodiscover GLiNet router

- [x] Secure mode
- [x] ERROR HANDLING
- [x] HTTPS connection to API
- [x] Enable appliances by default (to see if they drop off)
- [x] Check OpenWRT RPC endpoints ?
- [x] Change MB to GB for eMMC
- [x] Change entity IDs to be9300_xxxx
- [x] convert B to GB for download
- [x] convert kB/s to mB/s for speed
- [x] Make sure trhoughput is accurate
- [ ] Before shipping:
  - [x] Clean config flow text
  - [x] Polish standalone API tool
  - [x] Update readme with all functions
  - [x] Remove password from tests
  - [x] Assume 192.168.8.1 not 1.1
  - [x] Check for unused testing functions
  - [x] Code cleanup

## Router

- [x] Model name (Use MODEL_MAP in const to return Flint 3)
- [x] Device MAC
- [x] Visit (goes to configured ip)

## Sensors

- [x] CPU: 100% [cores: 4, 1m load: 4.00, 5m load: 4.00, 15m load: 4.00, accel: hw+sw, arch: ARMv8]
- [x] Memory: 50% [used: 500MB, total: 1000MB]
- [x] eMMC: 10% [used: 800MB, total: 8000MB]
- [x] Temperature: 70c
- [x] Fan: 100% [rpm: 5500]
- [x] Firmware: Minor update available [current: 4.8.3, latest: 4.8.4]
- [x] Uptime: 3 days
- [x] Guest Clients: 1 [cable: 0, wireless: 1, list?]
- [x] LAN Clients: 14 [cable: 8, wireless: 6, list?]
- [x] Total Clients: 15 [cable: 8, wireless: 7, list?]
- [x] Internet: WAN [ipv4: ip4, ipv6: ip6, type: Failover/Load Balancing, wan: Online(.status_v4), wan2: offline, ...]

## Controls

- [x] xGHz WiFi: ON
  - [x] SSID: LAN of
  - [x] Band: xGH(multi for MLO)
  - [x] Mode: be
  - [x] Width: 40
  - [x] Password: password
- [x] LED: ON/OFF
- [x] Reboot PRESS
- [x] Port 25565 OPEN (Port controls)
- [x] Builtin Services(tailscale, openvpn, tor, ddns, nas, adguard) ON

## Devices

- [x] Class map (presense: phones + watch, monitor: smartappliances, sound, tv)
- [x] IF PRESENSE GROUP BY MAC
- [x] Phone 2: Online (from any listed MAC) [Connected AP: LAN of, ip: ip]
- [x] MAC (including linked MACs)
- [ ] Block Internet ON (good for IoT or parental controls) -> Doesn't work
- [x] Uplink speed 1000Mbps
- [x] Recieve speed 1000Mbps
- [x] Total TX 1GB
- [x] Total RX 10GB
- [ ] Link rate -> Can't find in endpoints

## !! Secure mode toggle during initial setup:

- Populates wifi SSID and passwords in attributes
- Populates device IPs in attributes (including public WAN IP)
- Enables fan control
- Displays and adds controls for port forwards

# Out of scope

- WAN speed+ping+jitter?
- [ ] qos: Off [speed_limit, priority, cake_model]
