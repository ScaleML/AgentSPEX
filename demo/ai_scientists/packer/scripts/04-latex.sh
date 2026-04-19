#!/bin/bash
# 04-latex.sh — Install LaTeX toolchain for PDF compilation
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get install -y \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    texlive-science \
    texlive-latex-extra

# Verify installation
pdflatex --version
bibtex --version
