from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.request import pathname2url


def uri_to_path(uri: str) -> Path:
    url_parse_result = urlparse(uri)
    if url_parse_result.scheme:
        scheme_length = len(url_parse_result.scheme) + len("://")
    else:
        scheme_length = 0
    return Path(uri[scheme_length:])


def is_a_file_uri(uri: str) -> bool:
    url_parse_result = urlparse(uri)
    return url_parse_result.scheme == "file"


def is_azure_blob_storage_uri(uri: str) -> bool:
    url_parse_result = urlparse(uri)
    return url_parse_result.scheme in ("abfss", "abfs", "adls", "adl")


def uri_parent_path(uri: str) -> str:
    scheme, netloc, path, _params, _query, _fragment = urlparse(uri)
    path_parent = str(Path(path).parent)
    return f"{scheme}://{netloc}{path_parent}"


def path_to_uri(path: Path) -> str:
    return urljoin("file:", pathname2url(str(path)))
