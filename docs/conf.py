"""Sphinx configuration for conda-sigstore documentation."""

from __future__ import annotations

project = html_title = "conda-sigstore"
copyright = "2026, Jannis Leidel"
author = "Jannis Leidel"

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_sitemap",
]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "tasklist",
]

myst_url_schemes = {
    "http": None,
    "https": None,
    "mailto": None,
    "ftp": None,
}

html_theme = "conda_sphinx_theme"

html_theme_options = {
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/conda-incubator/conda-sigstore",
            "icon": "fa-brands fa-square-github",
            "type": "fontawesome",
        },
    ],
}

html_context = {
    "github_user": "conda-incubator",
    "github_repo": "conda-sigstore",
    "github_version": "main",
    "doc_path": "docs",
}

html_extra_path = ["robots.txt"]
html_baseurl = "https://conda-incubator.github.io/conda-sigstore/"
exclude_patterns = ["_build"]
