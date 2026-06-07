from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

_CORE = [
    "pydantic>=2.0.0",
    "PyYAML>=6.0",
    "jsonschema>=4.20.0",
    "PyMuPDF>=1.24.0",
    "mcp>=1.0.0",
]

_EXTRAS = {
    "anthropic": ["anthropic>=0.25.0"],
    "openai":    ["openai>=1.0.0"],
    "ollama":    ["ollama>=0.2.0"],
    "aws":       ["boto3>=1.34.0", "botocore>=1.34.0"],
    "gemini":    ["google-genai>=1.0.0"],
}
_EXTRAS["all"] = sorted({dep for deps in _EXTRAS.values() for dep in deps})

setup(
    name="kegal",
    version="0.1.3.0",
    author="Kedos srl",
    author_email="fabio.gagliardi@kedos-srl.it",
    description="KeGAL - Kedos Graph Agent for LLM",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/kedos-srl/kegal",
    packages=find_packages(exclude=["test", "test.*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.10",
    install_requires=_CORE,
    extras_require=_EXTRAS,
    entry_points={
        "console_scripts": [
            "kegal=kegal.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "kegal": ["docs/*.md"],
    },
)
