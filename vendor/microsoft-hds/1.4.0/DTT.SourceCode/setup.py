from pathlib import Path
from setuptools import find_packages, setup

__NAME__ = "dtt"
__version__ = "0.3.1.1271"

ROOT_DIR = Path(__file__).parent

EXCLUDED_PACKAGES = ("tests", "tests.*", "test", "test.*")


def parse_requirements(requirements_file: Path, collected=None, visited=None):
    """Parse requirements recursively, skipping comments, blanks, and options."""
    if collected is None:
        collected = set()

    if visited is None:
        visited = set()

    if requirements_file in visited:
        return sorted(collected) if collected else []

    visited.add(requirements_file)

    with requirements_file.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("-r") or line.startswith("--requirement"):
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    parse_requirements(requirements_file.parent / parts[1], collected, visited)
                continue

            # Skip non-package pip options and editable installs
            if line.startswith("-"):
                continue

            requirement = line.split(" #", 1)[0].strip()
            if requirement:
                collected.add(requirement)

    return sorted(collected)


setup(
    name=__NAME__,
    version=__version__,
    author="Microsoft Cloud for Healthcare",
    description="Data Transformation Toolkit Packages",
    long_description=(ROOT_DIR / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    package_dir={"": "src"},
    packages=find_packages(
        where="src",
        include=[
            "common",
            "common.*",
            "configuration_compiler",
            "configuration_compiler.*",
            "dmf",
            "dmf.*",
            "rmt",
            "rmt.*",
        ],
        exclude=EXCLUDED_PACKAGES,
    ),
    install_requires=parse_requirements(
        ROOT_DIR / "requirements" / "requirements.txt"
    ),
    classifiers=[
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.10,<4.0",
)
