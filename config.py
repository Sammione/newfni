BASE_URL = "https://sysprosystembackend-develop-hybyc7adhkh4cgfy.eastus-01.azurewebsites.net/"
FAQ_ENDPOINT = "/api/v1/FNI"

def get_auth_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


