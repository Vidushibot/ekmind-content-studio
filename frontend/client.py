import httpx

BASE_URL = "http://127.0.0.1:8000"


class ApiError(RuntimeError):
    pass


def _raise_api_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    raise ApiError(str(detail) or f"Request failed with status {response.status_code}")


def post(path: str, payload: dict, timeout: float = 60) -> dict:
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{BASE_URL}{path}", json=payload)
        _raise_api_error(response)
        return response.json()


def get(path: str) -> object:
    with httpx.Client(timeout=10) as client:
        response = client.get(f"{BASE_URL}{path}")
        _raise_api_error(response)
        return response.json()
