# -*- coding: utf-8 -*-
"""Configuración común de pytest: la raíz del repo queda en sys.path."""
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
