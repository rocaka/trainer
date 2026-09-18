"""Manual synthetic probe for the user-authorized okai origin; no secret output."""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_transport import relay_settings, key_service, diagnose
from server import load_api_key
if __name__ == '__main__':
    settings = relay_settings()
    if not settings or urlparse(settings['endpoint']).hostname != 'okai.la':
        print('Configured target is not the authorized okai.la endpoint. No request sent.')
        sys.exit(1)
    result = diagnose(settings, load_api_key('custom', key_service(settings)))
    print(json.dumps(result, ensure_ascii=False))
