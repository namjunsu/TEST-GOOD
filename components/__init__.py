"""
Components package for web_interface
Modular UI components for better maintainability
"""

from .pdf_viewer import PDFViewer
from .sidebar_library import render_sidebar_library

__all__ = ['PDFViewer', 'render_sidebar_library']
