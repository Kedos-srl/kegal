from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="kegal",
    version="0.1.2.2",
    author="Kedos srl",
    author_email="info@kedos-srl.it",
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
    install_requires=requirements,
    include_package_data=True,
    package_data={
        "kegal": ["docs/*.md"],
    },
)
