import datetime
import json
import os
import subprocess
import sys
from time import sleep
from uuid import uuid4

import pytz
import requests
from gptscript.gptscript import GPTScript
from gptscript.opts import Options


async def main():
    obot_url = os.environ.get("OBOT_URL", "http://localhost:8080")

    token, expiration = "", ""
    if "GPTSCRIPT_EXISTING_CREDENTIAL" in os.environ:
        # If the existing credential is set, then try to refresh it.
        token, expiration = refresh_token(obot_url, os.environ["GPTSCRIPT_EXISTING_CREDENTIAL"])

    if token == "":
        auth_provider = await prompt_for_auth_provider(obot_url)
        # If there's no existing credential or refresh failed, then create a new one.
        token, expiration = await create_token(
            obot_url,
            auth_provider["namespace"],
            auth_provider["id"],
        )

    print('{"env": {"OBOT_API_KEY": "%s"}, "expiresAt": "%s", "refreshToken": "%s"}' % (
        token, expiration, token,
    ))


async def prompt_for_auth_provider(obot_url: str) -> dict:
    resp = requests.get(f"{obot_url}/api/auth-providers")
    if resp.status_code != 200:
        print(resp.text)
        sys.exit(1)

    auth_providers = [auth_provider for auth_provider in resp.json()["items"] if auth_provider["configured"]]
    if len(auth_providers) == 0:
        print("No auth providers found")
        sys.exit(1)
    elif len(auth_providers) == 1:
        return auth_providers[0]
    gptscript = GPTScript()
    run = gptscript.run(
        "sys.prompt",
        Options(
            input=json.dumps(
                {
                    "message": f"Please choose an auth provider:\n\n{"\n".join([str(i+1) + ": " + a["name"]for i, a in enumerate(auth_providers)])}\n",
                    "fields": [{"name": "Auth Provider", "description": "Auth provider to use"}],
                    "metadata": {"toolDisplayName": "Obot Cred", "toolContext": "credential"}
                }
            ))
    )
    out = await run.text()
    try:
        return auth_providers[int(json.loads(out)["Auth Provider"]) - 1]
    except (IndexError, ValueError):
        print("Invalid selection")
        sys.exit(1)


async def create_token(obot_url: str, auth_provider_namespace: str, auth_provider_name: str) -> (str, str):
    token_request_id = str(uuid4())

    resp = requests.post(f"{obot_url}/api/token-request", json={"id": token_request_id, "providerNamespace": auth_provider_namespace, "providerName": auth_provider_name})
    if resp.status_code != 200:
        print(resp.text)
        sys.exit(1)

    token_path = resp.json()["token-path"]
    gptscript = GPTScript()
    run = gptscript.run(
        "sys.prompt",
        Options(
            input=json.dumps(
                {
                    "message": f"Opening browser to {token_path}. " +
                               "If there is an issue paste this link into a browser manually.",
                    "metadata": {"toolDisplayName": "Obot Cred", "authURL": f"{token_path}", "authType": "oauth", "toolContext": "credential"}
                }
            ))
    )
    out = await run.text()
    # If the caller didn't open the browser, open it now
    if out == "" or out == "null" or json.loads(out).get("handled", "") != "true":
        subprocess.run([sys.executable, "-m", "webbrowser", "-n", token_path], stdout=subprocess.DEVNULL)

    token_resp = poll_for_token(obot_url, token_request_id)

    return token_resp["token"], calculate_expires_at(token_resp.get("expiresAt", ""))


def refresh_token(obot_url: str, cred: str) -> (str, str):
    if cred == "":
        return "", ""

    try:
        token = json.loads(cred)["refreshToken"]
    except json.decoder.JSONDecodeError:
        return "", ""

    resp = requests.post(f"{obot_url}/api/tokens", headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        return "", ""

    res = resp.json()
    return res["token"], calculate_expires_at(res.get("expiresAt", ""))


def calculate_expires_at(expires_at: str) -> str:
    expiration = datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(hours=1)
    if expires_at != "":
        expiration = datetime.datetime.fromisoformat(expires_at)
        now = datetime.datetime.now(tz=expiration.tzinfo)
        # Tokens expire in half the time as the actual expiration, so they can be refreshed.
        expiration = now + (expiration - now) / 2

    return expiration.isoformat()


def create_token_request(obot_url: str, id: str):
    resp = requests.post(f"{obot_url}/api/token-request", json={"id": id})
    if resp.status_code != 200:
        raise Exception(resp.text)


def poll_for_token(obot_url: str, id: str) -> dict:
    while True:
        resp = requests.get(f"{obot_url}/api/token-request/{id}")
        if resp.status_code == 200:
            res = resp.json()
            if "token" in res and res["token"] is not None and res["token"] != "":
                return res

            sleep(1)
        else:
            raise Exception(resp.text)


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("User cancelled")
        exit(1)
    except Exception as e:
        print(str(e))
        exit(1)