import setuptools

setuptools.setup(
    name="autobot",
    version="0.1.0",
    description="Framework Autobot",
    author="Ton Nom",
    author_email="ton.email@example.com",
    package_dir={"": "src"},                           # ← Indique que le code source est dans src/
    packages=setuptools.find_packages(where="src"),    # ← Recherche les packages sous src/
    install_requires=[
        # Copie ici les lignes de requirements.txt, par ex.:
        "fastapi",
        "uvicorn",
        "requests",
        # …
    ],
    extras_require={
        "dev": [
            # Copie ici les lignes de requirements.dev.txt, ex.:
            "pytest",
            "coverage",
            # …
        ]
    },
    python_requires=">=3.10",
)
