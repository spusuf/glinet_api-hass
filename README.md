# GL-iNet API integration for Home Assistant

## Installation

Add the custom repository to HACS and install it.

Being listed on HACS by default and an "add to HACS" button is pending review.

## Features

I don't list entity list spam and therefore a lot of the information is in the attributes of the sensor it relates to (click the 3 dots then attributes or use the State content field of the Tile card to see these).

Supports MLO

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
| Download Speed          | Instantaneous download speed      |                                                 |
| Upload Speed            | Instantaneous upload speed        |                                                 |

## Groups
There are two types of groups: device groups and guest groups.
Device groups allow you to combine multiple MAC addresses into one device (useful for combining one device's multiple MACs such as the 2.4GHz interface, 5GHz interface, 6GHz interface, Ethernet, etc.)
Guest groups are to allow you to combine multiple discrete devices into a person for Guest count. This allows you to track how many guests are over at your home, not only how many guest devices are connected to your guest wifi. For example if a guest brings their phone and laptop that should count as one guest in your home, not two. I wouldn't recommend adding yourself to a group because if you leave your laptop or tablet or watch at home, doesnt mean YOU (your phone or whatever your actually track) is at home (plus just add multiple devices to your home assistant person).

## Secure Mode

For extra security (mostly piece of mind) does not populate the following attributes:

- WiFi SSIDs and passwords
- MAC address visibility (they will still be present in logs for device tracking)
- IP address visibility (both public and internal IPs)
- Fan Control (won't let a hacker cook your router)
- Port forwarding controls (duh, should be noted that I have not and will not add the ability to CREATE port forwards, only toggle existing ones)

Great for guests have access to your attributes (if they have HA admin), you frequently take screenshots of your home assistant attributes, or you don't trust your security and isolation from the wider internet.

## Notes

1. CPU usage is normalised for core count (e.g a 4 core router will show 25% for 100% load on a single thread)
2. Assumes max fan speed of 5600rpm (the value my flint 3 peaked to when manually overrided to 100% was 5531rpm, nothing should break if it is higher or lower but be aware it will affect accuracy). You can change this in const.py or create an issue if there is a known max for your model (see note 2).
3. See secure mode
4. Services are dynamically pulled from the router such as Tailscale, WireGuard, Tor, Parental Controls, AdGuard, etc. If I have set a definitions for them they will have controls and related attributes otherwise will just show as a On/Off status.
5. See groups
6. Classes are the icons set in the GLiNet webUI or app (e.g phone, laptop, etc). Defaults to phones (for wifi based presence detection) and smartappliances (for loss of connectivity/battery and Internet blocking), any glienet class can be configured during setup. (WIP -> Exclude devices in guest networks)
7. Tested on my Flint 3. If you test on a different model and it DOES or DOES NOT work please create an issue for your model so we can track working devices and broken features/changes in that issue.
8. This integration relies on the GLiNet API directly not any python libraries (such as gli4py). API is no longer public on the GL-iNet website, but is archived at: https://web.archive.org/web/20240121142533/https://dev.gl-inet.com/router-4.x-api . I have used the last available version, probed, as well as "guess and checked" endpoints, but there may be extra features or future breaking changes.
9. Sorry about the screenshots, HDR on Hyprland isnt perfect
10. This code is probably messy as hell, I created a bunch of functions only to come back and completely rework them weeks later plus I'm not a professional dev so I'm not sure if there's standards that I've missed. I would encourage any seasoned developers to give the code a review and if possible submit pull requests.

### Possible but out of scope:

I personally dont use these and wouldnt want to waste time on something nobody would use:

- Changing client RX/TX limits
- Change MultiWAN Mode Failover/LoadBalance
- View and edit the router native schedules (for wifi, mlo, led, etc)
- Define a list of software packages to track
- Set client alias to sync with HA (clients.alias), e.g HA friendly name would override the alias
- Set client class to sync with HA (clients.class), e.g mdi:cellphone would set class to phone
- USB storage stats, (connected, storage size and usage)?
- Instantaneous RX/TX?
