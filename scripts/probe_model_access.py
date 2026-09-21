"""Check gated model access without downloading weights or exposing credentials."""
from __future__ import annotations

import argparse
import json

from huggingface_hub import get_hf_file_metadata, hf_hub_url
from huggingface_hub.utils import HfHubHTTPError, LocalTokenNotFoundError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--filename", default="config.json")
    args = parser.parse_args()
    result = {"repository": args.repository, "revision": args.revision, "filename": args.filename}
    try:
        metadata = get_hf_file_metadata(
            hf_hub_url(args.repository, args.filename, revision=args.revision),
            token=True, timeout=20,
        )
        result.update(access="OK", size_bytes=metadata.size, resolved_revision=metadata.commit_hash)
    except LocalTokenNotFoundError:
        result.update(access="LOGIN_REQUIRED")
    except HfHubHTTPError as error:
        status = error.response.status_code if error.response is not None else None
        result.update(access="HTTP_ERROR", http_status=status)
    except (OSError, TimeoutError) as error:
        # Do not print request headers, signed download URLs or exception bodies.
        result.update(access="NETWORK_ERROR", error_type=type(error).__name__)
    print(json.dumps(result, indent=2))
    return 0 if result["access"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
