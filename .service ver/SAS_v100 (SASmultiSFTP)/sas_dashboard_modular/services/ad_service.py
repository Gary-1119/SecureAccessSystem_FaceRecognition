import html
import requests
import xml.etree.ElementTree as ET


class ActiveDirectoryService:
    """SOAP / Active Directory logic migrated from lockapp.py."""

    def __init__(self, soap_url: str, debug_callback=None):
        self.soap_url = soap_url
        self.debug_callback = debug_callback

    def debug(self, message: str):
        if self.debug_callback:
            self.debug_callback(message)
        else:
            print("[AD DEBUG]", message)

    def validate_ntid_in_ad(self, ntid: str) -> bool:
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                         xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                         xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <IsUserExistsInAD xmlns="http://jpetewebapp/jtesw_ws/">
              <userName>{html.escape(ntid)}</userName>
            </IsUserExistsInAD>
          </soap12:Body>
        </soap12:Envelope>"""

        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "SOAPAction": "http://jpetewebapp/jtesw_ws/IsUserExistsInAD",
        }

        try:
            self.debug(f"Calling IsUserExistsInAD SOAP for NTID: {ntid}")
            response = requests.post(
                self.soap_url,
                data=soap.encode("utf-8"),
                headers=headers,
                timeout=15,
            )
            self.debug(f"IsUserExistsInAD HTTP status: {response.status_code}")
            response.raise_for_status()
            result = self.parse_ad_response(response.text)
            self.debug(f"IsUserExistsInAD parsed result: {result}")
            return result
        except Exception as e:
            self.debug(f"IsUserExistsInAD exception: {type(e).__name__}: {e}")
            return False

    def parse_ad_response(self, response: str) -> bool:
        if not response or not response.strip():
            return False

        try:
            root = ET.fromstring(response)
            for elem in root.iter():
                if "ReturnedValue" in elem.tag:
                    value = (elem.text or "").strip().lower()
                    return value == "true"
            return False
        except Exception as e:
            self.debug(f"AD parse error: {type(e).__name__}: {e}")
            return False

    def encrypt_password(self, password: str):
        safe_password = html.escape(password)
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                         xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                         xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <DESEncrypt xmlns="http://jpetewebapp/jtesw_ws/">
              <sender>{safe_password}</sender>
            </DESEncrypt>
          </soap12:Body>
        </soap12:Envelope>"""

        try:
            self.debug("Calling DESEncrypt SOAP...")
            response = requests.post(
                self.soap_url,
                data=soap.encode("utf-8"),
                headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                timeout=15,
            )
            self.debug(f"DESEncrypt HTTP status: {response.status_code}")
            response.raise_for_status()
            root = ET.fromstring(response.text)
            for elem in root.iter():
                if elem.tag.endswith("DESEncryptResult"):
                    self.debug("DESEncryptResult received.")
                    return (elem.text or "").strip()

            self.debug("DESEncryptResult not found in response.")
            return None

        except Exception as e:
            self.debug(f"DESEncrypt exception: {type(e).__name__}: {e}")
            return None

    def validate_ntid_password_in_ad(self, ntid: str, password: str) -> bool:
        encrypted_password = self.encrypt_password(password)
        if not encrypted_password:
            return False

        safe_ntid = html.escape(ntid)
        safe_encrypted_password = html.escape(encrypted_password)

        soap = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                         xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                         xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <ValidateUserCredentialsInAD xmlns="http://jpetewebapp/jtesw_ws/">
              <userName>{safe_ntid}</userName>
              <password>{safe_encrypted_password}</password>
            </ValidateUserCredentialsInAD>
          </soap12:Body>
        </soap12:Envelope>"""

        try:
            response = requests.post(
                self.soap_url,
                data=soap.encode("utf-8"),
                headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                timeout=15,
            )
            response.raise_for_status()
            root = ET.fromstring(response.text)
            for elem in root.iter():
                if elem.tag.endswith("ReturnedValue"):
                    return (elem.text or "").strip().lower() == "true"
            return False
        except Exception as e:
            self.debug(f"Password validation exception: {type(e).__name__}: {e}")
            return False

    def validate_ntid_password_with_debug(self, ntid: str, password: str):
        debug_steps = []

        def step(message: str):
            debug_steps.append(message)
            self.debug(message)

        safe_ntid = ntid.strip().lower()
        step(f"Input NTID: {safe_ntid}")

        if not safe_ntid:
            return False, "NTID is empty.", "\n".join(debug_steps)

        if not password:
            step("Password is empty.")
            return False, "Password is empty.", "\n".join(debug_steps)

        step("Step 1/3: Checking NTID exists in Active Directory...")
        ntid_exists = self.validate_ntid_in_ad(safe_ntid)
        step(f"NTID exists result: {ntid_exists}")

        if not ntid_exists:
            return (
                False,
                "NTID does not exist or the Active Directory service is unreachable.",
                "\n".join(debug_steps),
            )

        step("Step 2/3: Encrypting password using SOAP DESEncrypt...")
        encrypted_password = self.encrypt_password(password)

        if not encrypted_password:
            step("Password encryption failed or SOAP service did not return DESEncryptResult.")
            return (
                False,
                "Password encryption failed or SOAP service is unreachable.",
                "\n".join(debug_steps),
            )

        step("Password encryption result: received encrypted token.")
        step("Step 3/3: Validating NTID + encrypted password in Active Directory...")

        safe_ntid_xml = html.escape(safe_ntid)
        safe_encrypted_password = html.escape(encrypted_password)

        soap = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                         xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                         xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <ValidateUserCredentialsInAD xmlns="http://jpetewebapp/jtesw_ws/">
              <userName>{safe_ntid_xml}</userName>
              <password>{safe_encrypted_password}</password>
            </ValidateUserCredentialsInAD>
          </soap12:Body>
        </soap12:Envelope>"""

        try:
            response = requests.post(
                self.soap_url,
                data=soap.encode("utf-8"),
                headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                timeout=15,
            )
            step(f"Credential validation HTTP status: {response.status_code}")
            response.raise_for_status()

            root = ET.fromstring(response.text)
            for elem in root.iter():
                if elem.tag.endswith("ReturnedValue"):
                    value = (elem.text or "").strip().lower()
                    step(f"Credential ReturnedValue: {value}")
                    if value == "true":
                        return True, "Login validated successfully.", "\n".join(debug_steps)
                    return False, "Invalid NTID or password.", "\n".join(debug_steps)

            step("Credential validation response did not contain ReturnedValue.")
            return (
                False,
                "Active Directory response did not contain a validation result.",
                "\n".join(debug_steps),
            )

        except Exception as e:
            step(f"Credential validation exception: {type(e).__name__}: {e}")
            return (
                False,
                f"Active Directory validation error: {e}",
                "\n".join(debug_steps),
            )
