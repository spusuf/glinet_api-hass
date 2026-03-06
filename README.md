# GL-iNet API integration for Home Assistant

Yet another Home Assistant integration for GL-iNet routers. Written from the ground up, and uses the API directly not the python library.

Highlights: Supports MLO, autodiscovery, automatic device tracking, HTTPS, and more.

## Installation

Add the custom repository to HACS and install it.

Being listed on HACS by default and an "add to HACS" button is pending review.

## Features

I don't list entity list spam and therefore a lot of the information is in the attributes of the sensor it relates to (click the 3 dots then attributes or use the State content field of the Tile card to see these).

### Router

| Entity         | State                            | Attributes                                                                     |
| -------------- | -------------------------------- | ------------------------------------------------------------------------------ |
| CPU            | Usage % [1]                      | 1m/5m/15m load                                                                 |
| Memory         | Usage %                          | Used/Total/Free/Cache (MB)                                                     |
| eMMC           | Usage %                          | Used/Total/Free (MB)                                                           |
| Temp           | temp                             |                                                                                |
| Fan Speed      | Speed % [2]                      | Speed/Max Speed (rpm)                                                          |
| Uptime         | uptime                           |                                                                                |
| Firmware       | Update Available                 | Current version, new version?, openWRT version, release notes?, prompt?, type? |
| WiFi interface | On/Off                           | Channel, bandwidth, wifi spec, SSID [3], password [3], guest, hidden           |
| Internet       | Online/Offline/Fallback/MultiWAN |                                                                                |
| Lights         | On/Off                           |                                                                                |
| Services [4]   | On/Off                           | Attributes if they have a definition, see [4] or edit const.py                 |
| Guest Clients  | Number of devices                |                                                                                |
| Guest Count    | Number of guest groups [5]       |                                                                                |
| LAN Clients    | Number of devices                |                                                                                |
| People home    | Number of tracked devices        |                                                                                |
| Total clients  | Number of devices                |                                                                                |

### Devices

| Entity                  | State                             | Attributes                                      |
| ----------------------- | --------------------------------- | ----------------------------------------------- |
| (Device Name)           | State for that MAC Address        | Interface, Alias, IP[3], MAC [3], MAC group [5] |
| Presence/Connection [6] | If the MAC/MAC group is connected |                                                 |
| Data Downloaded         | Total data downloaded             |                                                 |
| Data Uploaded           | Total data uploaded               |                                                 |
| Download Speed [7]      | Instantaneous download speed      | Download speed in Megabits/second               |
| Upload Speed [7]        | Instantaneous upload speed        | Upload speed in Megabits/second                 |

## Groups

## Secure Mode

For extra security (mostly piece of mind) does not populate the following attributes:

- WiFi SSIDs and passwords
- IP address visibility (both public and internal IPs)
- Fan Control (won't let a hacker cook your router)
- Port forwarding controls (duh, should be noted that I have not and will not add the ability to CREATE port forwards, only toggle existing ones)

Great for if you want to take screenshots of your dashboards, guests have access to your attributes (if they have HA admin), or you don't trust your security and isolation from the wider internet.

## Notes

1. CPU usage is normalised for core count (e.g a 4 core router will show 25% for 100% load on a single thread)
2. Assumes max fan speed of 5600rpm (the value my flint 3 peaked to when manually overrided to 100% was 5531rpm, nothing should break if it is higher or lower but be aware it will affect accuracy). You can change this in const.py or create an issue if there is a known max for your model (see note 2).
3. See secure mode
4. Services are dynamically pulled from the router such as Tailscale, WireGuard, Tor, Parental Controls, AdGuard, etc. If I have set a definitions for them they will have controls and related attributes otherwise will just show as a On/Off status.
5. See groups
6. Classes are the icons set in the GLiNet webUI or app (e.g phone, laptop, etc). Defaults to phones (for wifi based presence detection) and smartappliances (for loss of connectivity/battery and Internet blocking), any glienet class can be configured during setup. (WIP -> Exclude devices in guest networks)
7. If you have hardware acceleration on (which you probably should) Download and Upload speed are incredibly incorrect (including) in the official Web UI and mobile app. These speeds (and potentially totals) will be between 10-2000x incorrect.
8. Tested on my Flint 3. If you test on a different model and it DOES or DOES NOT work please create an issue for your model so we can track working devices and broken features/changes in that issue.
9. This integration relies on the GLiNet API directly not any python libraries (such as gli4py). API is no longer public on the GL-iNet website, but is archived at: https://web.archive.org/web/20240121142533/https://dev.gl-inet.com/router-4.x-api . I have used the last available version of the API, probed my router, and "guess and checked" endpoints, but there may be extra features or future breaking changes.
10. Sorry about the screenshots, HDR on Hyprland isnt perfect
11. This code is probably messy as hell, I created a bunch of functions only to come back and completely rework them weeks later plus I'm not a professional dev so I'm not sure if there's standards that I've missed. I would encourage any seasoned developers to give the code a review and if possible submit pull requests.

### Possible but out of scope:

I personally dont use these and wouldnt want to waste time on something nobody would use:

- Changing client download/upload limits
- Viewing client realtime link speed (e.g max negotiated wireless transmit/receive speed or ethernet speed)
- Change MultiWAN Mode between Failover and LoadBalance
- View and edit the router native schedules (for wifi, mlo, led, etc)
- Define a list of software packages to track
- Set client alias to sync with HA (clients.alias), e.g HA friendly name would override the alias
- Set client class to sync with HA (clients.class), e.g mdi:cellphone would set class to phone
- USB storage stats, (connected, storage size and usage)?
