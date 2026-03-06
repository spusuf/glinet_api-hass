"""
GL-iNet Router API Client
"""
import hashlib
import json
import logging
import httpx
import asyncio

from passlib.hash import md5_crypt, sha256_crypt, sha512_crypt

_LOGGER = logging.getLogger(__name__)

class GLiNetAPI:
    """Standalone API client for GL-iNet V4 firmware (OpenWrt-based)."""

    def __init__(self, host: str, username: str = "root", password: str = "", session: httpx.AsyncClient = None, verify_ssl: bool = False, use_https: bool = True):
        clean_host = host.replace("https://", "").replace("http://", "").rstrip('/')
        if "://" in host:
            self.host = host.rstrip('/')
        else:
            proto = "https" if use_https else "http"
            self.host = f"{proto}://{clean_host}"
        
        self.api_url = f"{self.host}/rpc"
        self.username = username
        self.password = password
        self.sid = None
        self._login_lock = asyncio.Lock()
        self.session = session
        self.verify_ssl = verify_ssl
        self._semaphore = asyncio.Semaphore(4)

    def _get_client(self) -> httpx.AsyncClient:
        """Create a client that mimics curl and avoids HA blocking calls."""
        if self.session is None or self.session.is_closed:
            self.session = httpx.AsyncClient(
                verify=self.verify_ssl,
                http2=False, # Strictly HTTP/1.1
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            )
        return self.session

    async def _post(self, payload):
        """Internal helper for posting to the RPC endpoint."""
        client = self._get_client()

        headers = {
            "glinet": "1",
            "Content-Type": "application/json",
            "User-Agent": "curl/8.18.0",
            "Connection": "close",
            "Accept": "application/json",
        }
        
        data_str = json.dumps(payload)
        
        try:
            resp = await client.post(
                self.api_url, 
                content=data_str, 
                headers=headers,
                timeout=10.0
            )
            resp.raise_for_status()
            return resp.json()
        except (httpx.RemoteProtocolError, httpx.WriteError) as e:
            _LOGGER.error("Router sent TCP Reset. Resetting session and retrying.")
            await self.session.aclose()
            self.session = None
            raise Exception(f"Router reset connection (Error 0). Retrying session: {e}") from e
        except Exception as e:
            _LOGGER.error("Communication error: %s", e)
            raise


    async def batch_call(self, calls: list[tuple[str, str, dict]]):
        """
        Emulate batch execution by running all calls concurrently.
        GL-iNet routers do not support JSON-RPC batch arrays (-32600), so we
        fire individual requests in parallel via asyncio.gather instead.
        'calls' is a list of (module, method, params) tuples.
        Returns a list of response-shaped dicts keyed by 'id', 'result', and optionally 'error'.
        """
        if not self.sid:
            await self.login()

        async def _single_call(idx: int, module: str, method: str, params: dict):
            """Send one RPC call and return a response-shaped dict with an 'id'."""
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": [self.sid, module, method, params],
                "id": idx,
            }
            try:
                async with self._semaphore:
                    data = await self._post(payload)
                if isinstance(data, dict):
                    data["id"] = idx
                return data
            except Exception as exc:
                _LOGGER.debug(
                    "Concurrent call %s (%s.%s) failed: %s", idx, module, method, exc
                )
                return {"id": idx, "error": {"code": -1, "message": str(exc)}}

        tasks = [
            _single_call(i, module, method, params)
            for i, (module, method, params) in enumerate(calls)
        ]

        results = await asyncio.gather(*tasks)

        for item in results:
            if "error" in item:
                idx = item.get("id", "?")
                err_info = item["error"]
                _LOGGER.debug(
                    "Call %s (%s.%s) error (code %s): %s",
                    idx,
                    calls[idx][0] if isinstance(idx, int) and idx < len(calls) else "?",
                    calls[idx][1] if isinstance(idx, int) and idx < len(calls) else "?",
                    err_info.get("code"),
                    err_info.get("message", err_info),
                )

        return list(results)

    async def challenge(self):
        """Get the login challenge parameters."""
        payload = {
            "jsonrpc": "2.0",
            "method": "challenge",
            "params": {"username": self.username},
            "id": 1
        }
        data = await self._post(payload)
        if "result" not in data:
            raise Exception(f"Challenge failed: {data}")
        return data["result"]

    async def login(self):
        """Authenticate according to GL-iNet v4 specs."""
        res = await self.challenge()
        nonce = res.get("nonce")
        salt = res.get("salt")
        alg = res.get("alg")
        hash_method = res.get("hash-method", "md5")
        
        if alg == 1:  # MD5
            cipher_password = md5_crypt.using(salt=salt).hash(self.password)
        elif alg == 5:  # SHA-256
            cipher_password = sha256_crypt.using(salt=salt, rounds=5000).hash(self.password)
        elif alg == 6:  # SHA-512
            cipher_password = sha512_crypt.using(salt=salt, rounds=5000).hash(self.password)
        else:
            raise ValueError(f"Unsupported algorithm (alg={alg}) from router challenge.")

        data = f"{self.username}:{cipher_password}:{nonce}"
        
        if hash_method == "md5":
            hsh = hashlib.md5(data.encode()).hexdigest().lower()
        elif hash_method == "sha256":
            hsh = hashlib.sha256(data.encode()).hexdigest().lower()
        elif hash_method == "sha512":
            hsh = hashlib.sha512(data.encode()).hexdigest().lower()
        else:
            raise ValueError(f"Unsupported hash-method ({hash_method}) from router challenge.")
            
        payload = {
            "jsonrpc": "2.0",
            "method": "login",
            "params": {
                "username": self.username,
                "hash": hsh
            },
            "id": 1
        }
        data = await self._post(payload)
        if "result" not in data or "sid" not in data["result"]:
            raise Exception(f"Login failed: {data}")
            
        self.sid = data["result"]["sid"]
        return self.sid

    async def call(self, module: str, method: str, **params):
        """Invoke a remote procedure call."""
        if not self.sid:
            async with self._login_lock:
                if not self.sid: await self.login()
            
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": [self.sid, module, method, params],
            "id": 1
        }
        
        data = await self._post(payload)
        
        if "error" in data:
            error_code = data["error"].get("code")
            error_msg = data["error"].get("message", "")
            if error_code in [-32000, -32002] or "Access denied" in error_msg:
                _LOGGER.warning("Access denied to %s.%s. Attempting re-login...", module, method)
                async with self._login_lock:
                    current_sid = self.sid
                    await self.login()

                    if not self.sid or self.sid == current_sid:
                        raise Exception("Re-login failed to generate a new session ID")
                return await self.call(module, method, **params)
        
            raise Exception(f"RPC Error [{module}.{method}]: {error_msg} ({data['error']})")
            
        return data.get("result")

    async def call_with_params(self, module: str, method: str, params: dict):
        """Like call() but accepts a plain dict instead of **kwargs."""
        if not self.sid:
            async with self._login_lock:
                if not self.sid:
                    await self.login()

        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": [self.sid, module, method, params],
            "id": 1,
        }

        data = await self._post(payload)

        if "error" in data:
            error_code = data["error"].get("code")
            error_msg = data["error"].get("message", "")
            if error_code in [-32000, -32002] or "Access denied" in error_msg:
                _LOGGER.warning("Access denied to %s.%s. Re-logging in.", module, method)
                async with self._login_lock:
                    current_sid = self.sid
                    await self.login()
                    if not self.sid or self.sid == current_sid:
                        raise Exception("Re-login failed to generate a new session ID")
                return await self.call_with_params(module, method, params)
            raise Exception(f"RPC Error [{module}.{method}]: {error_msg} ({data['error']})")

        return data.get("result")

    async def call_endpoint(self, endpoint: str, params: dict | None = None):
        """Call an RPC endpoint given as 'module/method' with an optional params dict."""
        if "/" not in endpoint:
            raise ValueError(f"call_endpoint expects 'module/method', got: {endpoint!r}")
        module, method = endpoint.split("/", 1)
        return await self.call_with_params(module, method, params or {})



    async def system_get_info(self):
        """Retrieve router model, firmware and hardware info."""
        return await self.call("system", "get_info")

    async def system_get_status(self):
        """Retrieve system status."""
        return await self.call("system", "get_status")

    async def fan_get_status(self):
        """Retrieve fan status."""
        return await self.call("fan", "get_status")

    async def firewall_get_port_forward_list(self):
        """Retrieve port forward list."""
        return await self.call("firewall", "get_port_forward_list")

    async def get_clients(self):
        """List all connected clients."""
        return await self.call("clients", "get_list")

    async def set_client_block(self, mac: str, blocked: bool):
        """Block or unblock a client from WAN access."""
        return await self.call("clients", "block_client", mac=mac, block=blocked)

    async def get_wifi_ifaces(self):
        """Get all standard WiFi interfaces."""
        return await self.call("wifi", "get_config")

    async def set_wifi_iface(self, device: str, iface: str, enabled: bool):
        """Toggle a standard WiFi interface."""
        return await self.call("wifi", "set_config", device=device, iface_name=iface, enabled=enabled)

    async def get_mlo_config(self):
        """Get MLO-specific WiFi interfaces."""
        return await self.call("wifi", "get_mlo_config")

    async def set_mlo_status(self, iface_name: str, enabled: bool):
        """Toggle an MLO interface. Router only needs name + mlo_enable."""
        return await self.call_with_params(
            "wifi", "set_mlo_config", {"name": iface_name, "mlo_enable": enabled}
        )

    async def upgrade_check_firmware_online(self):
        """Retrieve system status including WiFi summary."""
        return await self.call("upgrade", "check_firmware_online")

    async def kmwan_get_status(self):
        """Retrieve mwan status."""
        return await self.call("kmwan", "get_status")

    async def kmwan_get_config(self):
        """Retrieve mwan config."""
        return await self.call("kmwan", "get_config")

    async def firewall_set_port_forward(self, rule_data: dict):
        """Update/Toggle a port forward rule. Requires the full rule object."""
        return await self.call_with_params("firewall", "set_port_forward", rule_data)

    async def get_cable_status(self):
        """Retrieve cable status."""
        return await self.call("cable", "get_status")

    async def led_get_config(self):
        """Retrieve LED config."""
        return await self.call("led", "get_config")

    async def led_set_config(self, led_enable: bool):
        """Set LED config."""
        return await self.call("led", "set_config", led_enable=led_enable)

    async def system_reboot(self, delay: int = 1):
        """Reboot the router."""
        return await self.call("system", "reboot", delay=delay)
