from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="blackroad-ticket-system",
    version="1.0.0",
    author="BlackRoad Foundation",
    author_email="support@blackroad.foundation",
    description="Production-grade Python helpdesk ticket engine with SLA tracking, "
                "auto-prioritisation, queue management, Stripe billing, and reporting.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/BlackRoad-Foundation/blackroad-ticket-system",
    project_urls={
        "Bug Tracker": "https://github.com/BlackRoad-Foundation/blackroad-ticket-system/issues",
        "Source Code": "https://github.com/BlackRoad-Foundation/blackroad-ticket-system",
    },
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=[],
    extras_require={"dev": ["pytest>=7"]},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Office/Business",
    ],
    keywords="helpdesk ticket sla support queue management stripe billing",
)
