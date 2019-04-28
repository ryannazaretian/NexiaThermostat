import requests
from bs4 import BeautifulSoup

import time
import json

class NexiaThermostat:

    ROOT_URL = "https://www.mynexia.com"
    AUTH_FAILED_STRING = "https://www.mynexia.com/login"

    username = None
    password = None
    house_id = None

    session = None
    last_csrf = None

    thermostat_json = None

    def __init__(self, house_id, username=None, password=None, auto_login=True):

        self.username = username
        self.password = password
        self.house_id = house_id

        self.session = requests.session()
        self.session.max_redirects = 3
        
        if auto_login:
            self.login()

    def login(self):
        print("Logging in as " + self.username)
        token = self._get_authenticity_token("/login")
        if token:
            payload = {
                'login': self.username,
                'password': self.password,
                token['param']: token['token']
            }
            self.last_csrf = token['token']
            print("posting login")
            r = self._post_url("/session", payload)
            self._check_response("Failed to login", r)
        else:
            raise Exception("Failed to get csrf token")

    def _get_authenticity_token(self, url):
        print("getting auth token")
        r = self._get_url(url)
        self._check_response("Failed to get authenticity token", r)
        print("parsing csrf token")
        soup = BeautifulSoup(r.text, 'html5lib')
        param = soup.find("meta", attrs={'name': "csrf-param"})
        token = soup.find("meta", attrs={'name': "csrf-token"})
        if token and param:
            return {
                "token": token['content'],
                "param": param['content']
            }

    def _put_url(self, url, payload):
        print("Starting PUT Request")
        request_url = self.ROOT_URL + url

        if not self.last_csrf:
            self.login()

        headers = {
            "X-CSRF-Token": self.last_csrf,
            "X-Requested-With": "XMLHttpRequest"
        }
        print(headers, payload)
        try:
            r = self.session.put(request_url, payload, headers=headers, allow_redirects=False)
        except requests.RequestException as e:
            print("Error putting url", str(e))
            return None
        if r.status_code == 302 and self.AUTH_FAILED_STRING in r.text:
            # assuming its redirecting to login
            time.sleep(1)
            self.login()
            time.sleep(1)
            return self._put_url(url, payload)

        self._check_response("Failed PUT Request", r)
        return r

    def _post_url(self, url, payload):
        request_url = self.ROOT_URL + url
        try:
            r = self.session.post(request_url, payload)
        except requests.RequestException as e:
            print("Error posting url", str(e))
            return None

        if r.status_code == 302 and self.AUTH_FAILED_STRING in r.text:
            # assuming its redirecting to login
            self.login()
            return self._post_url(url, payload)

        self._check_response("Failed to POST url", r)
        return r

    def _get_url(self, url):
        request_url = self.ROOT_URL + url

        try:
            r = self.session.get(request_url, allow_redirects=False)
        except requests.RequestException as e:
            print("Error getting url", str(e))
            return None

        if r.status_code == 302 and self.AUTH_FAILED_STRING in r.text:
            # assuming its redirecting to login
            self.login()
            return self._get_url(url)

        self._check_response("Failed to GET url", r)
        return r

    def _get_zone_key(self, key, zone_id=0):
        zone = self._get_zone(zone_id)
        if not zone:
            raise KeyError("Zone {0} invalid.".format(zone_id))

        if key in zone:
            return zone[key]
        raise KeyError("Zone {0} key \"{1}\" invalid.".format(zone_id, key))

    def print_all_zone_data(self, zone_id):
        json = self._get_zone(zone_id)
        for key in sorted(json.keys()):
            print("{0}: {1}".format(key, json[key]))

    def _get_thermostat_key(self, key):
        thermostat = self._get_thermostat_json()
        if thermostat and key in thermostat:
            return thermostat[key]
        raise KeyError("Key \"{0}\" not in the thermostat JSON!".format(key))

    def _get_zone(self, zone_id=0):
        thermostat = self._get_thermostat_json()
        if not thermostat:
            return None
        if len(thermostat['zones']) > zone_id:
            return thermostat['zones'][zone_id]
        return None

    def _get_thermostat_json(self):
        if self.thermostat_json is None:
            r = self._get_url("/houses/" + str(self.house_id) + "/xxl_thermostats")
            if r and r.status_code == 200:
                ts = json.loads(r.text)
                if len(ts):
                    self.thermostat_json = ts[0]
                else:
                    raise Exception("Nothing in the JSON")
            else:
                self._check_response("Failed to get thermostat JSON, session probably timed out", r)
        return self.thermostat_json

    def _check_response(self, description, r):
        if r.status_code != 200:
            raise Exception("{description}: \n"
                            "  Code: {code}\n"
                            "  Header: {header}\n"
                            "  Text: {text}".format(description=description, code=r.status_code, header=r.header,
                                                    text=r.text))

    def get_zone_cooling_setpoint(self, zone_id=0):
        return self._get_zone_key('cooling_setpoint', zone_id=zone_id)

    def get_zone_heating_setpoint(self, zone_id=0):
        return self._get_zone_key('heating_setpoint', zone_id=zone_id)

    def get_zone_temperature(self, zone_id=0):
        return self._get_zone_key('temperature', zone_id=zone_id)

    def get_fan_mode(self):
        return self._get_thermostat_key('fan_mode')

    def get_outdoor_temperature(self):
        if self.has_outdoor_temperature():
            return self._get_thermostat_key('outdoor_temperature')
        else:
            raise Exception("This system does not have an outdoor temperature sensor")

    def has_outdoor_temperature(self):
        return self._get_thermostat_key("have_odt")

    def _get_setpoint_url(self, zone_id=0):
        zone_id = self._get_zone_key('id', zone_id)
        return "/houses/" + str(self.house_id) + "/xxl_zones/" + str(zone_id) + "/setpoints"

    def set_min_max_temp(self, min_temperature, max_temperature, zone_id=0):
        url = self._get_setpoint_url(zone_id)

        data = {
            'cooling_setpoint': max_temperature,
            'cooling_integer': max_temperature,
            'heating_setpoint': min_temperature,
            'heating_integer': min_temperature
        }

        r = self._put_url(url, data)
        self._check_response("Could not set min/max temperature", r)

    def get_zone_ids(self):
        return list(range(len(self._get_thermostat_key("zones"))))

    def get_setpoint_limits(self):
        return (self._get_thermostat_key("temperature_low_limit"), self._get_thermostat_key("temperature_high_limit"))

    def get_deadband(self):
        return self._get_thermostat_key("temperature_deadband")

    def get_relative_humidity(self):
        if self.has_relative_humidity():
            return self._get_thermostat_key("current_relative_humidity")
        else:
            raise Exception("This system does not have a relative humidity sensor.")

    def has_relative_humidity(self):
        return self._get_thermostat_key("have_rh")

    def print_all_json_data(self):
        json = self._get_thermostat_json()
        for key in sorted(json.keys()):
            print("{0}: {1}".format(key, json[key]))

    def get_compressor_speed(self):
        if self.has_variable_speed_compressor():
            return self._get_thermostat_key("compressor_speed")
        else:
            raise Exception("This system does not have a variable speed compressor.")

    def has_variable_speed_compressor(self):
        return self._get_thermostat_key("has_variable_speed_compressor")

    def get_variable_fan_speed_limits(self):
        if self.has_variable_fan_speed:
            return (self._get_thermostat_key("min_fan_speed"), self._get_thermostat_key("max_fan_speed"))

    def get_fan_speed(self):
        if self.has_variable_fan_speed():
            return self._get_thermostat_key("fan_speed")
        else:
            return 1.0 if self.is_blower_active() else 0.0

    def is_blower_active(self):
        return self._get_thermostat_key("blower_active")

    def has_emergency_heat(self):
        return self._get_thermostat_key("emergency_heat_supported")

    def is_emergency_heat_active(self):
        if self.has_emergency_heat():
            return self._get_thermostat_key("emergency_heat_active")
        else:
            raise Exception("This system does not support emergency heat")

    def has_variable_fan_speed(self):
        return self._get_thermostat_key("fan_type") == "VSPD"

