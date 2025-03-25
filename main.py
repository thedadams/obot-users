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
    auth_header = f"Bearer {os.environ['OBOT_API_KEY']}"

    resp = requests.get(f"{obot_url}/api/active-users?start={os.environ.get('START', '')}&end={os.environ.get('END', '')}", headers={"Authorization": auth_header})
    if resp.status_code != 200:
        print(resp.text)
        sys.exit(1)
    
    print(resp.text)


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