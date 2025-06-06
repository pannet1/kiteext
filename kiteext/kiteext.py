import urllib.parse
import json
import six
import kiteconnect.exceptions as ex
import logging
import requests

from kiteconnect import KiteConnect, KiteTicker

log = logging.getLogger(__name__)


class KiteExtTicker(KiteTicker):
    def __init__(self, *args, **kwargs):
        KiteTicker.__init__(self, *args, **kwargs)

    def _parse_text_message(self, payload):
        """Parse text message."""
        # Decode unicode data
        if not six.PY2 and type(payload) == bytes:
            payload = payload.decode("utf-8")

        try:
            data = json.loads(payload)
        except ValueError:
            return

        # Order update callback
        if self.on_order_update and data.get("type") == "order":
            self.on_order_update(self, data)

        # Custom error with websocket error code 0
        if data.get("type") == "error":
            self._on_error(self, 0, data)


class KiteExt(KiteConnect):
    def login_with_credentials(self, userid, password, pin):
        self.headers = {
            "x-kite-version": "3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.128 Safari/537.36",
        }
        self.user_id = userid
        self.password = password
        self.twofa = pin
        self.reqsession = requests.Session()
        r = self.reqsession.post(
            self.root + self._routes["api.login"],
            data={"user_id": self.user_id, "password": self.password},
        )
        print(f"kiteext login with credentials r contains {r}")
        r = self.reqsession.post(
            self.root + self._routes["api.twofa"],
            data={
                "request_id": r.json()["data"]["request_id"],
                "twofa_value": self.twofa,
                "user_id": r.json()["data"]["user_id"],
            },
        )

        self.enctoken = r.cookies.get("enctoken")
        self.public_token = r.cookies.get("public_token")
        self.user_id = r.cookies.get("user_id")

        self.headers["Authorization"] = "enctoken {}".format(self.enctoken)

    def login_using_enctoken(self, userid, enctoken, public_token):
        self.headers = {
            "x-kite-version": "3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.128 Safari/537.36",
        }
        self.user_id = userid
        self.reqsession = requests.Session()

        self.enctoken = enctoken
        self.public_token = public_token
        # self.user_id = r.cookies.get('user_id')

        self.headers["Authorization"] = "enctoken {}".format(self.enctoken)

    def __init__(self, api_key="kitefront", userid=None, *args, **kw):
        KiteConnect.__init__(self, api_key=api_key, *args, **kw)

        if userid is not None:
            self.user_id = userid

        self._routes.update(
            {
                "api.login": "/api/login",
                "api.twofa": "/api/twofa",
                "api.misdata": "/margins/equity",
            }
        )

    def set_headers(self, enctoken, userid=None):
        self.public_token = enctoken
        self.enctoken = enctoken
        if userid is not None:
            self.user_id = userid
        if self.user_id is None:
            raise Exception(
                f"userid cannot be none, either login with credentials first or set userid here"
            )
        self.headers = {
            "x-kite-version": "3",
            "Authorization": "enctoken {}".format(self.enctoken),
        }

    def kws(self, api_key="kitefront"):
        return KiteExtTicker(
            api_key=api_key,
            access_token="&user_id="
            + self.user_id
            + "&enctoken="
            + urllib.parse.quote(self.enctoken)
            + "&user-agent=kite3-web&version=3.0.7",
            root="wss://ws.zerodha.com",
        )

    def ticker(self, api_key="kitefront", enctoken=None, userid=None):
        if enctoken is not None:
            self.enctoken = enctoken
        if userid is not None:
            self.user_id = userid
        if self.user_id is None:
            raise Exception(
                f"userid cannot be none, either login with credentials first or set userid here"
            )
        return KiteExtTicker(
            api_key=api_key,
            access_token="&user_id="
            + self.user_id
            + "&enctoken="
            + urllib.parse.quote(self.enctoken)
            + "&user-agent=kite3-web&version=3.0.7",
            root="wss://ws.zerodha.com",
        )

    def instruments(self, exchange=None):
        """
        Retrieve the list of market instruments available to trade.

        Note that the results could be large, several hundred KBs in size,
        with tens of thousands of entries in the list.

        - `exchange` is specific exchange to fetch (Optional)
        """
        # if exchange:
        #    return self._parse_instruments(self._get("market.instruments", url_args={"exchange": exchange}))
        # else:
        #    return self._parse_instruments(self._get("market.instruments.all"))
        if exchange:
            data = requests.get(f"{self._default_root_uri}/instruments/{exchange}")
            return self._parse_instruments(data.content)
        else:
            data = requests.get(f"{self._default_root_uri}/instruments")
            return self._parse_instruments(data.content)

    # NOTE NEW
    def _request(
        self,
        route,
        method,
        url_args=None,
        params=None,
        is_json=False,
        query_params=None,
    ):
        """Make an HTTP request."""
        # Form a restful URL
        if url_args:
            uri = self._routes[route].format(**url_args)
        else:
            uri = self._routes[route]

        if uri[0] != "/":
            uri = "/" + uri

        url = "https://kite.zerodha.com/oms" + uri

        headers = self.headers

        # Custom headers
        # headers = {
        #     'X-Kite-Version': '3',  # For version 3
        #     'User-Agent': self._user_agent()
        # }

        # if self.api_key and self.access_token:
        #     # set authorization header
        #     auth_header = self.api_key + ':' + self.access_token
        #     headers['Authorization'] = 'token {}'.format(auth_header)

        if self.debug:
            log.debug(
                "Request: {method} {url} {params} {headers}".format(
                    method=method, url=url, params=params, headers=headers
                )
            )

        # prepare url query params
        if method in ["GET", "DELETE"]:
            query_params = params

        try:
            r = self.reqsession.request(
                method,
                url,
                json=params if (method in ["POST", "PUT"] and is_json) else None,
                data=params if (method in ["POST", "PUT"] and not is_json) else None,
                params=params if method in ["GET", "DELETE"] else None,
                headers=headers,
                verify=not self.disable_ssl,
                allow_redirects=True,
                timeout=self.timeout,
                proxies=self.proxies,
            )
        # Any requests lib related exceptions are raised here - http://docs.python-requests.org/en/master/_modules/requests/exceptions/
        except Exception as e:
            raise e

        if self.debug:
            log.debug(
                "Response: {code} {content}".format(
                    code=r.status_code, content=r.content
                )
            )

        # Validate the content type.
        if "json" in r.headers["content-type"]:
            try:
                data = json.loads(r.content.decode("utf8"))
            except ValueError:
                raise ex.DataException(
                    "Could not parse the JSON response received from the server: {content}".format(
                        content=r.content
                    )
                )

            # api error
            if data.get("error_type"):
                # Call session hook if its registered and TokenException is raised
                if (
                    self.session_expiry_hook
                    and r.status_code == 403
                    and data["error_type"] == "TokenException"
                ):
                    self.session_expiry_hook()

                # native Kite errors
                exp = getattr(ex, data["error_type"], ex.GeneralException)
                raise exp(data["message"], code=r.status_code)

            return data["data"]
        elif "csv" in r.headers["content-type"]:
            return r.content
        else:
            raise ex.DataException(
                "Unknown Content-Type ({content_type}) with response: ({content})".format(
                    content_type=r.headers["content-type"], content=r.content
                )
            )
