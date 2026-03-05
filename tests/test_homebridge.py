from __future__ import annotations

from unittest.mock import MagicMock, patch

from loadctl.homebridge import HomebridgeClient


def test_login():
    client = HomebridgeClient("http://localhost:8581", "admin", "admin")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok123"}
    mock_resp.raise_for_status = MagicMock()
    with patch("loadctl.homebridge.requests.post", return_value=mock_resp) as mock_post:
        client.login()
        mock_post.assert_called_once()
        assert client._token == "tok123"


def test_get_accessory_state():
    client = HomebridgeClient("http://localhost:8581", "admin", "admin")
    client._token = "tok123"
    accessories = [
        {
            "aid": 10,
            "serviceName": "Pool Pump",
            "type": "Switch",
            "serviceCharacteristics": [
                {"description": "On", "value": 1, "iid": 11, "type": "On"},
            ],
        },
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = accessories
    mock_resp.raise_for_status = MagicMock()
    with patch("loadctl.homebridge.requests.get", return_value=mock_resp):
        state = client.get_accessory_state("Pool Pump")
        assert state is True


def test_set_accessory_off():
    client = HomebridgeClient("http://localhost:8581", "admin", "admin")
    client._token = "tok123"
    client._accessory_cache = {"Pool Pump": {"aid": 10, "on_iid": 11}}
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    with patch("loadctl.homebridge.requests.put", return_value=mock_resp) as mock_put:
        client.set_accessory("Pool Pump", False)
        mock_put.assert_called_once()
        call_json = mock_put.call_args[1]["json"]
        assert call_json["value"] == 0
